"""Flask serves the built frontend from frontend/dist on the same origin."""
import pytest

import app as app_module


@pytest.fixture
def dist(monkeypatch, tmp_path):
    """A fake build: an index page and one hashed asset."""
    (tmp_path / 'index.html').write_text('<!doctype html><title>Music</title>')
    (tmp_path / 'assets').mkdir()
    (tmp_path / 'assets' / 'app-abc123.js').write_text('console.log(1)')
    monkeypatch.setattr(app_module, 'DIST_DIR', str(tmp_path))
    return tmp_path


def test_root_serves_the_index_page(client, dist):
    res = client.get('/')

    assert res.status_code == 200
    assert res.mimetype == 'text/html'
    assert b'<title>Music</title>' in res.data


def test_built_assets_are_served(client, dist):
    res = client.get('/assets/app-abc123.js')

    assert res.status_code == 200
    assert res.data == b'console.log(1)'


def test_client_routes_fall_back_to_the_index_page(client, dist):
    """/recipes/3 is a page; the router owns it once index.html loads."""
    for path in ('/todo', '/recipes/3', '/journal/new'):
        res = client.get(path)

        assert res.status_code == 200, path
        assert res.mimetype == 'text/html', path
        assert b'<title>Music</title>' in res.data


def test_unknown_api_paths_are_a_json_404_not_the_index_page(client, dist):
    """A typo'd API path must not return HTML 200."""
    res = client.get('/api/music/track')

    assert res.status_code == 404
    assert res.mimetype == 'application/json'


def test_api_routes_are_not_shadowed(client, dist, reads):
    reads.rows = []
    reads.row = {'n': 0}

    res = client.get('/api/music/tracks')

    assert res.status_code == 200
    assert res.mimetype == 'application/json'


def test_non_get_on_an_unknown_path_is_still_a_404(client, dist):
    """A greedy catch-all turned this into 405 and broke the bad-id tests."""
    res = client.put('/api/todo/abc', json={'task': 'x'})

    assert res.status_code == 404


def test_the_fallback_is_get_only(client, dist):
    """A POST to a page path is a mistake and must not get index.html back.

    405 rather than 404: /todo matches the GET-only file rule, and werkzeug
    reports the method mismatch. Either way it is JSON, not the page.
    """
    res = client.post('/todo', json={'task': 'x'})

    assert res.status_code == 405
    assert res.mimetype == 'application/json'


def test_traversal_out_of_dist_is_refused(client, dist):
    """send_from_directory refuses the path, so it falls through to the page."""
    res = client.get('/..%2F..%2Fapp.py')

    assert res.status_code == 200
    assert res.mimetype == 'text/html'
    assert b'import flask' not in res.data


def test_missing_build_is_a_clear_404(client, monkeypatch, tmp_path):
    monkeypatch.setattr(app_module, 'DIST_DIR', str(tmp_path / 'nope'))

    res = client.get('/')

    assert res.status_code == 404
    assert 'npm run build' in res.get_json()['error']
