from flask import Blueprint, jsonify, request

from database.db import fetch_all, fetch_one

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
    limit, offset = DEFAULT_LIMIT, 0
    where, params = '', ()

    total = fetch_one(COUNT_ALL.format(where=where), params)['n']
    rows = fetch_all(SELECT_PAGE.format(where=where), params + (limit, offset))
    return jsonify({
        'tracks': rows, 'total': total, 'limit': limit, 'offset': offset,
    })
