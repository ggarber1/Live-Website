"""Round trips for the music library against a real database and real files.

Every other test in this project stubs the database. That is how GET /recipes
once shipped returning 500 for any stored row: MySQL hands JSON columns back
as bytes and no stub ever produced bytes. These tests exist to catch the
things a stub cannot represent — driver types, real column widths, MySQL's
own LIKE semantics, and what the JSON response actually contains.

Deselected by default (see pytest.ini). Run with:  pytest -m integration
"""
import os

import mariadb
import pytest
from dotenv import load_dotenv

from app import app as flask_app
from database import db
from music import scanner
from conftest import logged_in

pytestmark = pytest.mark.integration

load_dotenv()


@pytest.fixture
def real_env(monkeypatch, tmp_path):
    """Drop conftest's fake config, but keep MUSIC_DIR on a temp library."""
    monkeypatch.undo()
    load_dotenv(override=True)
    monkeypatch.setenv('MUSIC_DIR', str(tmp_path))
    return tmp_path


@pytest.fixture
def live_db(real_env):
    """A reachable database whose track table is empty.

    These tests scan into the real track table and wipe it on teardown, and
    the scanner treats rows it did not create as stale. Against an indexed
    library that either aborts every scan or deletes the index, so an occupied
    table is a hard failure, not a skip that a summary line would hide.
    """
    try:
        with flask_app.app_context():
            occupied = db.fetch_one("SELECT COUNT(*) AS n FROM track")['n']
    except (mariadb.Error, RuntimeError) as err:
        pytest.skip(f"no database available: {err}")
    if occupied:
        pytest.fail(
            f"track holds {occupied} rows; the integration suite scans into "
            "and wipes this table. Point DB_NAME at a scratch database or "
            "empty the table first."
        )
    yield
    with flask_app.app_context():
        db.execute("DELETE FROM track")


@pytest.fixture
def library(real_env, live_db):
    return real_env


@pytest.fixture
def client(live_db):
    flask_app.config.update(TESTING=True)
    return logged_in(flask_app.test_client())


def write_audio(root, relative, payload=b'ID3' + b'x' * 2048):
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return path


def scan(**kwargs):
    with flask_app.app_context():
        return scanner.scan_music(**kwargs)


def tracks(client, query=''):
    return client.get('/api/music/tracks' + query).get_json()


# ---------------------------------------------------------------- round trips

def test_scan_indexes_real_files(library, client):
    write_audio(library, 'Artist/Album/01 One.mp3')
    write_audio(library, 'Artist/Album/02 Two.flac')

    counts = scan()

    assert counts['added'] == 2
    body = tracks(client)
    assert body['total'] == 2
    assert {t['format'] for t in body['tracks']} == {'mp3', 'flac'}


def test_untagged_file_gets_a_title_from_its_filename(library, client):
    write_audio(library, 'Mystery Track.mp3')

    scan()

    assert 'Mystery Track' in [t['title'] for t in tracks(client)['tracks']]


def test_rescan_is_incremental(library):
    write_audio(library, 'song.mp3')

    first = scan()
    second = scan()

    assert first['added'] == 1
    assert second['unchanged'] == 1
    assert second['added'] == 0
    assert second['updated'] == 0
    assert second['skipped'] == 0


def test_rescan_after_edit_updates_in_place_keeping_the_id(library, client):
    path = write_audio(library, 'song.mp3')

    scan()
    before = tracks(client)['tracks'][0]['id']

    path.write_bytes(b'ID3' + b'y' * 4096)
    counts = scan()

    after = tracks(client)['tracks'][0]['id']
    assert counts['updated'] == 1
    assert after == before, "ids must survive an update, for playlists later"


def test_rescan_removes_deleted_files(library, client):
    path = write_audio(library, 'gone.mp3')
    write_audio(library, 'kept.mp3')

    scan()
    path.unlink()
    counts = scan()

    assert counts['removed'] == 1
    assert tracks(client)['total'] == 1


def test_scan_aborts_instead_of_emptying_the_library(library, client):
    write_audio(library, 'song.mp3')
    scan()

    for child in library.iterdir():
        child.unlink()

    with pytest.raises(scanner.ScanAborted):
        scan()

    assert tracks(client)['total'] == 1, "the row must survive an aborted scan"


def test_force_removals_lets_the_wipe_through(library, client):
    write_audio(library, 'song.mp3')
    scan()

    for child in library.iterdir():
        child.unlink()

    counts = scan(force_removals=True)

    assert counts['removed'] == 1
    assert tracks(client)['total'] == 0


# ------------------------------------------- things only a real database shows

def test_the_response_never_contains_the_filesystem_path(library, client):
    """Task 9 removed `path` from the SELECT, but the unit tests assert on
    query text only — the stub returns a fixed row whatever is selected. This
    is the check that the real JSON is actually free of it."""
    write_audio(library, 'song.mp3')
    scan()

    body = tracks(client)
    row = body['tracks'][0]

    assert 'path' not in row
    assert 'mtime_ns' not in row
    assert str(library) not in client.get('/api/music/tracks').get_data(as_text=True)

    single = client.get(f"/api/music/tracks/{row['id']}").get_json()
    assert 'path' not in single
    assert 'mtime_ns' not in single


def test_mtime_ns_round_trips_as_an_integer(library):
    """The incremental skip compares row['mtime_ns'] == stat.st_mtime_ns. If
    the driver returned anything that does not compare equal to a Python int,
    every file would look changed on every scan and the optimisation would
    silently never fire. No stub can tell us this."""
    path = write_audio(library, 'song.mp3')
    scan()

    with flask_app.app_context():
        row = db.fetch_one("SELECT size_bytes, mtime_ns FROM track LIMIT 1")

    assert isinstance(row['mtime_ns'], int)
    assert isinstance(row['size_bytes'], int)
    assert row['mtime_ns'] == path.stat().st_mtime_ns
    assert row['size_bytes'] == path.stat().st_size


def test_an_underscore_in_a_title_does_not_match_other_tracks(library, client):
    """MySQL's own LIKE semantics, and the only real test of ESCAPE '!'.
    Filename-derived titles are full of underscores, so `my_song` must not
    also match `myXsong`."""
    write_audio(library, 'my_song.mp3')
    write_audio(library, 'myXsong.mp3')
    scan()

    assert tracks(client)['total'] == 2

    found = tracks(client, '?q=my_song')
    assert found['total'] == 1
    assert found['tracks'][0]['title'] == 'my_song'


def test_a_percent_search_does_not_match_the_whole_library(library, client):
    """An unescaped % would return everything."""
    write_audio(library, '50% off.mp3')
    write_audio(library, 'something else.mp3')
    scan()

    found = tracks(client, '?q=%25')

    assert found['total'] == 1
    assert found['tracks'][0]['title'] == '50% off'


def test_an_over_length_tag_is_stored_truncated_not_rejected(library, client):
    """title is VARCHAR(255) and MySQL is in strict mode, so an unbounded
    value would fail the insert and skip the file. tags.py truncates.

    write_audio's default payload (b'ID3' + garbage) is not a parseable ID3v2
    header, and EasyID3 both reads the existing header before rewriting it and
    (via mutagen.File in read_tags) needs the body to actually sync as MPEG
    audio afterwards. So this writes several repeats of a real, minimal
    128kbps/44.1kHz MPEG frame header instead of arbitrary bytes.
    """
    from mutagen.easyid3 import EasyID3

    frame_header = b'\xff\xfb\x90\x00'
    frame = frame_header + b'\x00' * (417 - len(frame_header))
    path = write_audio(library, 'long.mp3', payload=frame * 10)
    try:
        tag = EasyID3()
        tag['title'] = 'T' * 500
        tag.save(str(path))
    except Exception as err:
        pytest.skip(f"cannot write a real ID3 tag here: {err}")

    counts = scan()

    assert counts['added'] == 1
    assert counts['skipped'] == 0
    title = tracks(client)['tracks'][0]['title']
    assert len(title) == 255


def test_an_over_length_path_is_skipped_not_fatal(library, client):
    """path is VARCHAR(768); a longer one cannot be stored intact."""
    deep = library
    while len(str(deep)) + 200 < scanner.MAX_PATH_LENGTH:
        deep = deep / ('d' * 100)
    deep = deep / ('e' * 200)
    deep.mkdir(parents=True)
    (deep / 'too-long.mp3').write_bytes(b'ID3data')
    assert len(str(deep / 'too-long.mp3')) > scanner.MAX_PATH_LENGTH
    write_audio(library, 'fine.mp3')

    counts = scan()

    assert counts['added'] == 1
    assert counts['skipped_too_long'] == 1
    assert tracks(client)['total'] == 1


def test_unicode_paths_and_search_round_trip(library, client):
    write_audio(library, 'Sigur Rós/Ágætis byrjun/Svefn-g-englar.mp3')

    scan()

    body = tracks(client, '?q=Svefn')
    assert body['total'] == 1
    assert 'Svefn' in body['tracks'][0]['title']


def test_four_byte_characters_survive_the_column(library, client):
    """utf8mb4: an emoji is one character to MySQL and one codepoint to
    Python, which is what makes the 255-character truncation correct."""
    write_audio(library, 'party 🎉 mix.mp3')

    scan()

    titles = [t['title'] for t in tracks(client)['tracks']]
    assert 'party 🎉 mix' in titles


# ------------------------------------------------------------------ streaming

def test_stream_returns_the_bytes_on_disk(library, client):
    write_audio(library, 'song.mp3', payload=b'EXACTBYTES')
    scan()
    track_id = tracks(client)['tracks'][0]['id']

    res = client.get(f'/api/music/tracks/{track_id}/stream')

    assert res.status_code == 200
    assert res.get_data() == b'EXACTBYTES'


def test_stream_honours_a_range_request(library, client):
    write_audio(library, 'song.mp3', payload=b'0123456789')
    scan()
    track_id = tracks(client)['tracks'][0]['id']

    res = client.get(f'/api/music/tracks/{track_id}/stream',
                     headers={'Range': 'bytes=3-6'})

    assert res.status_code == 206
    assert res.get_data() == b'3456'
    assert res.headers['Content-Range'] == 'bytes 3-6/10'


@pytest.mark.parametrize('name,expected', [
    ('song.mp3', 'audio/mpeg'),
    ('song.flac', 'audio/flac'),
    ('song.ogg', 'audio/ogg'),
])
def test_stream_sets_an_audio_content_type_for_a_real_file(library, client,
                                                           name, expected):
    """Registered explicitly in music.py rather than guessed, because the
    host may ship no system mime table."""
    write_audio(library, name)
    scan()
    track_id = tracks(client)['tracks'][0]['id']

    res = client.get(f'/api/music/tracks/{track_id}/stream')

    assert res.mimetype == expected


def test_pagination_walks_the_whole_library_without_gaps(library, client):
    for i in range(5):
        write_audio(library, f'{i:02d}.mp3')
    scan()

    seen = []
    for offset in (0, 2, 4):
        page = tracks(client, f'?limit=2&offset={offset}')
        seen.extend(t['id'] for t in page['tracks'])

    assert page['total'] == 5
    assert len(seen) == 5, "every row appears exactly once across the pages"
    assert len(set(seen)) == 5, "and no row appears twice"
