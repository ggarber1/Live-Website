from flask import Blueprint, jsonify, request

from database.db import fetch_all, fetch_one

bp = Blueprint('music', __name__)

DEFAULT_LIMIT = 50
MAX_LIMIT = 200

SELECT_PAGE = (
    "SELECT * FROM track {where} "
    "ORDER BY artist, album, track_no, title LIMIT ? OFFSET ?"
)
COUNT_ALL = "SELECT COUNT(*) AS n FROM track {where}"


@bp.route('/music/tracks', methods=['GET'])
def list_tracks():
    """A page of the library.

    Returns an envelope rather than a bare array — unlike the other services,
    this table holds thousands of rows and the client needs the total to
    paginate.
    """
    limit, offset = DEFAULT_LIMIT, 0
    where, params = '', ()

    total = fetch_one(COUNT_ALL.format(where=where), params)['n']
    rows = fetch_all(SELECT_PAGE.format(where=where), params + (limit, offset))
    return jsonify({
        'tracks': rows, 'total': total, 'limit': limit, 'offset': offset,
    })
