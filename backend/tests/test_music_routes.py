import pytest

TRACK_ROW = {
    'id': 1, 'path': '/tmp/livs-test-music/a.mp3', 'title': 'Space Song',
    'artist': 'Beach House', 'album': 'Depression Cherry', 'track_no': 5,
    'duration_seconds': 301, 'format': 'mp3', 'size_bytes': 7_200_000,
    'mtime_ns': 1_700_000_000_000_000_000, 'created_at': None,
}


def test_list_returns_tracks_with_pagination_envelope(client, reads):
    reads.rows = [TRACK_ROW]
    reads.row = {'n': 1}

    res = client.get('/music/tracks')

    assert res.status_code == 200
    body = res.get_json()
    assert body['tracks'][0]['title'] == 'Space Song'
    assert body['total'] == 1
    assert body['limit'] == 50
    assert body['offset'] == 0


def test_list_envelope_is_an_object_not_a_bare_array(client, reads):
    """Unlike the other services: a library is too big to return whole.

    Asserts the exact key set, not merely `isinstance(dict)` — an error body
    like {"error": ...} is also a dict, so the looser check passed against a
    404 while the route did not yet exist.
    """
    reads.rows = []
    reads.row = {'n': 0}

    res = client.get('/music/tracks')

    assert res.status_code == 200
    assert set(res.get_json()) == {'tracks', 'total', 'limit', 'offset'}


def test_list_runs_a_count_and_a_page_query(client, reads):
    reads.rows = []
    reads.row = {'n': 0}

    client.get('/music/tracks')

    queries = [q for q, _ in reads.queries]
    assert any('COUNT(*)' in q for q in queries)
    assert any('LIMIT ? OFFSET ?' in q for q in queries)


def test_list_orders_deterministically(client, reads):
    """Without an ORDER BY, pagination can repeat or skip rows between pages.

    The sort ends in `id`, the primary key, as a tiebreaker: untagged tracks
    have artist/album/track_no all NULL and can tie on title too (two folders
    each containing "01 - Track.mp3"), and without a unique final key their
    relative order is undefined and can change between two queries.
    """
    reads.rows = []
    reads.row = {'n': 0}

    client.get('/music/tracks')

    page = next(q for q, _ in reads.queries if 'LIMIT' in q)
    assert 'ORDER BY artist, album, track_no, title, id' in page


def test_list_does_not_expose_the_filesystem_path(client, reads):
    """Paths are server-side only — clients address tracks by id.

    Asserted against the query text, because the stubbed reads return a fixed
    row whatever the SELECT asks for. Task 12 checks the real response.
    """
    reads.rows = []
    reads.row = {'n': 0}

    client.get('/music/tracks')

    page = next(q for q, _ in reads.queries if 'LIMIT' in q)
    selected = page.split('FROM')[0]
    assert 'SELECT *' not in selected
    assert 'path' not in selected
    assert 'mtime_ns' not in selected


def test_list_does_not_swallow_query_errors(client, reads):
    """db.py's contract: a broken read fails loudly, not as an empty page."""
    import mariadb

    reads.error = mariadb.Error('table is gone')

    with pytest.raises(mariadb.Error):
        client.get('/music/tracks')
