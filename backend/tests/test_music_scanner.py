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

    def test_insert_carries_every_column_in_order(self, library, fake_db):
        """Positional, not membership: a transposition must fail this."""
        path = write_audio(library, 'song.mp3')
        stat = path.stat()

        scanner.scan_music()

        _, query, params = next(w for w in fake_db['writes'] if w[0] == 'insert')
        assert 'INSERT INTO track' in query
        assert params == (
            str(path), 'song', None, None, None, None,
            'mp3', stat.st_size, stat.st_mtime_ns,
        )

    def test_empty_library_and_empty_table_is_not_an_error(self, library, fake_db):
        counts = scanner.scan_music()

        assert counts == {'added': 0, 'updated': 0, 'unchanged': 0,
                          'removed': 0, 'skipped': 0, 'unreadable_dirs': 0}

    def test_an_unreadable_file_is_skipped_not_fatal(self, library, fake_db, monkeypatch):
        write_audio(library, 'ok.mp3')
        write_audio(library, 'bad.mp3')

        real_stat = os.stat

        def failing_stat(target, *args, **kwargs):
            if str(target).endswith('bad.mp3'):
                raise OSError(13, 'Permission denied')
            return real_stat(target, *args, **kwargs)

        monkeypatch.setattr(scanner.os, 'stat', failing_stat)

        counts = scanner.scan_music()

        assert counts['added'] == 1
        assert counts['skipped'] == 1

    def test_a_rejected_row_skips_only_that_file(self, library, fake_db, monkeypatch):
        """One bad row must not abandon the rest of a large scan."""
        import mariadb

        for name in ('a.mp3', 'b.mp3', 'c.mp3'):
            write_audio(library, name)

        attempts = []

        def flaky_insert(query, params=None):
            attempts.append(params)
            if len(attempts) == 2:
                # What a duplicate path or an out-of-range value actually is.
                raise mariadb.IntegrityError('duplicate key')
            return len(attempts)

        monkeypatch.setattr(scanner, 'insert', flaky_insert)

        counts = scanner.scan_music()

        assert counts['added'] == 2
        assert counts['skipped'] == 1
        assert len(attempts) == 3, "the scan must continue past the failure"

    def test_a_lost_connection_aborts_instead_of_skipping_everything(
            self, library, fake_db, monkeypatch):
        """A dead connection is systemic, not a bad row.

        The connection is cached for the whole app context, so swallowing this
        per file would make every remaining file pay for a tag read and then be
        reported as merely skipped — hiding a dead database behind thousands of
        per-file entries.
        """
        import mariadb

        for name in ('a.mp3', 'b.mp3', 'c.mp3'):
            write_audio(library, name)

        attempts = []

        def dead_insert(query, params=None):
            attempts.append(params)
            raise mariadb.OperationalError('server has gone away')

        monkeypatch.setattr(scanner, 'insert', dead_insert)

        with pytest.raises(mariadb.OperationalError):
            scanner.scan_music()

        assert len(attempts) == 1, "must give up, not try every remaining file"


@pytest.mark.skipif(os.geteuid() == 0, reason="root bypasses permission bits")
def test_an_unreadable_directory_is_counted(library, fake_db):
    """os.walk hides scandir failures, which would make a partial library look
    complete — and Task 5's removal detection would then delete the rows for
    everything underneath it."""
    locked = library / 'Locked'
    locked.mkdir()
    write_audio(library, 'Locked/hidden.mp3')
    write_audio(library, 'ok.mp3')
    os.chmod(locked, 0o000)
    try:
        counts = scanner.scan_music()
    finally:
        os.chmod(locked, 0o755)

    assert counts['unreadable_dirs'] == 1
    assert counts['added'] == 1


class TestScanIsIncremental:
    def test_unchanged_file_is_not_rewritten(self, library, fake_db, monkeypatch):
        path = write_audio(library, 'song.mp3')
        stat = path.stat()
        fake_db['rows'] = [{
            'id': 7, 'path': str(path),
            'size_bytes': stat.st_size, 'mtime_ns': stat.st_mtime_ns,
        }]

        read_calls = []
        monkeypatch.setattr(scanner, 'read_tags',
                            lambda p: read_calls.append(p) or {
                                'title': None, 'artist': None, 'album': None,
                                'track_no': None, 'duration_seconds': None})

        counts = scanner.scan_music()

        assert counts == {'added': 0, 'updated': 0, 'unchanged': 1,
                          'removed': 0, 'skipped': 0, 'unreadable_dirs': 0}
        assert read_calls == [], "tags must not be re-read for unchanged files"
        assert [w for w in fake_db['writes'] if w[0] in ('insert', 'execute')] == []

    def test_changed_mtime_updates_in_place(self, library, fake_db):
        path = write_audio(library, 'song.mp3')
        fake_db['rows'] = [{
            'id': 7, 'path': str(path),
            'size_bytes': path.stat().st_size, 'mtime_ns': 1,
        }]

        counts = scanner.scan_music()

        assert counts['updated'] == 1
        assert counts['added'] == 0
        kinds = [w[0] for w in fake_db['writes']]
        assert 'insert' not in kinds, "must UPDATE, not delete-and-reinsert"
        _, query, params = next(w for w in fake_db['writes'] if w[0] == 'execute')
        assert query.strip().startswith('UPDATE track')
        assert 7 in params

    def test_changed_size_updates_in_place(self, library, fake_db):
        path = write_audio(library, 'song.mp3')
        fake_db['rows'] = [{
            'id': 7, 'path': str(path),
            'size_bytes': 999999, 'mtime_ns': path.stat().st_mtime_ns,
        }]

        assert scanner.scan_music()['updated'] == 1

    def test_an_update_keeps_the_existing_id(self, library, fake_db):
        """Playlists will reference track.id; re-tagging must not renumber.

        Asserts against the UPDATE specifically, and that no DELETE or INSERT
        happened. Matching merely "the first execute call" passes by accident
        under a delete-then-insert implementation, because that DELETE also
        carries id 7 as its only parameter.
        """
        path = write_audio(library, 'song.mp3')
        fake_db['rows'] = [{
            'id': 7, 'path': str(path), 'size_bytes': 1, 'mtime_ns': 1,
        }]

        scanner.scan_music()

        updates = [w for w in fake_db['writes']
                   if w[0] == 'execute' and w[1].strip().startswith('UPDATE track')]
        assert len(updates) == 1, "exactly one UPDATE, no re-creation"
        assert updates[0][2][-1] == 7, "the id must be the WHERE target, unchanged"
        assert not [w for w in fake_db['writes'] if w[0] == 'insert']
        assert not [w for w in fake_db['writes']
                    if w[0] == 'execute' and 'DELETE' in w[1]]

    def test_a_rejected_update_skips_only_that_file(self, library, fake_db, monkeypatch):
        import mariadb

        path = write_audio(library, 'song.mp3')
        fake_db['rows'] = [{
            'id': 7, 'path': str(path), 'size_bytes': 1, 'mtime_ns': 1,
        }]

        def rejecting_execute(query, params=None):
            fake_db['writes'].append(('execute', query, params))
            raise mariadb.DataError('out of range')

        monkeypatch.setattr(scanner, 'execute', rejecting_execute)

        counts = scanner.scan_music()

        assert counts['updated'] == 0
        assert counts['skipped'] == 1


class TestScanRemoves:
    def test_row_whose_file_is_gone_is_deleted(self, library, fake_db):
        kept = write_audio(library, 'kept.mp3')
        fake_db['rows'] = [
            {'id': 1, 'path': str(kept), 'size_bytes': kept.stat().st_size,
             'mtime_ns': kept.stat().st_mtime_ns},
            {'id': 2, 'path': str(library / 'gone.mp3'),
             'size_bytes': 10, 'mtime_ns': 10},
        ]

        counts = scanner.scan_music()

        assert counts['removed'] == 1
        assert counts['unchanged'] == 1
        deletes = [w for w in fake_db['writes']
                   if w[0] == 'execute' and 'DELETE' in w[1]]
        assert len(deletes) == 1
        assert deletes[0][2] == (2,)

    def test_a_file_that_cannot_be_stat_ed_keeps_its_row(self, library, fake_db,
                                                         monkeypatch):
        """It is unreadable, not gone. Deleting the row would renumber it on
        the next successful scan and orphan any reference to the old id."""
        path = write_audio(library, 'song.mp3')
        fake_db['rows'] = [{
            'id': 7, 'path': str(path), 'size_bytes': 1, 'mtime_ns': 1,
        }]

        real_stat = os.stat

        def failing_stat(target, *args, **kwargs):
            if str(target).endswith('song.mp3'):
                raise OSError(13, 'Permission denied')
            return real_stat(target, *args, **kwargs)

        monkeypatch.setattr(scanner.os, 'stat', failing_stat)

        counts = scanner.scan_music()

        assert counts['skipped'] == 1
        assert counts['removed'] == 0, "the file exists; its row must survive"
        deletes = [w for w in fake_db['writes']
                   if w[0] == 'execute' and 'DELETE' in w[1]]
        assert deletes == []


@pytest.mark.skipif(os.geteuid() == 0, reason="root bypasses permission bits")
def test_removal_is_skipped_after_an_incomplete_walk(library, fake_db):
    """An unreadable directory hides its files, which is indistinguishable
    from them being deleted. Removing those rows would be silent data loss."""
    locked = library / 'Locked'
    locked.mkdir()
    hidden = locked / 'hidden.mp3'
    hidden.write_bytes(b'audio bytes')
    kept = write_audio(library, 'ok.mp3')
    fake_db['rows'] = [
        {'id': 1, 'path': str(kept), 'size_bytes': kept.stat().st_size,
         'mtime_ns': kept.stat().st_mtime_ns},
        {'id': 2, 'path': str(hidden), 'size_bytes': 11, 'mtime_ns': 1},
    ]
    os.chmod(locked, 0o000)
    try:
        counts = scanner.scan_music()
    finally:
        os.chmod(locked, 0o755)

    assert counts['unreadable_dirs'] == 1
    assert counts['removed'] == 0
    deletes = [w for w in fake_db['writes']
               if w[0] == 'execute' and 'DELETE' in w[1]]
    assert deletes == [], "must not delete rows it could not verify"
