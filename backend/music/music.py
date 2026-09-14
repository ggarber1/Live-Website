import os

from flask import Blueprint, abort, jsonify, request, send_file

from database.db import fetch_all, fetch_one
from music.config import resolve_inside_music_dir

bp = Blueprint('music', __name__)

DEFAULT_LIMIT = 50
MAX_LIMIT = 200

# path is deliberately absent: it is the Pi's absolute filesystem path, used
# only server-side when the stream endpoint resolves it from an id. mtime_ns
# is scanner bookkeeping and exceeds JavaScript's safe integer range anyway.
TRACK_COLUMNS = ("id, title, artist, album, track_no, duration_seconds, "
                 "format, size_bytes, created_at")

# `where` only ever receives a static SQL fragment defined in this module;
# every client-supplied value must go through `params` as a bound `?`.
SELECT_PAGE = (
    f"SELECT {TRACK_COLUMNS} FROM track {{where}} "
    "ORDER BY artist, album, track_no, title, id LIMIT ? OFFSET ?"
)
COUNT_ALL = "SELECT COUNT(*) AS n FROM track {where}"

# '!' rather than the default backslash: a backslash in an ESCAPE clause is
# itself subject to sql_mode (NO_BACKSLASH_ESCAPES would make '\\' two
# characters, which ESCAPE rejects). '!' needs no escaping in a string
# literal under any mode, so this means the same thing on every server.
LIKE_ESCAPE = '!'

SEARCH_WHERE = (
    "WHERE title LIKE ? ESCAPE '!' "
    "OR artist LIKE ? ESCAPE '!' "
    "OR album LIKE ? ESCAPE '!'"
)


def _positive_int(name, default):
    raw = request.args.get(name)
    if raw is None or raw == '':
        return default
    try:
        value = int(raw)
    except ValueError:
        abort(400, description=f"{name} must be an integer")
    if value < 0:
        abort(400, description=f"{name} cannot be negative")
    return value


def _pagination():
    limit = _positive_int('limit', DEFAULT_LIMIT)
    if limit < 1:
        abort(400, description="limit must be at least 1")
    offset = _positive_int('offset', 0)
    return min(limit, MAX_LIMIT), offset


def _like_term(term):
    """Wrap a search term for LIKE, escaping the wildcards it may contain.

    `%` and `_` are LIKE metacharacters. Filename-derived titles are full of
    underscores, and an unescaped `%` matches the whole library. The escape
    character itself is escaped first, or the escapes introduced below would
    themselves be escaped.
    """
    escaped = term
    for char in (LIKE_ESCAPE, '%', '_'):
        escaped = escaped.replace(char, LIKE_ESCAPE + char)
    return f"%{escaped}%"


def _search():
    """The WHERE clause and its bound parameters for ?q=, if given.

    The clause is a fixed string defined in this module; only the term is a
    bound parameter. That is the invariant noted above the query constants.
    """
    term = request.args.get('q', '').strip()
    if not term:
        return '', ()
    like = _like_term(term)
    return SEARCH_WHERE, (like, like, like)


@bp.route('/music/tracks', methods=['GET'])
def list_tracks():
    """A page of the library.

    Returns an envelope rather than a bare array — unlike the other services,
    this table holds thousands of rows and the client needs the total to
    paginate. The count and the page are two separate queries, but they can't
    disagree: the connection is per-request with autocommit off, and under
    InnoDB's default REPEATABLE READ the first read fixes the snapshot for the
    rest of the transaction.
    """
    limit, offset = _pagination()
    where, params = _search()

    total = fetch_one(COUNT_ALL.format(where=where), params)['n']
    rows = fetch_all(SELECT_PAGE.format(where=where), params + (limit, offset))
    return jsonify({
        'tracks': rows, 'total': total, 'limit': limit, 'offset': offset,
    })


@bp.route('/music/tracks/<int:track_id>', methods=['GET'])
def get_track(track_id):
    track = fetch_one(
        f"SELECT {TRACK_COLUMNS} FROM track WHERE id = ? LIMIT 1", (track_id,))
    if track is None:
        abort(404, description=f"no track with id {track_id}")
    return jsonify(track)


@bp.route('/music/tracks/<int:track_id>/stream', methods=['GET'])
def stream_track(track_id):
    """Serve the audio file for a track, supporting range requests.

    The client supplies an id, never a path — the path comes from the row.
    The containment check is defence in depth: the scanner indexes whatever
    is on disk, so a symlink planted in the library would otherwise make this
    an arbitrary-file read. A refusal returns the same 404 as an unknown id,
    so it does not confirm the row exists.
    """
    track = fetch_one("SELECT path FROM track WHERE id = ? LIMIT 1", (track_id,))
    if track is None:
        abort(404, description=f"no track with id {track_id}")

    path = resolve_inside_music_dir(track['path'])
    if path is None:
        abort(404, description=f"no track with id {track_id}")
    if not os.path.isfile(path):
        abort(404, description=f"track {track_id} is indexed but missing on disk")

    # conditional=True makes Flask honour Range and return 206, which is what
    # lets an <audio> element seek. Phase 3 replaces this with X-Accel-Redirect
    # so gunicorn workers are not held open for the length of a track.
    return send_file(path, conditional=True)
