import logging
import os

import click
from flask.cli import with_appcontext

from database.db import execute, fetch_all, insert
from library.rails import REMOVAL_FLOOR, REMOVAL_LIMIT, ScanAborted  # noqa: F401  (re-exported for tests and callers)
from library.scan import find_files, run_scan_command, scan
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
    return find_files(root, AUDIO_EXTENSIONS, on_error)


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


def scan_music(force_removals=False):
    """Index MUSIC_DIR into the track table. See library.scan.scan.

    The database and tag functions are looked up here at call time so the
    tests' stubs on this module take effect.
    """
    return scan(
        root=music_dir(), extensions=AUDIO_EXTENSIONS, table='track',
        noun='audio', variable='MUSIC_DIR', read=read_tags,
        insert=_insert_track, update=_update_track,
        fetch_all=fetch_all, execute=execute, force_removals=force_removals,
    )


@click.command('scan-music')
@click.option('--force-removals', is_flag=True,
              help="Delete stale rows even when that would gut the table.")
@with_appcontext
def scan_music_command(force_removals):
    """Index MUSIC_DIR into the track table."""
    run_scan_command(scan_music, force_removals)
