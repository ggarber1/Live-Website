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


def scan_music():
    """Index MUSIC_DIR into the track table.

    Returns counts of added, updated, unchanged, removed, skipped and
    unreadable_dirs.
    """
    root = music_dir()
    unreadable = []
    counts = {'added': 0, 'updated': 0, 'unchanged': 0,
              'removed': 0, 'skipped': 0, 'unreadable_dirs': 0}

    for path in find_audio_files(root, on_error=unreadable.append):
        try:
            stat = os.stat(path)
        except OSError as err:
            logger.error("skipping unreadable file %s: %s", path, err)
            counts['skipped'] += 1
            continue
        try:
            _insert_track(path, read_tags(path), stat)
        except (mariadb.IntegrityError, mariadb.DataError) as err:
            # This row is bad; the next one may be fine. A lost connection is
            # OperationalError/InterfaceError and deliberately propagates: the
            # connection is cached for the whole app context, so every
            # remaining file would pay for a full tag read before failing and
            # then be reported as merely "skipped", hiding a dead database
            # behind thousands of per-file entries.
            logger.error("skipping %s, insert rejected: %s", path, err)
            counts['skipped'] += 1
            continue
        counts['added'] += 1

    counts['unreadable_dirs'] = len(unreadable)
    return counts
