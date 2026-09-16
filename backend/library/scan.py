"""The scan loop shared by the media libraries.

Disk is the source of truth and the table is a rebuildable index keyed by
path. The loop is incremental (size and mtime_ns unchanged means the file is
not re-read), updates rows in place so ids survive, and only removes rows
after a complete walk that does not look destructive. The database and
metadata functions are passed in so each library's tests can stub its own.
"""
import logging
import os

import click
import mariadb

from library.rails import ScanAborted, refuse_mass_removal
from music.config import MAX_PATH_LENGTH

logger = logging.getLogger(__name__)


def find_files(root, extensions, on_error=None):
    """Yield every file under `root` with one of `extensions`, sorted within
    each directory.

    Dotfiles and dot directories are skipped. A drive that has been mounted on
    a Mac carries `._name.mp3` AppleDouble stubs, which satisfy the extension
    check while being unplayable metadata, and `.Trashes`, which can hold
    deleted media. The photo thumbnail cache is a dot directory for the same
    reason.

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
        dirnames[:] = sorted(name for name in dirnames
                             if not name.startswith('.'))
        for name in sorted(filenames):
            if name.startswith('.'):
                continue
            if name.lower().endswith(extensions):
                yield os.path.join(dirpath, name)


def _skip(counts, reason):
    """Record a skipped file under both the rollup and its specific reason.

    The reasons need different fixes — rename the file, repair permissions,
    correct the data — so a single total is not actionable.
    """
    counts['skipped'] += 1
    counts[f'skipped_{reason}'] += 1


def scan(root, extensions, table, noun, variable, read, insert, update,
         fetch_all, execute, force_removals=False):
    """Index `root` into `table`. Returns the nine counts.

    `read(path)` returns the metadata to store, or None to skip the file as
    rejected. `insert(path, meta, stat)` and `update(row_id, path, meta,
    stat)` write one row. `fetch_all` and `execute` are the database calls.

    Removal only runs when the walk was complete: an unreadable directory
    makes its files invisible, which looks exactly like them being deleted.
    Even after a complete walk, a removal that would delete too large a share
    of the table is refused (see refuse_mass_removal) unless `force_removals`.

    That refusal is not atomic with the writes already made: each statement
    commits on its own, so an aborted scan leaves the adds and updates in
    place and only the removals undone. A re-run finishes the job.
    """
    unreadable = []
    indexed = {row['path']: row for row in
               fetch_all(f"SELECT id, path, size_bytes, mtime_ns FROM {table}")}
    counts = {'added': 0, 'updated': 0, 'unchanged': 0, 'removed': 0,
              'skipped': 0, 'skipped_too_long': 0, 'skipped_unreadable': 0,
              'skipped_rejected': 0, 'unreadable_dirs': 0}
    seen = set()
    found_any = False

    for path in find_files(root, extensions, on_error=unreadable.append):
        # Recorded the moment the walk yields it. The file demonstrably
        # exists, so its row must survive even if we then fail to stat or to
        # write it — deleting it would renumber the row on a later scan.
        found_any = True
        seen.add(path)
        if len(path) > MAX_PATH_LENGTH:
            logger.error(
                "skipping path longer than %d characters (%s.path cannot "
                "store it intact): %s", MAX_PATH_LENGTH, table, path)
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

        meta = read(path)
        if meta is None:
            logger.error("skipping %s: not a readable %s file", path, noun)
            _skip(counts, 'rejected')
            continue
        try:
            if row is None:
                insert(path, meta, stat)
                counts['added'] += 1
            else:
                update(row['id'], path, meta, stat)
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
        refuse_mass_removal(root, stale, indexed, found_any,
                            table=table, noun=noun, variable=variable)

    for row in stale:
        execute(f"DELETE FROM {table} WHERE id = ?", (row['id'],))
        counts['removed'] += 1

    return counts


def run_scan_command(scan_fn, force_removals):
    """The CLI half every scan command shares: print counts, set the exit code.

    A refused scan and a knowingly stale index both exit non-zero, because
    this runs from a timer and a silent partial success is the failure the
    scanner exists to avoid. Skipped files alone do not: one permanently
    broken file must not fail a nightly run forever.
    """
    try:
        counts = scan_fn(force_removals=force_removals)
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
        raise click.ClickException(
            f"{blocked} director{'y' if blocked == 1 else 'ies'} could not be "
            "read, so stale rows were left in place. Fix the permissions and "
            "re-run."
        )
