import json
import pathlib

import pytest

import cinema.cinema as routes
from cinema.client import JellyfinError, JellyfinNotFound, JellyfinUnavailable

FIXTURES = pathlib.Path(__file__).parent / 'fixtures' / 'jellyfin'
DIRECT_ID = '19881abd403a19cbb77d6edea8d3a40a'
REMUX_ID = 'a9c6c7c6a3a9e76c9fa4fb4d2864f591'
REMUX_VID = 'a9c6c7c6-a3a9-e76c-9fa4-fb4d2864f591'


def fixture(name):
    return json.loads((FIXTURES / name).read_text())


class FakeUpstream:
    def __init__(self, body=b'', status=200, headers=None):
        self.status_code = status
        self.headers = headers or {}
        self._body = body

    @property
    def text(self):
        return self._body.decode()

    def iter_content(self, size):
        for i in range(0, len(self._body), size):
            yield self._body[i:i + size]


class FakeJellyfin:
    """Records how the routes drive the client; answers from `state`."""
    state = {}

    def __init__(self, device_id='livs-server'):
        self.user_id = 'user-1'
        self.device_id = device_id
        FakeJellyfin.state['devices'].append(device_id)

    def _fail(self):
        if FakeJellyfin.state.get('error'):
            raise FakeJellyfin.state['error']

    def get_json(self, path, params=None):
        self._fail()
        FakeJellyfin.state['calls'].append(('GET', path, None, params))
        if path == '/Items':
            return fixture('items.json')
        # The real server answers 400 to /Items/<id> without a userId.
        if not (params or {}).get('userId'):
            raise JellyfinError(400)
        wanted = path.split('/')[-1]
        for item in fixture('items.json')['Items']:
            if item['Id'] == wanted:
                return item
        raise JellyfinNotFound()

    def post_json(self, path, body=None, params=None):
        self._fail()
        FakeJellyfin.state['calls'].append(('POST', path, body, params))
        return FakeJellyfin.state['playbackinfo']

    def delete(self, path, params=None):
        self._fail()
        FakeJellyfin.state['calls'].append(('DELETE', path, None, params))

    def stream(self, path, params=None, range_header=None):
        self._fail()
        FakeJellyfin.state['calls'].append(('STREAM', path, range_header, params))
        return FakeJellyfin.state['upstream']


@pytest.fixture
def jellyfin(monkeypatch):
    FakeJellyfin.state = {'calls': [], 'devices': [], 'error': None,
                          'playbackinfo': fixture('playbackinfo_remux.json'),
                          'upstream': FakeUpstream()}
    monkeypatch.setattr(routes, 'Jellyfin', FakeJellyfin)
    return FakeJellyfin.state


class TestListing:
    def test_lists_every_film_sorted_by_title(self, client, jellyfin):
        res = client.get('/api/cinema/films')

        assert res.status_code == 200
        films = res.get_json()
        # Jellyfin's SortName drops leading articles, so "The Lavender Hill
        # Mob" files under L. We keep its order rather than re-sorting.
        assert [f['title'] for f in films] == ['The Lavender Hill Mob', 'Paper Moon', 'Roman Holiday']
        assert [f['playback'] for f in films] == ['transcode', 'remux', 'direct']
        _, path, _, params = jellyfin['calls'][0]
        assert path == '/Items'
        assert params['IncludeItemTypes'] == 'Movie'
        assert 'MediaSources' in params['Fields']
        assert params['userId'] == 'user-1', 'without userId there is no UserData, so no resume'

    def test_one_film(self, client, jellyfin):
        res = client.get(f'/api/cinema/films/{DIRECT_ID}')

        assert res.status_code == 200
        assert res.get_json()['title'] == 'Roman Holiday'

    def test_an_unknown_film_is_a_404(self, client, jellyfin):
        res = client.get('/api/cinema/films/00000000000000000000000000000000')

        assert res.status_code == 404
        assert res.get_json() == {'error': 'no such film'}


class TestImages:
    def test_the_poster_is_proxied_and_cacheable(self, client, jellyfin):
        jellyfin['upstream'] = FakeUpstream(b'\xff\xd8jpeg', headers={'Content-Type': 'image/jpeg', 'Content-Length': '6'})

        res = client.get(f'/api/cinema/films/{DIRECT_ID}/poster?w=300')

        assert res.status_code == 200
        assert res.data == b'\xff\xd8jpeg'
        assert res.headers['Content-Type'] == 'image/jpeg'
        assert res.headers['Cache-Control'] == 'public, max-age=86400'
        assert jellyfin['calls'][0][1] == f'/Items/{DIRECT_ID}/Images/Primary'
        assert jellyfin['calls'][0][3] == {'maxWidth': 300}

    def test_the_backdrop_is_the_first_backdrop(self, client, jellyfin):
        jellyfin['upstream'] = FakeUpstream(b'x', headers={'Content-Type': 'image/jpeg'})

        client.get(f'/api/cinema/films/{DIRECT_ID}/backdrop')

        assert jellyfin['calls'][0][1] == f'/Items/{DIRECT_ID}/Images/Backdrop/0'
        assert jellyfin['calls'][0][3] == {'maxWidth': 1280}

    @pytest.mark.parametrize('w', ['0', '2001', 'big', '-1'])
    def test_a_bad_width_is_a_400_before_any_request(self, client, jellyfin, w):
        res = client.get(f'/api/cinema/films/{DIRECT_ID}/poster?w={w}')

        assert res.status_code == 400
        assert jellyfin['calls'] == []

    def test_no_poster_is_a_404(self, client, jellyfin):
        jellyfin['error'] = JellyfinNotFound()

        res = client.get(f'/api/cinema/films/{DIRECT_ID}/poster')

        assert res.status_code == 404


class TestPlay:
    def test_direct_play_points_at_the_file_route(self, client, jellyfin):
        jellyfin['playbackinfo'] = fixture('playbackinfo_direct.json')

        res = client.post(f'/api/cinema/films/{DIRECT_ID}/play', json={'device_id': 'browser-1'})

        assert res.status_code == 200
        body = res.get_json()
        assert body['kind'] == 'direct'
        assert body['url'] == f'/api/cinema/films/{DIRECT_ID}/file?mediaSourceId={DIRECT_ID}'
        assert body['play_session_id'] == jellyfin['playbackinfo']['PlaySessionId']

    def test_remux_points_at_the_hls_proxy_without_the_key(self, client, jellyfin):
        res = client.post(f'/api/cinema/films/{REMUX_ID}/play', json={'device_id': 'browser-1'})

        body = res.get_json()
        assert body['kind'] == 'hls'
        assert body['url'].startswith(f'/api/cinema/videos/{REMUX_VID}/master.m3u8?')
        assert 'ApiKey' not in body['url']
        assert 'PlaySessionId=' in body['url']

    def test_the_browser_device_id_reaches_jellyfin(self, client, jellyfin):
        client.post(f'/api/cinema/films/{REMUX_ID}/play', json={'device_id': 'browser-xyz'})

        assert jellyfin['devices'] == ['browser-xyz']
        _, path, body, _ = jellyfin['calls'][0]
        assert path == f'/Items/{REMUX_ID}/PlaybackInfo'
        assert body['UserId'] == 'user-1'
        assert body['DeviceProfile']['Name'] == 'livs-browser'

    def test_missing_device_id_is_a_400(self, client, jellyfin):
        res = client.post(f'/api/cinema/films/{REMUX_ID}/play', json={})

        assert res.status_code == 400
        assert jellyfin['calls'] == []

    def test_no_media_sources_is_a_502(self, client, jellyfin):
        jellyfin['playbackinfo'] = {'MediaSources': [], 'ErrorCode': 'NoCompatibleStream'}

        res = client.post(f'/api/cinema/films/{REMUX_ID}/play', json={'device_id': 'b'})

        assert res.status_code == 502
        assert 'NoCompatibleStream' in res.get_json()['error']


class TestHls:
    def test_playlists_come_back_without_the_key(self, client, jellyfin):
        jellyfin['upstream'] = FakeUpstream((FIXTURES / 'master.m3u8').read_bytes(),
                                            headers={'Content-Type': PLAYLIST})

        res = client.get(f'/api/cinema/videos/{REMUX_VID}/master.m3u8?DeviceId=b&MediaSourceId={REMUX_ID}')

        assert res.status_code == 200
        assert res.mimetype == 'application/vnd.apple.mpegurl'
        assert b'ApiKey' not in res.data
        assert b'main.m3u8?DeviceId=' in res.data
        _, path, _, _ = jellyfin['calls'][0]
        assert path == f'/videos/{REMUX_VID}/master.m3u8?DeviceId=b&MediaSourceId={REMUX_ID}'

    def test_segments_pass_through_unchanged(self, client, jellyfin):
        jellyfin['upstream'] = FakeUpstream(b'\x47' * 100000, headers={
            'Content-Type': 'video/mp2t', 'Content-Length': '100000', 'Set-Cookie': 'no'})

        res = client.get(f'/api/cinema/videos/{REMUX_VID}/hls1/main/0.ts?DeviceId=b')

        assert res.status_code == 200
        assert res.data == b'\x47' * 100000
        assert res.headers['Content-Type'] == 'video/mp2t'
        assert 'Set-Cookie' not in res.headers


class TestFile:
    def test_range_is_forwarded_and_206_comes_back(self, client, jellyfin):
        jellyfin['upstream'] = FakeUpstream(b'x' * 100, status=206, headers={
            'Content-Type': 'video/mp4', 'Content-Length': '100',
            'Content-Range': 'bytes 0-99/5000', 'Accept-Ranges': 'bytes'})

        res = client.get(f'/api/cinema/films/{DIRECT_ID}/file?mediaSourceId={DIRECT_ID}',
                         headers={'Range': 'bytes=0-99'})

        assert res.status_code == 206
        assert res.headers['Content-Range'] == 'bytes 0-99/5000'
        assert res.headers['Accept-Ranges'] == 'bytes'
        assert res.headers['Content-Type'] == 'video/mp4'
        _, path, range_header, params = jellyfin['calls'][0]
        assert path == f'/Videos/{DIRECT_ID}/stream'
        assert range_header == 'bytes=0-99'
        assert params == {'static': 'true', 'mediaSourceId': DIRECT_ID}


class TestPosition:
    def test_saves_the_position_as_ticks_for_the_user(self, client, jellyfin):
        res = client.post(f'/api/cinema/films/{REMUX_ID}/position', json={'seconds': 754.4})

        assert res.status_code == 204
        assert jellyfin['calls'] == [('POST', f'/UserItems/{REMUX_ID}/UserData',
                                      {'PlaybackPositionTicks': 7_544_000_000, 'Played': False},
                                      {'userId': 'user-1'})]

    def test_finished_marks_played_and_clears_the_position(self, client, jellyfin):
        client.post(f'/api/cinema/films/{REMUX_ID}/position', json={'seconds': 2700, 'finished': True})

        _, _, body, _ = jellyfin['calls'][0]
        assert body == {'PlaybackPositionTicks': 0, 'Played': True}

    @pytest.mark.parametrize('body', [{}, {'seconds': -1}, {'seconds': 'ten'}, {'seconds': True}])
    def test_bad_input_is_a_400_before_any_request(self, client, jellyfin, body):
        res = client.post(f'/api/cinema/films/{REMUX_ID}/position', json=body)

        assert res.status_code == 400
        assert jellyfin['calls'] == []


class TestStop:
    def test_ends_the_encoding_for_that_device_and_session(self, client, jellyfin):
        res = client.post('/api/cinema/play/sess-1/stop', json={'device_id': 'browser-1'})

        assert res.status_code == 204
        assert jellyfin['devices'] == ['browser-1']
        assert jellyfin['calls'] == [('DELETE', '/Videos/ActiveEncodings', None,
                                      {'deviceId': 'browser-1', 'playSessionId': 'sess-1'})]


class TestFailures:
    def test_an_unreachable_jellyfin_is_a_503_not_a_500(self, client, jellyfin):
        jellyfin['error'] = JellyfinUnavailable('cannot reach Jellyfin at http://jf.test')

        res = client.post(f'/api/cinema/films/{REMUX_ID}/play', json={'device_id': 'b'})

        assert res.status_code == 503
        assert res.mimetype == 'application/json'
        assert 'Jellyfin' in res.get_json()['error']

    def test_an_unknown_film_is_a_404(self, client, jellyfin):
        jellyfin['error'] = JellyfinNotFound()

        res = client.post('/api/cinema/films/nope/play', json={'device_id': 'b'})

        assert res.status_code == 404

    def test_a_malformed_id_is_a_404_not_a_500(self, client, jellyfin):
        """Jellyfin answers 400 for an id that is not a GUID; to the browser that is no such film."""
        jellyfin['error'] = JellyfinError(400)

        res = client.post('/api/cinema/films/nope/play', json={'device_id': 'b'})

        assert res.status_code == 404
        assert res.mimetype == 'application/json'

    def test_other_jellyfin_errors_are_a_502(self, client, jellyfin):
        jellyfin['error'] = JellyfinError(500)

        res = client.post(f'/api/cinema/films/{REMUX_ID}/play', json={'device_id': 'b'})

        assert res.status_code == 502
        assert '500' in res.get_json()['error']

    def test_an_unconfigured_cinema_is_a_503_not_a_500(self, client, monkeypatch):
        for name in ('JELLYFIN_URL', 'JELLYFIN_API_KEY', 'JELLYFIN_USER_ID'):
            monkeypatch.delenv(name, raising=False)

        res = client.get('/api/cinema/films')

        assert res.status_code == 503
        assert 'JELLYFIN' in res.get_json()['error']

    def test_the_rest_of_the_site_does_not_need_jellyfin(self, client, monkeypatch, reads):
        """Cinema config is read at use time; /api/todo works with none of it set."""
        for name in ('JELLYFIN_URL', 'JELLYFIN_API_KEY', 'JELLYFIN_USER_ID'):
            monkeypatch.delenv(name, raising=False)

        assert client.get('/api/todo').status_code == 200


PLAYLIST = 'application/vnd.apple.mpegurl'
