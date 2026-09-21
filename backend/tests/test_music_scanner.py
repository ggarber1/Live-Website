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
                          'removed': 0, 'skipped': 0, 'skipped_too_long': 0,
                          'skipped_unreadable': 0, 'skipped_rejected': 0,
                          'unreadable_dirs': 0}

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
        assert counts['skipped_unreadable'] == 1

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
        assert counts['skipped_rejected'] == 1
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
                          'removed': 0, 'skipped': 0, 'skipped_too_long': 0,
                          'skipped_unreadable': 0, 'skipped_rejected': 0,
                          'unreadable_dirs': 0}
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
        assert counts['skipped_rejected'] == 1


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
        assert counts['skipped_unreadable'] == 1
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


class TestRemovalAbortRail:
    def test_an_unmounted_drive_aborts_rather_than_deleting_everything(
            self, library, fake_db):
        """An unmounted drive looks exactly like an emptied library."""
        fake_db['rows'] = [
            {'id': i, 'path': str(library / f'{i}.mp3'),
             'size_bytes': 10, 'mtime_ns': 10}
            for i in range(1, 2001)
        ]

        with pytest.raises(scanner.ScanAborted) as err:
            scanner.scan_music()

        assert '2000' in str(err.value)
        assert [w for w in fake_db['writes'] if w[0] == 'execute'] == []

    def test_the_unmounted_message_names_the_root_and_mounting(self, library, fake_db):
        fake_db['rows'] = [{'id': 1, 'path': 'x', 'size_bytes': 1, 'mtime_ns': 1}]

        with pytest.raises(scanner.ScanAborted) as err:
            scanner.scan_music()

        assert str(library) in str(err.value)
        assert 'mount' in str(err.value).lower()

    def test_a_reconfigured_music_dir_does_not_wipe_the_table(self, library, fake_db):
        """The old library still exists, just not under this root. The walk
        succeeds and finds files, so no other guard fires."""
        write_audio(library, 'new.mp3')
        fake_db['rows'] = [
            {'id': i, 'path': f'/somewhere/else/{i}.mp3',
             'size_bytes': 10, 'mtime_ns': 10}
            for i in range(1, 21)
        ]

        with pytest.raises(scanner.ScanAborted) as err:
            scanner.scan_music()

        assert '20' in str(err.value)
        assert 'MUSIC_DIR' in str(err.value)
        deletes = [w for w in fake_db['writes']
                   if w[0] == 'execute' and 'DELETE' in w[1]]
        assert deletes == [], "must refuse before deleting anything"

    def test_force_removals_allows_it(self, library, fake_db):
        """The operator can mean it — a genuine bulk reorganisation."""
        write_audio(library, 'new.mp3')
        fake_db['rows'] = [
            {'id': i, 'path': f'/somewhere/else/{i}.mp3',
             'size_bytes': 10, 'mtime_ns': 10}
            for i in range(1, 21)
        ]

        counts = scanner.scan_music(force_removals=True)

        assert counts['removed'] == 20
        assert counts['added'] == 1

    def test_empty_library_with_empty_table_is_allowed(self, library, fake_db):
        """A first scan of an empty directory is legitimate, not an abort."""
        assert scanner.scan_music()['added'] == 0

    def test_a_small_library_is_not_blocked(self, library, fake_db):
        """Below REMOVAL_FLOOR the proportional check is nuisance: losing a
        handful of rows is recovered by one rescan."""
        kept = write_audio(library, 'kept.mp3')
        fake_db['rows'] = [
            {'id': 1, 'path': str(kept), 'size_bytes': kept.stat().st_size,
             'mtime_ns': kept.stat().st_mtime_ns},
            {'id': 2, 'path': str(library / 'a.mp3'),
             'size_bytes': 1, 'mtime_ns': 1},
            {'id': 3, 'path': str(library / 'b.mp3'),
             'size_bytes': 1, 'mtime_ns': 1},
        ]

        assert scanner.scan_music()['removed'] == 2

    def test_ordinary_attrition_proceeds(self, library, fake_db):
        """Deleting a couple of albums is normal and must not need forcing."""
        rows = []
        for i in range(1, 19):
            path = write_audio(library, f'{i}.mp3')
            rows.append({'id': i, 'path': str(path),
                         'size_bytes': path.stat().st_size,
                         'mtime_ns': path.stat().st_mtime_ns})
        rows += [{'id': 90 + i, 'path': str(library / f'gone{i}.mp3'),
                  'size_bytes': 1, 'mtime_ns': 1} for i in range(2)]
        fake_db['rows'] = rows

        assert scanner.scan_music()['removed'] == 2

    def _rows_for(self, library, present, stale):
        """`present` files on disk plus `stale` rows with no file behind them."""
        rows = []
        for i in range(present):
            path = write_audio(library, f'{i}.mp3')
            rows.append({'id': i, 'path': str(path),
                         'size_bytes': path.stat().st_size,
                         'mtime_ns': path.stat().st_mtime_ns})
        rows += [{'id': 500 + i, 'path': str(library / f'gone{i}.mp3'),
                  'size_bytes': 1, 'mtime_ns': 1} for i in range(stale)]
        return rows

    def test_exactly_the_limit_proceeds(self, library, fake_db):
        """The check is `> REMOVAL_LIMIT`, not `>=`: half is still allowed.

        Ten rows, so REMOVAL_FLOOR does not exempt this — the limit is what
        is being pinned, not the floor.
        """
        fake_db['rows'] = self._rows_for(library, present=5, stale=5)

        assert scanner.scan_music()['removed'] == 5

    def test_one_row_past_the_limit_aborts(self, library, fake_db):
        fake_db['rows'] = self._rows_for(library, present=4, stale=6)

        with pytest.raises(scanner.ScanAborted):
            scanner.scan_music()

    def test_just_below_the_floor_is_exempt(self, library, fake_db):
        """Nine rows, eight of them stale — far past the limit, under the
        floor, so it proceeds. Pins `< REMOVAL_FLOOR` rather than `<=`."""
        fake_db['rows'] = self._rows_for(library, present=1, stale=8)

        assert scanner.scan_music()['removed'] == 8

    @pytest.mark.skipif(os.geteuid() == 0, reason="root bypasses permission bits")
    def test_an_unreadable_directory_still_defers_quietly(self, library, fake_db):
        """Distinct from the abort rail: an incomplete walk is known-incomplete,
        so removal is deferred automatically rather than raising."""
        locked = library / 'Locked'
        locked.mkdir()
        (locked / 'hidden.mp3').write_bytes(b'audio bytes')
        kept = write_audio(library, 'ok.mp3')
        fake_db['rows'] = [
            {'id': i, 'path': f'/somewhere/else/{i}.mp3',
             'size_bytes': 1, 'mtime_ns': 1} for i in range(1, 21)
        ]
        fake_db['rows'].append(
            {'id': 99, 'path': str(kept), 'size_bytes': kept.stat().st_size,
             'mtime_ns': kept.stat().st_mtime_ns})
        os.chmod(locked, 0o000)
        try:
            counts = scanner.scan_music()
        finally:
            os.chmod(locked, 0o755)

        assert counts['removed'] == 0
        assert counts['unreadable_dirs'] == 1


def test_scan_aborted_is_a_runtime_error():
    assert issubclass(scanner.ScanAborted, RuntimeError)


class TestOverLengthPaths:
    def _too_long(self, library):
        """A real file whose path exceeds MAX_PATH_LENGTH.

        Nested rather than one long name: filesystems cap a single component
        at 255 bytes, and the total must stay under PATH_MAX (1024 on macOS).
        """
        deep = library
        for _ in range(5):
            deep = deep / ('d' * 150)
        deep.mkdir(parents=True)
        path = deep / 'song.mp3'
        path.write_bytes(b'audio bytes')
        assert len(str(path)) > scanner.MAX_PATH_LENGTH
        return path

    def _at_length(self, library, total):
        """A real file whose full path is exactly `total` characters.

        Nested until the remaining budget fits inside one path component,
        since filesystems cap a single name at 255 bytes.
        """
        deep = library
        while total - len(str(deep)) - 1 - len('.mp3') > 200:
            deep = deep / ('d' * 100)
        deep.mkdir(parents=True, exist_ok=True)
        stem = 'n' * (total - len(str(deep)) - 1 - len('.mp3'))
        assert stem, "no budget left for a filename; tmp base path too long"
        path = deep / (stem + '.mp3')
        path.write_bytes(b'audio bytes')
        assert len(str(path)) == total
        return path

    def test_a_path_longer_than_the_column_is_skipped(self, library, fake_db):
        self._too_long(library)

        counts = scanner.scan_music()

        assert counts['skipped'] == 1
        assert counts['skipped_too_long'] == 1
        assert counts['added'] == 0
        assert [w for w in fake_db['writes'] if w[0] == 'insert'] == []

    def test_skipping_is_logged(self, library, fake_db, caplog):
        self._too_long(library)

        with caplog.at_level('ERROR'):
            scanner.scan_music()

        assert any('longer than' in record.getMessage()
                   for record in caplog.records)

    def test_a_long_path_does_not_stop_other_files(self, library, fake_db):
        write_audio(library, 'fine.mp3')
        self._too_long(library)

        counts = scanner.scan_music()

        assert counts['added'] == 1
        assert counts['skipped'] == 1

    def test_all_paths_too_long_is_not_mistaken_for_an_unmounted_drive(
            self, library, fake_db):
        """found_any means the walk saw candidates, not that any was stored.

        Pins the ordering: the skip must not run before found_any is set, or
        this reports a missing drive instead of the real problem.
        """
        self._too_long(library)
        fake_db['rows'] = [
            {'id': i, 'path': f'/old/{i}.mp3', 'size_bytes': 1, 'mtime_ns': 1}
            for i in range(1, 21)
        ]

        with pytest.raises(scanner.ScanAborted) as err:
            scanner.scan_music()

        assert 'MUSIC_DIR' in str(err.value)
        assert 'mounted' not in str(err.value).lower()

    def test_a_path_exactly_at_the_limit_is_indexed(self, library, fake_db):
        """The check is `> MAX_PATH_LENGTH`, not `>=`: 768 characters fit.

        768 utf8mb4 characters is exactly the widest full unique index InnoDB
        allows (3072 bytes / 4), so the guard and the column agree precisely.
        """
        self._at_length(library, scanner.MAX_PATH_LENGTH)

        counts = scanner.scan_music()

        assert counts['added'] == 1
        assert counts['skipped'] == 0

    def test_one_character_past_the_limit_is_skipped(self, library, fake_db):
        self._at_length(library, scanner.MAX_PATH_LENGTH + 1)

        counts = scanner.scan_music()

        assert counts['added'] == 0
        assert counts['skipped_too_long'] == 1


COUNTS = {
    'added': 0, 'updated': 0, 'unchanged': 0, 'removed': 0, 'skipped': 0,
    'skipped_too_long': 0, 'skipped_unreadable': 0, 'skipped_rejected': 0,
    'unreadable_dirs': 0,
}


def counts_with(**overrides):
    return {**COUNTS, **overrides}


class TestScanMusicCommand:
    def _run(self, monkeypatch, counts=None, error=None, args=None):
        from app import app as flask_app

        seen = {}

        def fake_scan(force_removals=False, reread=False):
            seen['force_removals'] = force_removals
            if error is not None:
                raise error
            return counts if counts is not None else counts_with()

        monkeypatch.setattr(scanner, 'scan_music', fake_scan)
        result = flask_app.test_cli_runner().invoke(args=['scan-music'] + (args or []))
        return result, seen

    def test_command_is_registered(self):
        from app import app as flask_app

        assert 'scan-music' in flask_app.cli.commands

    def test_reports_the_headline_counts(self, monkeypatch):
        result, _ = self._run(monkeypatch, counts_with(
            added=3, updated=2, unchanged=10, removed=1))

        assert result.exit_code == 0, result.output
        assert 'added 3' in result.output
        assert 'updated 2' in result.output
        assert 'unchanged 10' in result.output
        assert 'removed 1' in result.output

    def test_a_clean_scan_says_nothing_about_skips(self, monkeypatch):
        result, _ = self._run(monkeypatch, counts_with(added=5))

        assert result.exit_code == 0
        assert 'skipped' not in result.output

    def test_skips_are_broken_down_by_reason(self, monkeypatch):
        """One total is not actionable: each reason needs a different fix."""
        result, _ = self._run(monkeypatch, counts_with(
            added=1, skipped=4, skipped_too_long=1,
            skipped_unreadable=2, skipped_rejected=1))

        assert result.exit_code == 0, result.output
        assert 'skipped 4' in result.output
        assert 'too long 1' in result.output
        assert 'unreadable files 2' in result.output
        assert 'rejected 1' in result.output

    def test_skipped_files_alone_still_exit_zero(self, monkeypatch):
        """A permanently bad file must not fail a nightly timer forever."""
        result, _ = self._run(monkeypatch, counts_with(skipped=9,
                                                       skipped_rejected=9))

        assert result.exit_code == 0

    def test_an_abort_exits_non_zero_with_a_clean_message(self, monkeypatch):
        """Wrapped in ClickException, not propagated raw.

        Asserting `'Traceback' not in result.output` would be vacuous:
        CliRunner catches exceptions, so a traceback never reaches output
        either way. What distinguishes the two is `result.exception` — a
        SystemExit when Click handled it, the ScanAborted itself when not —
        and whether the operator sees the message at all.
        """
        result, _ = self._run(
            monkeypatch, error=scanner.ScanAborted('drive not mounted'))

        assert result.exit_code != 0
        assert 'drive not mounted' in result.output
        assert not isinstance(result.exception, scanner.ScanAborted), \
            "must be wrapped in ClickException so the operator sees a message"

    def test_an_incomplete_walk_exits_non_zero(self, monkeypatch):
        """Removal was skipped, so the index is knowingly stale."""
        result, _ = self._run(monkeypatch, counts_with(added=2,
                                                       unreadable_dirs=3))

        assert result.exit_code != 0
        assert '3' in result.output
        assert 'added 2' in result.output, "counts still reported before failing"

    def test_an_incomplete_walk_explains_what_to_do(self, monkeypatch):
        result, _ = self._run(monkeypatch, counts_with(unreadable_dirs=3))

        assert result.exit_code != 0
        assert 'stale rows were left in place' in result.output
        assert 'permissions' in result.output

    def test_skips_and_an_incomplete_walk_report_together(self, monkeypatch):
        """Counts first, then the breakdown, then the failure — losing the
        numbers to an early raise would defeat the per-reason split."""
        result, _ = self._run(monkeypatch, counts_with(
            added=10, skipped=2, skipped_unreadable=2, unreadable_dirs=1))

        assert result.exit_code != 0
        lines = [line for line in result.output.splitlines() if line.strip()]
        assert 'added 10' in lines[0]
        assert 'skipped 2' in lines[1]
        assert 'stale rows were left in place' in lines[-1]

    def test_force_removals_defaults_off(self, monkeypatch):
        _, seen = self._run(monkeypatch)

        assert seen['force_removals'] is False

    def test_force_removals_flag_is_passed_through(self, monkeypatch):
        _, seen = self._run(monkeypatch, args=['--force-removals'])

        assert seen['force_removals'] is True


def test_reread_updates_unchanged_files(library, fake_db, monkeypatch):
    """A better tag reader must be able to reach files already indexed."""
    path = write_audio(library, 'a.mp3')
    stat = os.stat(path)
    fake_db['rows'] = [{'id': 3, 'path': str(path), 'size_bytes': stat.st_size, 'mtime_ns': stat.st_mtime_ns}]

    assert scanner.scan_music()['unchanged'] == 1
    counts = scanner.scan_music(reread=True)

    assert counts['updated'] == 1
    assert any(w[0] == 'execute' and 'UPDATE track' in w[1] for w in fake_db['writes'])
