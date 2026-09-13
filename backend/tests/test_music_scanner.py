import os

import pytest

from music import scanner


@pytest.fixture
def fake_db(monkeypatch):
    """Stub the scanner's database calls and record every statement."""
    state = {'rows': [], 'writes': [], 'next_id': 1}

    def fake_fetch_all(query, params=None):
        state['writes'].append(('select', query, params))
        return list(state['rows'])

    def fake_insert(query, params=None):
        state['writes'].append(('insert', query, params))
        state['next_id'] += 1
        return state['next_id'] - 1

    def fake_execute(query, params=None):
        state['writes'].append(('execute', query, params))
        return 1

    monkeypatch.setattr(scanner, 'fetch_all', fake_fetch_all)
    monkeypatch.setattr(scanner, 'insert', fake_insert)
    monkeypatch.setattr(scanner, 'execute', fake_execute)
    return state


@pytest.fixture
def library(monkeypatch, tmp_path):
    """An empty music root, with MUSIC_DIR pointed at it."""
    monkeypatch.setenv('MUSIC_DIR', str(tmp_path))
    return tmp_path


def write_audio(root, relative):
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b'audio bytes')
    return path


class TestFindAudioFiles:
    def test_finds_files_with_audio_extensions(self, library):
        write_audio(library, 'a/one.mp3')
        write_audio(library, 'b/two.flac')

        found = list(scanner.find_audio_files(str(library)))

        assert len(found) == 2

    def test_ignores_non_audio_files(self, library):
        write_audio(library, 'cover.jpg')
        write_audio(library, 'notes.txt')

        assert list(scanner.find_audio_files(str(library))) == []

    def test_extension_match_is_case_insensitive(self, library):
        write_audio(library, 'LOUD.MP3')

        assert len(list(scanner.find_audio_files(str(library)))) == 1

    def test_recurses(self, library):
        write_audio(library, 'a/b/c/deep.mp3')

        assert len(list(scanner.find_audio_files(str(library)))) == 1

    def test_ignores_appledouble_stubs(self, library):
        """macOS writes ._song.mp3 beside song.mp3; it matches the extension."""
        write_audio(library, '._song.mp3')
        write_audio(library, '.hidden.mp3')

        assert list(scanner.find_audio_files(str(library))) == []

    def test_a_stub_does_not_hide_the_real_file(self, library):
        write_audio(library, 'Album/._song.mp3')
        write_audio(library, 'Album/song.mp3')

        found = list(scanner.find_audio_files(str(library)))

        assert len(found) == 1
        assert os.path.basename(found[0]) == 'song.mp3'

    def test_does_not_descend_into_dot_directories(self, library):
        """.Trashes on a Mac-mounted drive can hold deleted media."""
        write_audio(library, '.Trashes/deleted.mp3')
        write_audio(library, 'Album/kept.mp3')

        found = list(scanner.find_audio_files(str(library)))

        assert len(found) == 1
        assert os.path.basename(found[0]) == 'kept.mp3'


class TestScanAddsFiles:
    def test_inserts_a_row_per_new_file(self, library, fake_db):
        write_audio(library, 'one.mp3')
        write_audio(library, 'two.mp3')

        counts = scanner.scan_music()

        assert counts['added'] == 2
        inserts = [w for w in fake_db['writes'] if w[0] == 'insert']
        assert len(inserts) == 2

    def test_insert_carries_path_format_size_and_mtime(self, library, fake_db):
        path = write_audio(library, 'song.mp3')

        scanner.scan_music()

        _, query, params = next(w for w in fake_db['writes'] if w[0] == 'insert')
        assert 'INSERT INTO track' in query
        assert str(path) in params
        assert 'mp3' in params
        assert path.stat().st_size in params
        assert int(path.stat().st_mtime) in params

    def test_empty_library_and_empty_table_is_not_an_error(self, library, fake_db):
        counts = scanner.scan_music()

        assert counts == {'added': 0, 'updated': 0, 'unchanged': 0,
                          'removed': 0, 'skipped': 0}
