"""The photo library: newest first, captions, originals and thumbnails.

Clients only ever send an id. `path` is never in a response, as with music.
"""
import mimetypes
import os

from flask import Blueprint, abort, jsonify, request, send_file

from api import json_body
from database.db import execute, fetch_all, fetch_one, insert
from photos.config import photos_dir, resolve_inside_photos_dir
from photos.scanner import INSERT_PHOTO
from photos.thumbs import SIZES, forget, thumbnail
from photos.upload import Rejected, save_upload

bp = Blueprint('photos', __name__)

DEFAULT_LIMIT = 60
MAX_LIMIT = 200
MAX_CAPTION = 255

PHOTO_COLUMNS = "id, taken_at, width, height, format, size_bytes, caption, created_at"
# photo_recent (taken_at, id) serves this sort; test_schema ties them together.
SELECT_PAGE = (
    f"SELECT {PHOTO_COLUMNS} FROM photo "
    "ORDER BY taken_at DESC, id DESC LIMIT ? OFFSET ?"
)
COUNT_ALL = "SELECT COUNT(*) AS n FROM photo"


def _positive_int(name, default, maximum=None):
    raw = request.args.get(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        abort(400, description=f"{name} must be an integer")
    if value < 0 or (name == 'limit' and value == 0):
        abort(400, description=f"{name} must be positive")
    if maximum is not None and value > maximum:
        abort(400, description=f"{name} must be at most {maximum}")
    return value


@bp.route('/photos', methods=['GET'])
def list_photos():
    limit = _positive_int('limit', DEFAULT_LIMIT, MAX_LIMIT)
    offset = _positive_int('offset', 0)
    rows = fetch_all(SELECT_PAGE, (limit, offset))
    total = fetch_one(COUNT_ALL)['n']
    return jsonify({'photos': rows, 'total': total, 'limit': limit, 'offset': offset})


@bp.route('/photos/<int:photo_id>', methods=['GET'])
def get_photo(photo_id):
    photo = fetch_one(f"SELECT {PHOTO_COLUMNS} FROM photo WHERE id = ? LIMIT 1", (photo_id,))
    if photo is None:
        abort(404, description=f"no photo with id {photo_id}")
    return jsonify(photo)


@bp.route('/photos/<int:photo_id>', methods=['PUT'])
def set_caption(photo_id):
    """The one curated field. An empty string clears it."""
    caption, = json_body('caption')
    if not isinstance(caption, str):
        abort(400, description="caption must be a string")
    caption = caption.strip()[:MAX_CAPTION] or None
    if not execute("UPDATE photo SET caption = ? WHERE id = ?", (caption, photo_id)):
        abort(404, description=f"no photo with id {photo_id}")
    return "", 204


def _stored_path(photo_id):
    """The on-disk path for a row, or a 404 that does not confirm the row exists.

    Same reasoning as the music stream: a containment refusal must look like
    an unknown id, while an indexed-but-missing file is reported as such.
    """
    row = fetch_one("SELECT path FROM photo WHERE id = ? LIMIT 1", (photo_id,))
    if row is None:
        abort(404, description=f"no photo with id {photo_id}")
    path = resolve_inside_photos_dir(row['path'])
    if path is None:
        abort(404, description=f"no photo with id {photo_id}")
    if not os.path.isfile(path):
        abort(404, description=f"photo {photo_id} is indexed but missing on disk")
    return path


@bp.route('/photos/<int:photo_id>/file', methods=['GET'])
def original(photo_id):
    path = _stored_path(photo_id)
    mimetype = mimetypes.guess_type(path)[0] or 'application/octet-stream'
    return send_file(path, mimetype=mimetype, conditional=True)


@bp.route('/photos/<int:photo_id>/thumb', methods=['GET'])
def thumb(photo_id):
    width = _positive_int('w', SIZES[0])
    if width not in SIZES:
        abort(400, description=f"w must be one of {', '.join(str(s) for s in SIZES)}")
    path = _stored_path(photo_id)
    cached = thumbnail(photo_id, path, width)
    response = send_file(cached, mimetype='image/jpeg', conditional=True)
    # The id never changes meaning; a deleted photo's id is never reused
    # for a different file by this app, so the thumbnail can be cached hard.
    response.headers['Cache-Control'] = 'public, max-age=31536000'
    return response


@bp.route('/photos', methods=['POST'])
def upload():
    """Multipart field `files`, repeatable. One bad file does not fail the rest.

    201 with what was added when at least one file was kept; 400 with the
    reasons when none was.
    """
    files = request.files.getlist('files')
    if not files:
        abort(400, description="send one or more files in the 'files' field")
    root = photos_dir()
    added, rejected = [], []
    for upload in files:
        name = upload.filename or 'file'
        try:
            path, meta, stat = save_upload(root, upload.stream, name)
        except Rejected as err:
            rejected.append({'name': name, 'reason': str(err)})
            continue
        photo_id = insert(INSERT_PHOTO, (
            path, meta['taken_at'], meta['width'], meta['height'], meta['format'],
            stat.st_size, stat.st_mtime_ns,
        ))
        added.append({
            'id': photo_id, 'taken_at': meta['taken_at'], 'width': meta['width'],
            'height': meta['height'], 'format': meta['format'],
            'size_bytes': stat.st_size, 'caption': None,
        })
    status = 201 if added else 400
    return jsonify({'added': added, 'rejected': rejected}), status


@bp.route('/photos/<int:photo_id>', methods=['DELETE'])
def delete_photo(photo_id):
    """Remove the file, its thumbnails and the row, in that order.

    A file that is already gone, or a path that fails containment, still
    lets the row go: the row is what the site shows, and it is wrong either
    way. Nothing outside PHOTOS_DIR is ever removed.
    """
    row = fetch_one("SELECT path FROM photo WHERE id = ? LIMIT 1", (photo_id,))
    if row is None:
        abort(404, description=f"no photo with id {photo_id}")
    path = resolve_inside_photos_dir(row['path'])
    if path is not None:
        try:
            os.remove(path)
        except FileNotFoundError:
            pass
    forget(photo_id)
    execute("DELETE FROM photo WHERE id = ?", (photo_id,))
    return "", 204
