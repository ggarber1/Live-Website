import mariadb
import pytest

import todo.todo
from app import DEFAULT_CORS_ORIGINS, app as flask_app, cors_origins


class TestCorsOrigins:
    def test_defaults_to_the_local_dev_servers(self, monkeypatch):
        monkeypatch.delenv('CORS_ORIGINS', raising=False)

        assert cors_origins() == ['http://localhost:5173', 'http://localhost:3000']

    def test_reads_a_single_origin(self, monkeypatch):
        monkeypatch.setenv('CORS_ORIGINS', 'http://livs-pi.local')

        assert cors_origins() == ['http://livs-pi.local']

    def test_splits_a_comma_separated_list(self, monkeypatch):
        monkeypatch.setenv('CORS_ORIGINS', 'http://a.local,http://b.local')

        assert cors_origins() == ['http://a.local', 'http://b.local']

    def test_tolerates_whitespace_and_trailing_commas(self, monkeypatch):
        monkeypatch.setenv('CORS_ORIGINS', ' http://a.local , http://b.local ,')

        assert cors_origins() == ['http://a.local', 'http://b.local']

    def test_is_never_a_wildcard(self, monkeypatch):
        """A wildcard would let any page on the network call this API."""
        monkeypatch.delenv('CORS_ORIGINS', raising=False)

        assert '*' not in cors_origins()
        assert '*' not in DEFAULT_CORS_ORIGINS


def test_cors_header_reflects_an_allowed_origin(client):
    res = client.get('/', headers={'Origin': 'http://localhost:5173'})

    assert res.headers.get('Access-Control-Allow-Origin') == 'http://localhost:5173'


def test_cors_header_absent_for_a_disallowed_origin(client):
    res = client.get('/', headers={'Origin': 'http://evil.example'})

    assert res.headers.get('Access-Control-Allow-Origin') is None


def test_debug_is_off_by_default():
    """Nothing in the app may hardcode debug on — it's an RCE console."""
    assert flask_app.debug is False
    assert flask_app.config['DEBUG'] is False


@pytest.fixture
def crashing_client(monkeypatch):
    """A client that renders error handlers instead of re-raising."""
    original = flask_app.config.get('PROPAGATE_EXCEPTIONS')
    flask_app.config.update(TESTING=True, PROPAGATE_EXCEPTIONS=False)
    yield flask_app.test_client()
    flask_app.config['PROPAGATE_EXCEPTIONS'] = original


def test_unhandled_error_returns_json_not_html(crashing_client, monkeypatch):
    def boom(query, params=None):
        raise mariadb.Error('connection refused')

    monkeypatch.setattr(todo.todo, 'fetch_all', boom)

    res = crashing_client.get('/todo')

    assert res.status_code == 500
    assert res.mimetype == 'application/json'
    assert res.get_json() == {'error': 'internal server error'}


def test_unhandled_error_does_not_leak_internals(crashing_client, monkeypatch):
    def boom(query, params=None):
        raise mariadb.Error("Access denied for user 'root'@'localhost'")

    monkeypatch.setattr(todo.todo, 'fetch_all', boom)

    res = crashing_client.get('/todo')

    assert 'Access denied' not in res.get_data(as_text=True)


def test_http_errors_still_use_their_own_handler(crashing_client):
    res = crashing_client.get('/nope')

    assert res.status_code == 404
    assert res.mimetype == 'application/json'
    assert 'error' in res.get_json()
