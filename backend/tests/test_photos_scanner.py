import datetime
import os

import pytest
from PIL import Image

from app import app as flask_app
from library.rails import REMOVAL_FLOOR, ScanAborted
from photos import scanner


@pytest.fixture
def fake_db(monkeypatch):
    """Stub the scanner's database calls and record every statement."""
    state = {'rows': [], 'writes': [], 'next_id': 1}

    def fake_fetch_all(query, params=None):
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
    monkeypatch.setenv('PHOTOS_DIR', str(tmp_path))
    return tmp_path


def photo(root, relative, taken=None, size=(20, 10)):
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new('RGB', size, 'purple')
    exif = Image.Exif()
    if taken:
        exif.get_ifd(0x8769)[36867] = taken
    img.save(path, 'JPEG', exif=exif.tobytes())
    return path


def indexed(path, size_bytes=None, mtime_ns=None, row_id=1):
    stat = os.stat(path)
    return {'id': row_id, 'path': str(path),
            'size_bytes': size_bytes if size_bytes is not None else stat.st_size,
            'mtime_ns': mtime_ns if mtime_ns is not None else stat.st_mtime_ns}


def inserts(db):
    return [w for w in db['writes'] if w[0] == 'insert']


def test_adds_new_photos_with_their_metadata(library, fake_db):
    photo(library, '2024/07/a.jpg', taken='2024:07:04 12:00:00', size=(40, 30))

    counts = scanner.scan_photos()

    assert counts['added'] == 1
    [(_, query, params)] = inserts(fake_db)
    assert 'INSERT INTO photo' in query
    path, taken, width, height, fmt, size, mtime = params
    assert path.endswith('2024/07/a.jpg')
    assert taken == datetime.datetime(2024, 7, 4, 12, 0, 0)
    assert (width, height, fmt) == (40, 30, 'jpeg')
    assert size == os.stat(path).st_size


def test_unchanged_files_are_not_re_read(library, fake_db, monkeypatch):
    path = photo(library, 'a.jpg')
    fake_db['rows'] = [indexed(path)]
    monkeypatch.setattr(scanner, 'read_image', lambda p: pytest.fail('read_image called'))

    counts = scanner.scan_photos()

    assert counts['unchanged'] == 1
    assert fake_db['writes'] == []


def test_a_changed_file_is_updated_in_place_without_touching_the_caption(library, fake_db):
    path = photo(library, 'a.jpg')
    fake_db['rows'] = [indexed(path, size_bytes=1, row_id=7)]

    counts = scanner.scan_photos()

    assert counts['updated'] == 1
    [(kind, query, params)] = fake_db['writes']
    assert kind == 'execute' and query.strip().startswith('UPDATE photo')
    assert 'caption' not in query
    assert params[-1] == 7


def test_removed_files_are_removed(library, fake_db):
    keep = photo(library, 'keep.jpg')
    fake_db['rows'] = [indexed(keep, row_id=1), {'id': 2, 'path': str(library / 'gone.jpg'),
                                                  'size_bytes': 1, 'mtime_ns': 1}]

    counts = scanner.scan_photos()

    assert counts['removed'] == 1
    assert ('execute', 'DELETE FROM photo WHERE id = ?', (2,)) in fake_db['writes']


def test_a_corrupt_file_is_skipped_and_counted(library, fake_db):
    (library / 'bad.jpg').write_bytes(b'not a jpeg')
    photo(library, 'good.jpg')

    counts = scanner.scan_photos()

    assert counts['added'] == 1
    assert counts['skipped_rejected'] == 1
    assert counts['skipped'] == 1


def test_the_thumbnail_cache_is_ignored(library, fake_db):
    photo(library, '.thumbnails/1-400.jpg')
    photo(library, 'real.jpg')

    counts = scanner.scan_photos()

    assert counts['added'] == 1
    assert not any('.thumbnails' in w[2][0] for w in inserts(fake_db))


def test_zero_files_with_a_populated_table_is_refused(library, fake_db):
    fake_db['rows'] = [{'id': 1, 'path': str(library / 'x.jpg'), 'size_bytes': 1, 'mtime_ns': 1}]

    with pytest.raises(ScanAborted) as err:
        scanner.scan_photos()

    assert 'photo holds 1 rows' in str(err.value)
    assert 'image files' in str(err.value)
    assert not any(w[0] == 'execute' for w in fake_db['writes'])


def test_mass_removal_is_refused_and_names_photos_dir(library, fake_db):
    photo(library, 'only.jpg')
    fake_db['rows'] = [indexed(library / 'only.jpg', row_id=0)] + [
        {'id': i, 'path': str(library / f'gone{i}.jpg'), 'size_bytes': 1, 'mtime_ns': 1}
        for i in range(1, REMOVAL_FLOOR + 1)]

    with pytest.raises(ScanAborted) as err:
        scanner.scan_photos()

    assert 'PHOTOS_DIR' in str(err.value)


def test_force_removals_overrides_the_rail(library, fake_db):
    fake_db['rows'] = [{'id': 1, 'path': str(library / 'x.jpg'), 'size_bytes': 1, 'mtime_ns': 1}]

    counts = scanner.scan_photos(force_removals=True)

    assert counts['removed'] == 1


def test_the_command_prints_counts_and_exits_zero(library, fake_db):
    photo(library, 'a.jpg')

    result = flask_app.test_cli_runner().invoke(scanner.scan_photos_command)

    assert result.exit_code == 0, result.output
    assert 'added 1, updated 0, unchanged 0, removed 0' in result.output


def test_the_command_reports_a_refusal_without_a_traceback(library, fake_db):
    fake_db['rows'] = [{'id': 1, 'path': str(library / 'x.jpg'), 'size_bytes': 1, 'mtime_ns': 1}]

    result = flask_app.test_cli_runner().invoke(scanner.scan_photos_command)

    assert result.exit_code != 0
    assert 'Is the drive mounted?' in result.output
    assert result.exception is None or isinstance(result.exception, SystemExit)
