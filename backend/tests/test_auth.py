import time

import pytest
from werkzeug.security import check_password_hash, generate_password_hash

import auth.auth as auth_module
from app import app as flask_app
from auth.auth import hash_password_command

PASSWORD = 'fern & lavender'


@pytest.fixture(autouse=True)
def password(monkeypatch):
    monkeypatch.setenv('SITE_PASSWORD_HASH', generate_password_hash(PASSWORD))
    monkeypatch.setattr(auth_module, '_failures', {})


def login(client, password=PASSWORD):
    return client.post('/api/auth/login', json={'password': password})


class TestHashPassword:
    def test_prints_a_line_for_dot_env_that_verifies(self):
        result = flask_app.test_cli_runner().invoke(hash_password_command, ['--password', 'pw'])

        assert result.exit_code == 0, result.output
        assert result.output.startswith('SITE_PASSWORD_HASH=')
        assert check_password_hash(result.output.strip().split('=', 1)[1], 'pw')


class TestLogin:
    def test_the_right_password_sets_the_cookie(self, anonymous_client):
        res = login(anonymous_client)

        assert res.status_code == 204
        assert 'livs_session=' in res.headers.get('Set-Cookie', '')
        assert anonymous_client.get('/api/auth/me').get_json() == {'authenticated': True}

    def test_the_wrong_password_is_refused_without_a_cookie(self, anonymous_client):
        res = login(anonymous_client, 'nope')

        assert res.status_code == 401
        assert 'livs_session=' not in res.headers.get('Set-Cookie', '')
        assert anonymous_client.get('/api/auth/me').get_json() == {'authenticated': False}

    def test_five_failures_lock_the_door_for_half_a_minute(self, anonymous_client, monkeypatch):
        clock = {'now': 1000.0}
        monkeypatch.setattr(auth_module.time, 'monotonic', lambda: clock['now'])
        for _ in range(5):
            assert login(anonymous_client, 'nope').status_code == 401

        assert login(anonymous_client).status_code == 429, 'the right password is refused while locked'

        clock['now'] += 31
        assert login(anonymous_client).status_code == 204

    def test_no_hash_configured_fails_closed(self, anonymous_client, monkeypatch):
        monkeypatch.delenv('SITE_PASSWORD_HASH')

        res = login(anonymous_client)

        assert res.status_code == 503
        assert 'hash-password' in res.get_json()['error']
        assert anonymous_client.get('/api/auth/me').get_json() == {'authenticated': False}

    def test_a_non_string_password_is_refused(self, anonymous_client):
        assert login(anonymous_client, 123).status_code == 401

    def test_logout_clears_the_cookie(self, client):
        assert client.get('/api/auth/me').get_json() == {'authenticated': True}

        assert client.post('/api/auth/logout').status_code == 204

        assert client.get('/api/auth/me').get_json() == {'authenticated': False}


class TestGuard:
    def test_the_api_is_refused_without_a_session(self, anonymous_client, reads):
        res = anonymous_client.get('/api/todo')

        assert res.status_code == 401
        assert res.mimetype == 'application/json'

    def test_the_api_works_with_one(self, client, reads):
        assert client.get('/api/todo').status_code == 200

    def test_the_page_shell_and_me_are_open(self, anonymous_client):
        assert anonymous_client.get('/api/auth/me').status_code == 200
        assert anonymous_client.get('/').status_code in (200, 404)  # 404 only if dist is missing
        assert anonymous_client.get('/').mimetype != 'application/json' or anonymous_client.get('/').status_code == 404

    def test_media_routes_are_behind_it_too(self, anonymous_client, reads):
        for url in ('/api/music/tracks/1/stream', '/api/photos/1/file', '/api/cinema/films'):
            assert anonymous_client.get(url).status_code == 401, url


class TestCookieFlags:
    def test_httponly_and_lax_always(self, anonymous_client):
        cookie = login(anonymous_client).headers['Set-Cookie']

        assert 'HttpOnly' in cookie
        assert 'SameSite=Lax' in cookie

    def test_secure_only_behind_https(self, anonymous_client, monkeypatch):
        assert 'Secure' not in login(anonymous_client).headers['Set-Cookie']

        monkeypatch.setitem(flask_app.config, 'SESSION_COOKIE_SECURE', True)
        assert 'Secure' in login(anonymous_client).headers['Set-Cookie']
