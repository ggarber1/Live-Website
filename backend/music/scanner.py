import logging
import os

import mariadb

from database.db import execute, fetch_all, insert
from music.config import MAX_PATH_LENGTH, music_dir
from music.tags import AUDIO_EXTENSIONS, read_tags

logger = logging.getLogger(__name__)

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


def scan_music():
    """Index MUSIC_DIR into the track table.

    Incremental: a file whose size and mtime_ns match the indexed row is
    skipped without re-reading its tags, so rescanning a large library is
    cheap. Existing rows are updated in place rather than deleted and
    reinserted, so ids stay stable for future playlist references.

    Removal only runs when the walk was complete. An unreadable directory
    makes its files invisible, which looks exactly like them being deleted,
    and dropping those rows would be silent data loss.

    Returns counts of added, updated, unchanged, removed, skipped and
    unreadable_dirs.
    """
    root = music_dir()
    unreadable = []
    indexed = {row['path']: row for row in fetch_all(SELECT_INDEXED)}
    counts = {'added': 0, 'updated': 0, 'unchanged': 0,
              'removed': 0, 'skipped': 0, 'unreadable_dirs': 0}
    seen = set()

    for path in find_audio_files(root, on_error=unreadable.append):
        # Recorded the moment the walk yields it. The file demonstrably
        # exists, so its row must survive even if we then fail to stat or to
        # write it — deleting it would renumber the track on a later scan and
        # orphan anything referencing the old id.
        seen.add(path)
        try:
            stat = os.stat(path)
        except OSError as err:
            logger.error("skipping unreadable file %s: %s", path, err)
            counts['skipped'] += 1
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
            counts['skipped'] += 1
            continue

    counts['unreadable_dirs'] = len(unreadable)

    if unreadable:
        logger.error(
            "%d directories could not be read; skipping removal detection so "
            "rows for files beneath them are not deleted", len(unreadable))
        return counts

    for path, row in indexed.items():
        if path not in seen:
            execute("DELETE FROM track WHERE id = ?", (row['id'],))
            counts['removed'] += 1

    return counts
