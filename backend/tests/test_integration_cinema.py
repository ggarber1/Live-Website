"""The cinema proxy against a live Jellyfin holding the three test films.

Deselected by default. Run with:  pytest -m jellyfin
Needs JELLYFIN_* in .env and the films from scripts/make-test-films.sh
indexed (scripts/jellyfin-dev.sh does that).
"""
import os

import pytest
import requests
from dotenv import load_dotenv

from app import app as flask_app

pytestmark = pytest.mark.jellyfin

EXPECTED = {'Paper Moon': 'remux', 'The Lavender Hill Mob': 'transcode', 'Roman Holiday': 'direct'}
DEVICE = 'pytest-cinema'


@pytest.fixture
def live(monkeypatch):
    monkeypatch.undo()
    load_dotenv(override=True)
    url = os.environ.get('JELLYFIN_URL')
    if not url:
        pytest.skip('JELLYFIN_URL not set')
    try:
        requests.get(f'{url}/health', timeout=3).raise_for_status()
    except requests.RequestException as err:
        pytest.skip(f'no Jellyfin at {url}: {err}')
    flask_app.config.update(TESTING=True)
    return flask_app.test_client()


@pytest.fixture
def films(live):
    res = live.get('/api/cinema/films')
    assert res.status_code == 200, res.get_json()
    by_title = {f['title']: f for f in res.get_json()}
    missing = set(EXPECTED) - set(by_title)
    if missing:
        pytest.skip(f'test films not indexed: {sorted(missing)}')
    return by_title


def stop(client, session):
    client.post(f'/api/cinema/play/{session}/stop', json={'device_id': DEVICE})


def test_the_three_films_have_the_expected_playback_kinds(films):
    assert {t: films[t]['playback'] for t in EXPECTED} == EXPECTED
    assert all(films[t]['has_poster'] for t in EXPECTED)


def test_each_film_plays_the_way_its_kind_says(live, films):
    for title, kind in EXPECTED.items():
        res = live.post(f"/api/cinema/films/{films[title]['id']}/play", json={'device_id': DEVICE})
        assert res.status_code == 200, (title, res.get_json())
        body = res.get_json()
        try:
            assert body['kind'] == ('direct' if kind == 'direct' else 'hls'), title
            assert body['url'].startswith('/api/cinema/'), title
            assert 'ApiKey' not in body['url'], title
        finally:
            stop(live, body['play_session_id'])


def test_hls_through_flask_carries_no_key_and_serves_a_segment(live, films):
    res = live.post(f"/api/cinema/films/{films['Paper Moon']['id']}/play", json={'device_id': DEVICE})
    body = res.get_json()
    try:
        master = live.get(body['url'])
        assert master.status_code == 200
        assert master.mimetype == 'application/vnd.apple.mpegurl'
        assert b'ApiKey' not in master.data

        base = body['url'].rsplit('/', 1)[0]
        variant_uri = next(l for l in master.data.decode().splitlines() if l and not l.startswith('#'))
        variant = live.get(f'{base}/{variant_uri}')
        assert variant.status_code == 200
        assert b'ApiKey' not in variant.data

        segment_uri = next(l for l in variant.data.decode().splitlines() if l and not l.startswith('#'))
        segment = live.get(f'{base}/{segment_uri}')
        assert segment.status_code == 200
        assert segment.mimetype == 'video/mp2t'
        assert len(segment.data) > 100_000
    finally:
        stop(live, body['play_session_id'])


def test_direct_play_honours_ranges(live, films):
    res = live.post(f"/api/cinema/films/{films['Roman Holiday']['id']}/play", json={'device_id': DEVICE})
    body = res.get_json()
    try:
        part = live.get(body['url'], headers={'Range': 'bytes=0-99'})
        assert part.status_code == 206
        assert part.headers['Content-Range'].startswith('bytes 0-99/')
        assert part.mimetype == 'video/mp4'
        assert len(part.data) == 100
    finally:
        stop(live, body['play_session_id'])


def test_stop_is_accepted_for_a_session_that_is_already_gone(live):
    res = live.post('/api/cinema/play/00000000000000000000000000000000/stop', json={'device_id': DEVICE})

    assert res.status_code == 204


def test_the_poster_is_a_real_image(live, films):
    res = live.get(f"/api/cinema/films/{films['Paper Moon']['id']}/poster?w=200")

    assert res.status_code == 200
    assert res.mimetype == 'image/jpeg'
    assert res.data[:2] == b'\xff\xd8'
