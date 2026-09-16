import json
import pathlib

import pytest

import cinema.audit as audit
from app import app as flask_app
from cinema.client import JellyfinUnavailable

FIXTURES = pathlib.Path(__file__).parent / 'fixtures' / 'jellyfin'


class FakeJellyfin:
    error = None

    def __init__(self, device_id=None):
        pass

    def get_json(self, path, params=None):
        if FakeJellyfin.error:
            raise FakeJellyfin.error
        return json.loads((FIXTURES / 'items.json').read_text())


@pytest.fixture
def jellyfin(monkeypatch):
    FakeJellyfin.error = None
    monkeypatch.setattr(audit, 'Jellyfin', FakeJellyfin)
    return FakeJellyfin


def run():
    return flask_app.test_cli_runner().invoke(audit.cinema_audit_command)


def test_lists_only_the_films_that_will_transcode_video(jellyfin):
    result = run()

    assert result.exit_code == 0, result.output
    lines = result.output.strip().splitlines()
    assert lines == [
        'The Lavender Hill Mob (1951)  mkv  hevc/ac3',
        '1 of 3 films will transcode video',
    ]


def test_a_clean_library_says_so(jellyfin, monkeypatch):
    monkeypatch.setattr(audit, 'to_film', lambda item: {**_film(item), 'playback': 'remux'})

    result = run()

    assert result.output.strip() == '0 of 3 films will transcode video'


def test_an_unreachable_jellyfin_is_one_line_and_a_failure(jellyfin):
    jellyfin.error = JellyfinUnavailable('cannot reach Jellyfin at http://jf.test')

    result = run()

    assert result.exit_code == 1
    assert 'cannot reach Jellyfin' in result.output
    assert result.exception is None or isinstance(result.exception, SystemExit)


def test_missing_config_is_one_line_and_a_failure(monkeypatch):
    for name in ('JELLYFIN_URL', 'JELLYFIN_API_KEY', 'JELLYFIN_USER_ID'):
        monkeypatch.delenv(name, raising=False)

    result = run()

    assert result.exit_code == 1
    assert 'JELLYFIN_URL' in result.output


def _film(item):
    from cinema.films import to_film
    return to_film(item)
