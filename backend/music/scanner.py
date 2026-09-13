import logging
import os

import click
import mariadb
from flask.cli import with_appcontext

from database.db import execute, fetch_all, insert
from music.config import MAX_PATH_LENGTH, music_dir
from music.tags import AUDIO_EXTENSIONS, read_tags

logger = logging.getLogger(__name__)

# A single scan may not delete more than this share of the table without being
# told to. An unmounted drive, a changed MUSIC_DIR, or the same directory
# spelled differently (music_dir() resolves symlinks, so stored paths are
# resolved) all make every indexed path invisible while the walk itself
# succeeds — which is indistinguishable from the whole library being deleted.
REMOVAL_LIMIT = 0.5
# Below this many rows the proportional check is nuisance rather than safety.
REMOVAL_FLOOR = 10


class ScanAborted(RuntimeError):
    """Raised when a scan's removals look destructive rather than intended."""


INSERT_TRACK = """
INSERT INTO track
    (path, title, artist, album, track_no, duration_seconds,
     format, size_bytes, mtime_ns)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

UPDATE_TRACK = """
UPDATE track
   SET path = ?, title = ?, artist = ?, album = ?, track_no = ?,
       duration_seconds = ?, format = ?, size_bytes = ?, mtime_ns = ?
 WHERE id = ?
"""

SELECT_INDEXED = "SELECT id, path, size_bytes, mtime_ns FROM track"


def find_audio_files(root, on_error=None):
    """Yield every audio file under `root`, sorted within each directory.

    Dotfiles and dot directories are skipped. A drive that has been mounted on
    a Mac carries `._name.mp3` AppleDouble stubs, which satisfy the extension
    check while being unplayable metadata, and `.Trashes`, which can hold
    deleted media.

    Unreadable directories are logged and passed to `on_error` rather than
    vanishing. os.walk swallows scandir failures by default, which would let a
    partial library look like a complete one.
    """
    def report(err):
        logger.error("cannot read directory %s: %s",
                     getattr(err, 'filename', '?'), err)
        if on_error is not None:
            on_error(err)

    for dirpath, dirnames, filenames in os.walk(root, onerror=report):
        # Pruned in place so os.walk does not descend into them at all.
        # Sorted for a reproducible traversal order in logs.
        dirnames[:] = sorted(name for name in dirnames
                             if not name.startswith('.'))
        for name in sorted(filenames):
            if name.startswith('.'):
                continue
            if name.lower().endswith(AUDIO_EXTENSIONS):
                yield os.path.join(dirpath, name)


def _file_format(path):
    return os.path.splitext(path)[1].lstrip('.').lower()


def _insert_track(path, tags, stat):
    insert(INSERT_TRACK, (
        path, tags['title'], tags['artist'], tags['album'],
        tags['track_no'], tags['duration_seconds'],
        _file_format(path), stat.st_size, stat.st_mtime_ns,
    ))


def _update_track(track_id, path, tags, stat):
    execute(UPDATE_TRACK, (
        path, tags['title'], tags['artist'], tags['album'],
        tags['track_no'], tags['duration_seconds'],
        _file_format(path), stat.st_size, stat.st_mtime_ns, track_id,
    ))


def _skip(counts, reason):
    """Record a skipped file under both the rollup and its specific reason.

    The three reasons need three different fixes — rename the file, repair
    permissions, correct the tag data — so a single total is not actionable.
    """
    counts['skipped'] += 1
    counts[f'skipped_{reason}'] += 1


def _refuse_mass_removal(root, stale, indexed, found_any):
    """Raise ScanAborted if deleting `stale` would gut the table.

    Returns normally when the removal looks like ordinary attrition.

    This is deliberately louder than the unreadable-directory case, which
    defers removal silently: there we know the walk was incomplete, so
    skipping removal is automatically right. Here the walk succeeded and the
    result merely looks destructive, which needs a human to confirm.
    """
    if not found_any:
        raise ScanAborted(
            f"found no audio files under {root} but track holds "
            f"{len(indexed)} rows; refusing to delete them. "
            "Is the drive mounted? Pass --force-removals to proceed anyway."
        )
    if len(indexed) < REMOVAL_FLOOR:
        return
    share = len(stale) / len(indexed)
    if share > REMOVAL_LIMIT:
        raise ScanAborted(
            f"scan would remove {len(stale)} of {len(indexed)} rows "
            f"({share:.0%}) under {root}; refusing. Did MUSIC_DIR change, or "
            "did the drive remount under a different path? Pass "
            "--force-removals to proceed anyway."
        )


def scan_music(force_removals=False):
    """Index MUSIC_DIR into the track table.

    Incremental: a file whose size and mtime_ns match the indexed row is
    skipped without re-reading its tags, so rescanning a large library is
    cheap. Existing rows are updated in place rather than deleted and
    reinserted, so ids stay stable for future playlist references.

    Removal only runs when the walk was complete. An unreadable directory
    makes its files invisible, which looks exactly like them being deleted,
    and dropping those rows would be silent data loss.

    Even after a complete walk, a removal that would delete too large a
    share of the table is refused (see `_refuse_mass_removal`) unless
    `force_removals` is set, since an unmounted drive or a reconfigured
    MUSIC_DIR looks identical to a genuinely emptied library.

    That refusal is not atomic with respect to the writes already made in the
    same call: each statement commits on its own, so an aborted scan leaves
    the adds and updates in place and only the removals undone. The table is
    a rebuildable index and a re-run finishes the job, so this is coherent —
    but a listing will show stale rows alongside the new ones until then.

    Returns counts of added, updated, unchanged, removed, skipped (a rollup),
    skipped_too_long, skipped_unreadable, skipped_rejected and
    unreadable_dirs.
    """
    root = music_dir()
    unreadable = []
    indexed = {row['path']: row for row in fetch_all(SELECT_INDEXED)}
    counts = {'added': 0, 'updated': 0, 'unchanged': 0, 'removed': 0,
              'skipped': 0, 'skipped_too_long': 0, 'skipped_unreadable': 0,
              'skipped_rejected': 0, 'unreadable_dirs': 0}
    seen = set()
    found_any = False

    for path in find_audio_files(root, on_error=unreadable.append):
        # Recorded the moment the walk yields it. The file demonstrably
        # exists, so its row must survive even if we then fail to stat or to
        # write it — deleting it would renumber the track on a later scan and
        # orphan anything referencing the old id.
        found_any = True
        seen.add(path)
        if len(path) > MAX_PATH_LENGTH:
            # The column is VARCHAR(768). MySQL outside strict mode would
            # truncate, storing a path that can never stream.
            logger.error(
                "skipping path longer than %d characters (track.path cannot "
                "store it intact): %s", MAX_PATH_LENGTH, path)
            _skip(counts, 'too_long')
            continue
        try:
            stat = os.stat(path)
        except OSError as err:
            logger.error("skipping unreadable file %s: %s", path, err)
            _skip(counts, 'unreadable')
            continue

        row = indexed.get(path)
        if (row is not None
                and row['size_bytes'] == stat.st_size
                and row['mtime_ns'] == stat.st_mtime_ns):
            counts['unchanged'] += 1
            continue

        tags = read_tags(path)
        try:
            if row is None:
                _insert_track(path, tags, stat)
                counts['added'] += 1
            else:
                _update_track(row['id'], path, tags, stat)
                counts['updated'] += 1
        except (mariadb.IntegrityError, mariadb.DataError) as err:
            # A bad row; the next may be fine. A lost connection is
            # OperationalError/InterfaceError and deliberately propagates.
            logger.error("skipping %s, write rejected: %s", path, err)
            _skip(counts, 'rejected')
            continue

    counts['unreadable_dirs'] = len(unreadable)

    if unreadable:
        logger.error(
            "%d directories could not be read; skipping removal detection so "
            "rows for files beneath them are not deleted", len(unreadable))
        return counts

    stale = [row for path, row in indexed.items() if path not in seen]
    if stale and not force_removals:
        _refuse_mass_removal(root, stale, indexed, found_any)

    for row in stale:
        execute("DELETE FROM track WHERE id = ?", (row['id'],))
        counts['removed'] += 1

    return counts


@click.command('scan-music')
@click.option('--force-removals', is_flag=True,
              help="Delete stale rows even when that would gut the table.")
@with_appcontext
def scan_music_command(force_removals):
    """Index MUSIC_DIR into the track table."""
    try:
        counts = scan_music(force_removals=force_removals)
    except ScanAborted as err:
        raise click.ClickException(str(err))

    click.echo(
        "added {added}, updated {updated}, unchanged {unchanged}, "
        "removed {removed}".format(**counts))
    if counts['skipped']:
        click.echo(
            "skipped {skipped} (too long {skipped_too_long}, "
            "unreadable files {skipped_unreadable}, "
            "rejected {skipped_rejected})".format(**counts))

    blocked = counts['unreadable_dirs']
    if blocked:
        # Removal detection was skipped, so the index is knowingly stale.
        # Exit non-zero: this runs from a timer, and a silent partial success
        # is exactly the failure this scanner exists to avoid.
        raise click.ClickException(
            f"{blocked} director{'y' if blocked == 1 else 'ies'} could not be "
            "read, so stale rows were left in place. Fix the permissions and "
            "re-run."
        )
