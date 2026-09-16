import pathlib

from cinema.playlist import strip_api_key

FIXTURES = pathlib.Path(__file__).parent / 'fixtures' / 'jellyfin'


def test_removes_the_key_when_first():
    assert strip_api_key('main.m3u8?ApiKey=abc&a=1') == 'main.m3u8?a=1'


def test_removes_the_key_when_in_the_middle():
    assert strip_api_key('main.m3u8?a=1&ApiKey=abc&b=2') == 'main.m3u8?a=1&b=2'


def test_removes_the_key_when_last():
    assert strip_api_key('main.m3u8?a=1&ApiKey=abc') == 'main.m3u8?a=1'


def test_removes_a_lone_key():
    assert strip_api_key('main.m3u8?ApiKey=abc') == 'main.m3u8'


def test_leaves_a_keyless_playlist_byte_identical():
    text = '#EXTM3U\n#EXTINF:10.0,\nhls1/main/0.ts?a=1&b=2\n'

    assert strip_api_key(text) == text


def test_leaves_comment_lines_alone():
    text = '#EXT-X-STREAM-INF:BANDWIDTH=1,CODECS="avc1,mp4a"\n'

    assert strip_api_key(text) == text


def test_the_recorded_master_playlist_comes_out_clean():
    text = (FIXTURES / 'master.m3u8').read_text()
    assert 'ApiKey=' in text, 'fixture should contain the key, or this test proves nothing'

    cleaned = strip_api_key(text)

    assert 'ApiKey' not in cleaned
    assert 'main.m3u8?DeviceId=' in cleaned
    assert cleaned.count('\n') == text.count('\n')


def test_the_recorded_variant_playlist_comes_out_clean():
    text = (FIXTURES / 'main.m3u8').read_text()

    cleaned = strip_api_key(text)

    assert 'ApiKey' not in cleaned
    assert 'hls1/main/0.ts?DeviceId=' in cleaned
