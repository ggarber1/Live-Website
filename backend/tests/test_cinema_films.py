import json
import pathlib

from cinema.films import to_film

FIXTURES = pathlib.Path(__file__).parent / 'fixtures' / 'jellyfin'


def items():
    return json.loads((FIXTURES / 'items.json').read_text())['Items']


def by_title(title):
    return next(i for i in items() if i['Name'] == title)


def test_maps_the_recorded_remux_film():
    film = to_film(by_title('Paper Moon'))

    assert film == {
        'id': 'a9c6c7c6a3a9e76c9fa4fb4d2864f591',
        'title': 'Paper Moon',
        'year': 1973,
        'runtime_seconds': 45,
        'overview': film['overview'],   # real TMDB text; asserted non-empty below
        'genres': film['genres'],
        'has_poster': True,
        'playback': 'remux',
        'video_codec': 'h264',
        'audio_codec': 'ac3',
        'container': 'mkv',
        'position_seconds': 0,
        'played': False,
    }
    assert film['overview'].startswith('During the Great Depression')
    assert 'Comedy' in film['genres']


def test_each_recorded_film_has_the_expected_playback():
    kinds = {to_film(i)['title']: to_film(i)['playback'] for i in items()}

    assert kinds == {'Paper Moon': 'remux', 'The Lavender Hill Mob': 'transcode',
                     'Roman Holiday': 'direct'}


def test_runtime_ticks_become_seconds():
    assert to_film({'Id': 'x', 'RunTimeTicks': 67_200_000_000})['runtime_seconds'] == 6720


def test_missing_fields_degrade_rather_than_crash():
    film = to_film({'Id': 'x'})

    assert film['title'] == ''
    assert film['year'] is None
    assert film['runtime_seconds'] is None
    assert film['overview'] == ''
    assert film['genres'] == []
    assert film['has_poster'] is False
    assert film['playback'] == 'unknown'
    assert (film['video_codec'], film['audio_codec'], film['container']) == (None, None, None)


def test_user_data_becomes_position_and_played():
    item = {'Id': 'x', 'UserData': {'PlaybackPositionTicks': 754_000_000_000, 'Played': True}}

    film = to_film(item)

    assert film['position_seconds'] == 75400
    assert film['played'] is True


def test_no_user_data_means_unwatched():
    film = to_film({'Id': 'x'})

    assert (film['position_seconds'], film['played']) == (0, False)
