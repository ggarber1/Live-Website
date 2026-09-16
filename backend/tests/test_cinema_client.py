import pytest
import requests

from cinema import client as client_module
from cinema.client import Jellyfin, JellyfinError, JellyfinNotFound, JellyfinUnavailable


class FakeResponse:
    def __init__(self, status=200, body=None):
        self.status_code = status
        self._body = body

    def json(self):
        return self._body


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setenv('JELLYFIN_URL', 'http://jf.test:8096')
    monkeypatch.setenv('JELLYFIN_API_KEY', 'secret-key')
    monkeypatch.setenv('JELLYFIN_USER_ID', 'user-1')


@pytest.fixture
def http(env, monkeypatch):
    """Record every request the client makes; answer with what the test set."""
    calls = []
    state = {'response': FakeResponse(200, {'ok': True}), 'error': None}

    def fake_request(self, method, url, **kwargs):
        calls.append((method, url, kwargs, dict(self.headers)))
        if state['error']:
            raise state['error']
        return state['response']

    monkeypatch.setattr(requests.Session, 'request', fake_request)
    state['calls'] = calls
    return state


def test_the_auth_header_carries_the_key_and_the_device(http):
    Jellyfin(device_id='browser-abc').get_json('/Items')

    header = http['calls'][0][3]['Authorization']
    assert header == (
        'MediaBrowser Token="secret-key", Client="livs", Device="browser", '
        'DeviceId="browser-abc", Version="1"'
    )


def test_get_json_joins_the_url_and_passes_params(http):
    http['response'] = FakeResponse(200, {'Items': []})

    result = Jellyfin().get_json('/Items', params={'Recursive': 'true'})

    method, url, kwargs, _ = http['calls'][0]
    assert (method, url) == ('GET', 'http://jf.test:8096/Items')
    assert kwargs['params'] == {'Recursive': 'true'}
    assert result == {'Items': []}


def test_post_json_sends_a_body(http):
    Jellyfin().post_json('/Items/1/PlaybackInfo', body={'UserId': 'user-1'})

    method, _, kwargs, _ = http['calls'][0]
    assert method == 'POST'
    assert kwargs['json'] == {'UserId': 'user-1'}


def test_stream_forwards_the_range_and_does_not_buffer(http):
    Jellyfin().stream('/Videos/1/stream', params={'static': 'true'}, range_header='bytes=0-99')

    _, _, kwargs, _ = http['calls'][0]
    assert kwargs['stream'] is True
    assert kwargs['headers'] == {'Range': 'bytes=0-99'}
    assert kwargs['timeout'][1] is None


def test_a_connection_error_is_unavailable(http):
    http['error'] = requests.ConnectionError('refused')

    with pytest.raises(JellyfinUnavailable) as err:
        Jellyfin().get_json('/Items')

    assert 'jf.test' in str(err.value)


def test_a_404_is_not_found(http):
    http['response'] = FakeResponse(404)

    with pytest.raises(JellyfinNotFound):
        Jellyfin().get_json('/Items/nope')


def test_other_errors_carry_the_status(http):
    http['response'] = FakeResponse(500)

    with pytest.raises(JellyfinError) as err:
        Jellyfin().get_json('/Items')

    assert err.value.status == 500


def test_missing_config_fails_before_any_request(monkeypatch, http):
    monkeypatch.delenv('JELLYFIN_API_KEY')

    with pytest.raises(RuntimeError):
        Jellyfin()

    assert http['calls'] == []


def test_the_module_uses_requests_directly():
    """The stubs above patch requests.Session; a different HTTP library would slip past them."""
    assert client_module.requests is requests
