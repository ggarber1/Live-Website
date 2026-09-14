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


class TestPagination:
    def test_limit_and_offset_are_honoured(self, client, reads):
        reads.rows = []
        reads.row = {'n': 0}

        res = client.get('/music/tracks?limit=10&offset=20')

        assert res.get_json()['limit'] == 10
        assert res.get_json()['offset'] == 20
        _, params = next((q, p) for q, p in reads.queries if 'LIMIT' in q)
        assert params[-2:] == (10, 20)

    def test_limit_is_clamped_to_the_maximum(self, client, reads):
        reads.rows = []
        reads.row = {'n': 0}

        res = client.get('/music/tracks?limit=99999')

        assert res.get_json()['limit'] == 200

    def test_exactly_the_maximum_limit_is_allowed(self, client, reads):
        """Clamping is `min(limit, MAX_LIMIT)`, so the boundary itself passes."""
        reads.rows = []
        reads.row = {'n': 0}

        res = client.get('/music/tracks?limit=200')

        assert res.status_code == 200
        assert res.get_json()['limit'] == 200

    @pytest.mark.parametrize('query', [
        'limit=abc', 'offset=abc', 'limit=0', 'limit=-1', 'offset=-1',
    ])
    def test_invalid_pagination_is_a_400(self, client, reads, query):
        reads.rows = []
        reads.row = {'n': 0}

        res = client.get(f'/music/tracks?{query}')

        assert res.status_code == 400
        assert 'error' in res.get_json()


class TestSearch:
    def test_query_filters_on_title_artist_and_album(self, client, reads):
        reads.rows = []
        reads.row = {'n': 0}

        client.get('/music/tracks?q=beach')

        page, params = next((q, p) for q, p in reads.queries if 'LIMIT' in q)
        assert ("WHERE title LIKE ? ESCAPE '!' OR artist LIKE ? ESCAPE '!' "
                "OR album LIKE ? ESCAPE '!'") in page
        assert params[:3] == ('%beach%', '%beach%', '%beach%')

    def test_query_is_parameterised_not_interpolated(self, client, reads):
        """A quote in the search term must not reach the SQL text."""
        reads.rows = []
        reads.row = {'n': 0}

        client.get("/music/tracks?q=%27%3B%20DROP%20TABLE%20track%3B%20--")

        for query, _ in reads.queries:
            assert 'DROP TABLE' not in query

    def test_count_is_filtered_by_the_same_query(self, client, reads):
        reads.rows = []
        reads.row = {'n': 0}

        client.get('/music/tracks?q=beach')

        count, params = next((q, p) for q, p in reads.queries if 'COUNT(*)' in q)
        assert 'WHERE' in count
        assert params == ('%beach%', '%beach%', '%beach%')

    def test_blank_query_is_treated_as_no_filter(self, client, reads):
        reads.rows = []
        reads.row = {'n': 0}

        client.get('/music/tracks?q=%20%20')

        count, params = next((q, p) for q, p in reads.queries if 'COUNT(*)' in q)
        assert 'WHERE' not in count
        assert params == ()

    def test_like_metacharacters_are_escaped(self, client, reads):
        """% and _ are LIKE wildcards, not literals.

        Underscores are extremely common in this library because an untagged
        file's title is its filename, so searching "my_song" must not also
        match "myXsong". A bare % would match the entire library.
        """
        reads.rows = []
        reads.row = {'n': 0}

        client.get('/music/tracks?q=50%25_mix')

        _, params = next((q, p) for q, p in reads.queries if 'COUNT(*)' in q)
        assert params[0] == '%50!%!_mix%'

    def test_the_escape_character_is_itself_escaped(self, client, reads):
        """Pins the replacement order: escaping % and _ first would then
        double-escape the ! characters that escaping introduced."""
        reads.rows = []
        reads.row = {'n': 0}

        client.get('/music/tracks?q=hey%21_you')

        _, params = next((q, p) for q, p in reads.queries if 'COUNT(*)' in q)
        assert params[0] == '%hey!!!_you%'

    def test_a_backslash_is_no_longer_special(self, client, reads):
        """With ESCAPE '!' stated, a backslash in a title is just a character."""
        reads.rows = []
        reads.row = {'n': 0}

        client.get('/music/tracks?q=foo%5Cbar')

        _, params = next((q, p) for q, p in reads.queries if 'COUNT(*)' in q)
        assert params[0] == '%foo\\bar%'
