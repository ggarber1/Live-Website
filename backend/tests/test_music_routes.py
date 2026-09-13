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
    """Without an ORDER BY, pagination can repeat or skip rows between pages."""
    reads.rows = []
    reads.row = {'n': 0}

    client.get('/music/tracks')

    page = next(q for q, _ in reads.queries if 'LIMIT' in q)
    assert 'ORDER BY artist, album, track_no, title' in page
