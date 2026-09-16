"""Index PHOTOS_DIR into the photo table. The loop lives in library.scan."""
import click
from flask.cli import with_appcontext

from database.db import execute, fetch_all, insert
from library.scan import run_scan_command, scan
from photos.config import photos_dir
from photos.meta import IMAGE_EXTENSIONS, read_image

INSERT_PHOTO = """
INSERT INTO photo
    (path, taken_at, width, height, format, size_bytes, mtime_ns)
VALUES (?, ?, ?, ?, ?, ?, ?)
"""

# caption is deliberately absent: it is the curated column and a rescan
# must never touch it.
UPDATE_PHOTO = """
UPDATE photo
SET path = ?, taken_at = ?, width = ?, height = ?, format = ?,
    size_bytes = ?, mtime_ns = ?
WHERE id = ?
"""


def _insert_photo(path, meta, stat):
    insert(INSERT_PHOTO, (
        path, meta['taken_at'], meta['width'], meta['height'], meta['format'],
        stat.st_size, stat.st_mtime_ns,
    ))


def _update_photo(photo_id, path, meta, stat):
    execute(UPDATE_PHOTO, (
        path, meta['taken_at'], meta['width'], meta['height'], meta['format'],
        stat.st_size, stat.st_mtime_ns, photo_id,
    ))


def scan_photos(force_removals=False):
    """Index PHOTOS_DIR into the photo table. See library.scan.scan."""
    return scan(
        root=photos_dir(), extensions=IMAGE_EXTENSIONS, table='photo',
        noun='image', variable='PHOTOS_DIR', read=read_image,
        insert=_insert_photo, update=_update_photo,
        fetch_all=fetch_all, execute=execute, force_removals=force_removals,
    )


@click.command('scan-photos')
@click.option('--force-removals', is_flag=True,
              help="Delete stale rows even when that would gut the table.")
@with_appcontext
def scan_photos_command(force_removals):
    """Index PHOTOS_DIR into the photo table."""
    run_scan_command(scan_photos, force_removals)
