import logging
import os

from database.db import execute, fetch_all, insert
from music.config import MAX_PATH_LENGTH, music_dir
from music.tags import AUDIO_EXTENSIONS, read_tags

logger = logging.getLogger(__name__)

INSERT_TRACK = """
INSERT INTO track
    (path, title, artist, album, track_no, duration_seconds,
     format, size_bytes, mtime)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
"""


def find_audio_files(root):
    """Yield every audio file under `root`, sorted within each directory.

    Dotfiles and dot directories are skipped. A drive that has been mounted on
    a Mac carries `._name.mp3` AppleDouble stubs, which satisfy the extension
    check while being unplayable metadata, and `.Trashes`, which can hold
    deleted media.
    """
    for dirpath, dirnames, filenames in os.walk(root):
        # Pruned in place so os.walk does not descend into them at all.
        dirnames[:] = [name for name in dirnames if not name.startswith('.')]
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
        _file_format(path), stat.st_size, int(stat.st_mtime),
    ))


def scan_music():
    """Index MUSIC_DIR into the track table.

    Returns counts of added, updated, unchanged, removed and skipped files.
    """
    root = music_dir()
    counts = {'added': 0, 'updated': 0, 'unchanged': 0,
              'removed': 0, 'skipped': 0}

    for path in find_audio_files(root):
        try:
            stat = os.stat(path)
        except OSError as err:
            logger.error("skipping unreadable file %s: %s", path, err)
            counts['skipped'] += 1
            continue
        _insert_track(path, read_tags(path), stat)
        counts['added'] += 1

    return counts
