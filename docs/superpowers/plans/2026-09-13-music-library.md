# Music Library (Phase 1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A LAN-only music library: scan an on-disk music directory into the database, then browse, search and play it in a browser.

**Architecture:** Disk is the source of truth; the `track` table is a rebuildable index. A CLI-invoked scanner walks `MUSIC_DIR`, reads tags with mutagen, and upserts rows keyed by path. A Flask blueprint serves a paginated, searchable listing plus a byte-range streaming endpoint. Clients only ever send a track id — never a path.

**Tech Stack:** Python 3.9, Flask 3.1.3, MySQL/MariaDB via the `mariadb` driver, mutagen for tags, pytest.

Spec: `docs/superpowers/specs/2026-09-09-media-library-design.md`

---

## Status — read this before following any task below

| Task | State | Trust the code blocks here? |
| --- | --- | --- |
| 1 `MUSIC_DIR` config | done | **No.** Amended: absolute-path check, falsy-path guard |
| 2 `track` table | done | **No.** Column is `mtime_ns`, not `mtime` |
| 3 Tag reading | done | **No.** Amended twice: numeric bounds, text truncation |
| 4 Scanner, add files | done | **No.** Amended: dotfile skip, `on_error`, per-file write guard |
| 5 Incremental + removal | done | Section rewritten below; code is the source of truth |
| 6 Removal abort rail | done | Section rewritten below; widened to proportional |
| 7 Over-length paths | in progress | Placement instruction below is wrong — see note in that section |
| 8 CLI command | not started | Unverified against the current scanner |
| 9-11 Routes | not started | Believed accurate; independent of the scanner |
| 12 Integration tests | not started | **Stale** — asserts a five-key counts dict; there are six |
| 13 Manual verification | not started | **Stale** — expected CLI output predates `unreadable_dirs` |

Roughly every safety property of the scanner came out of code review rather
than this plan, so for Tasks 1-7 **`backend/music/` and its tests are the
specification**, not the code blocks below. The tasks are left in place for
the reasoning and the TDD sequence, which still hold.

Two conventions established during implementation and worth keeping:

- Clear bytecode between mutation checks: `find . -name __pycache__ -type d
  -not -path "./venv/*" -exec rm -rf {} +`. Python invalidates `.pyc` on
  mtime+size, so two edits inside one second can leave stale bytecode and make
  a restored file look broken.
- Every new guard gets proved load-bearing by breaking it deliberately and
  watching a named test fail.

---

## Conventions in this codebase

Read these before starting; every task depends on them.

- Work from `backend/`. Imports resolve relative to it and there are no `__init__.py` files.
- Run tests with `./venv/bin/python -m pytest tests -q`. Integration tests are deselected by default (`pytest.ini`); run them with `-m integration`.
- Services are `backend/<name>/<name>.py` exposing `bp = Blueprint(...)`, registered in `backend/app.py`.
- Database access is `from database.db import execute, insert, fetch_all, fetch_one`. Never open a connection directly.
- Errors use `abort(404, description=...)`; `app.py` renders them as JSON.
- Tests stub the database per module (see `tests/conftest.py`), because services import names directly rather than the module.
- The suite currently stands at **151 passed, 8 deselected**. Every "Expected:"
  count below assumes the test code in this plan is written exactly as given;
  if you add or merge a test, the totals shift by that much and that is fine.

## File structure

**Create:**

| File | Responsibility |
| --- | --- |
| `backend/music/config.py` | `MUSIC_DIR` lookup and path containment. No DB, no Flask. |
| `backend/music/tags.py` | Read metadata from one audio file. Pure; never raises. |
| `backend/music/scanner.py` | Walk the directory, upsert `track`, enforce the safety rails. |
| `backend/music/music.py` | Blueprint: listing, search, single track, streaming. |
| `backend/tests/test_music_config.py` | Unit tests for config and containment. |
| `backend/tests/test_music_tags.py` | Unit tests for tag reading. |
| `backend/tests/test_music_scanner.py` | Unit tests for the scanner. |
| `backend/tests/test_music_routes.py` | Unit tests for the endpoints. |
| `backend/tests/test_integration_music.py` | Real files + real database round trips. |

**Modify:** `backend/database/db.py` (DDL, CLI), `backend/app.py` (blueprint), `backend/tests/conftest.py` (stub wiring, `MUSIC_DIR`), `backend/tests/test_schema.py` (new table and routes), `backend/requirements.txt`, `backend/.env.example`.

Config is split from the scanner because the streaming route needs containment checking but must not import the scanner. Tags are split from the scanner so tag edge cases can be tested against real files without touching the database.

---

### Task 1: Dependency and `MUSIC_DIR` configuration

**Files:**
- Modify: `backend/requirements.txt`
- Modify: `backend/.env.example`
- Create: `backend/music/config.py`
- Test: `backend/tests/test_music_config.py`

- [ ] **Step 1: Install mutagen and pin it**

```bash
cd backend
./venv/bin/pip install mutagen==1.47.0
```

Set `backend/requirements.txt` to exactly:

```
Flask==3.1.3
flask-cors==6.0.5
mariadb==1.1.14
mutagen==1.47.0
python-dotenv==1.2.1
gunicorn==23.0.0
```

- [ ] **Step 2: Document the variable**

Append to `backend/.env.example`:

```
# Absolute path to the music library root. Required by the music service.
MUSIC_DIR=/mnt/media/music
```

- [ ] **Step 3: Write the failing tests**

Create `backend/tests/test_music_config.py`:

```python
import os

import pytest

from music.config import MAX_PATH_LENGTH, music_dir, resolve_inside_music_dir


class TestMusicDir:
    def test_reads_the_environment_variable(self, monkeypatch, tmp_path):
        monkeypatch.setenv('MUSIC_DIR', str(tmp_path))

        assert music_dir() == os.path.realpath(str(tmp_path))

    def test_missing_variable_names_it(self, monkeypatch):
        monkeypatch.delenv('MUSIC_DIR', raising=False)

        with pytest.raises(RuntimeError) as err:
            music_dir()

        assert 'MUSIC_DIR' in str(err.value)

    def test_blank_variable_is_treated_as_missing(self, monkeypatch):
        monkeypatch.setenv('MUSIC_DIR', '')

        with pytest.raises(RuntimeError):
            music_dir()

    def test_result_is_absolute(self, monkeypatch, tmp_path):
        monkeypatch.setenv('MUSIC_DIR', str(tmp_path))

        assert os.path.isabs(music_dir())


class TestResolveInsideMusicDir:
    def test_accepts_a_file_inside_the_root(self, monkeypatch, tmp_path):
        monkeypatch.setenv('MUSIC_DIR', str(tmp_path))
        target = tmp_path / 'album' / 'song.mp3'
        target.parent.mkdir()
        target.write_bytes(b'x')

        assert resolve_inside_music_dir(str(target)) == os.path.realpath(str(target))

    def test_rejects_a_path_outside_the_root(self, monkeypatch, tmp_path):
        monkeypatch.setenv('MUSIC_DIR', str(tmp_path / 'music'))
        (tmp_path / 'music').mkdir()
        outside = tmp_path / 'secret.txt'
        outside.write_bytes(b'x')

        assert resolve_inside_music_dir(str(outside)) is None

    def test_rejects_traversal(self, monkeypatch, tmp_path):
        monkeypatch.setenv('MUSIC_DIR', str(tmp_path / 'music'))
        (tmp_path / 'music').mkdir()

        assert resolve_inside_music_dir(str(tmp_path / 'music' / '..' / 'etc')) is None

    def test_rejects_a_symlink_escaping_the_root(self, monkeypatch, tmp_path):
        """The scanner indexes whatever is on disk, including planted symlinks."""
        root = tmp_path / 'music'
        root.mkdir()
        secret = tmp_path / 'secret.txt'
        secret.write_bytes(b'x')
        link = root / 'innocent.mp3'
        link.symlink_to(secret)
        monkeypatch.setenv('MUSIC_DIR', str(root))

        assert resolve_inside_music_dir(str(link)) is None

    def test_rejects_a_sibling_directory_with_the_same_prefix(self, monkeypatch, tmp_path):
        """/music must not be treated as containing /music-backup."""
        (tmp_path / 'music').mkdir()
        sibling = tmp_path / 'music-backup'
        sibling.mkdir()
        (sibling / 'song.mp3').write_bytes(b'x')
        monkeypatch.setenv('MUSIC_DIR', str(tmp_path / 'music'))

        assert resolve_inside_music_dir(str(sibling / 'song.mp3')) is None


def test_max_path_length_matches_the_column():
    """track.path is VARCHAR(768); longer paths cannot be stored intact."""
    assert MAX_PATH_LENGTH == 768
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `cd backend && ./venv/bin/python -m pytest tests/test_music_config.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'music.config'`

- [ ] **Step 5: Write the implementation**

Create `backend/music/config.py`:

```python
import os

# track.path is VARCHAR(768) — the longest utf8mb4 column that still fits a full
# UNIQUE index in InnoDB's 3072-byte limit. See the design spec.
MAX_PATH_LENGTH = 768


def music_dir():
    """Absolute path to the music library root, from MUSIC_DIR.

    Read at use time rather than import time, matching db_config(), so a missing
    value is a clear error on first use instead of an ImportError.
    """
    value = os.environ.get('MUSIC_DIR')
    if not value:
        raise RuntimeError(
            "missing environment variable: MUSIC_DIR. "
            "Copy backend/.env.example to backend/.env and fill it in."
        )
    return os.path.realpath(value)


def resolve_inside_music_dir(path):
    """Resolve `path`, returning it only if it stays inside the music root.

    Returns None when it escapes. The scanner indexes whatever is on disk, so a
    symlink planted in the library would otherwise turn the streaming endpoint
    into an arbitrary-file read. Comparison is against root + separator so that
    /music does not appear to contain /music-backup.
    """
    root = music_dir()
    resolved = os.path.realpath(path)
    if resolved != root and not resolved.startswith(root + os.sep):
        return None
    return resolved
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd backend && ./venv/bin/python -m pytest tests/test_music_config.py -q`
Expected: PASS, 10 passed

- [ ] **Step 7: Commit**

```bash
cd backend
git add requirements.txt .env.example music/config.py tests/test_music_config.py
git commit -m "feat(music): add MUSIC_DIR config and path containment"
```

---

### Task 2: The `track` table and schema guard

**Files:**
- Modify: `backend/database/db.py:108-147` (add to `TABLE_DDL`)
- Modify: `backend/tests/test_schema.py`

The existing `test_schema.py` parses column names out of the DDL using a regex of known types. `BIGINT` is not in that list and would not match `INT` (the alternation requires the type to *start* with `INT`), so `size_bytes` and `mtime` would silently go unvalidated. That must be fixed in the same change.

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_schema.py`, after `test_every_table_has_an_id_and_created_at`:

```python
def test_track_table_exists_with_the_columns_the_scanner_needs():
    columns = ddl_columns(TABLE_DDL['track'])

    assert {'id', 'path', 'title', 'artist', 'album', 'track_no',
            'duration_seconds', 'format', 'size_bytes', 'mtime',
            'created_at'} <= columns


def test_track_path_is_uniquely_indexed_in_full():
    """A prefix index would let two long paths collide into one track."""
    ddl = TABLE_DDL['track']

    assert 'VARCHAR(768)' in ddl
    assert 'UNIQUE' in ddl
    assert 'path(' not in ddl
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd backend && ./venv/bin/python -m pytest tests/test_schema.py -q -k track`
Expected: FAIL — `KeyError: 'track'`

- [ ] **Step 3: Add BIGINT to the column-type regex**

In `backend/tests/test_schema.py`, change:

```python
COLUMN_TYPES = 'INT|VARCHAR|TEXT|JSON|TIMESTAMP|DATE'
```

to:

```python
# BIGINT must precede INT: the alternation is ordered, and `INT` would
# otherwise never match the start of `BIGINT`.
COLUMN_TYPES = 'BIGINT|INT|VARCHAR|TEXT|JSON|TIMESTAMP|DATE'
```

- [ ] **Step 4: Add the table**

In `backend/database/db.py`, add to `TABLE_DDL` after the `'blog'` entry:

```python
    # Disk is the source of truth for this table: scan-music rebuilds it, and
    # dropping it loses nothing. path is the natural key and rows are updated in
    # place so ids stay stable for future playlist references.
    # VARCHAR(768) is the longest utf8mb4 column that fits a full UNIQUE index
    # inside InnoDB's 3072-byte limit.
    'track': """
    CREATE TABLE IF NOT EXISTS track (
        id INT AUTO_INCREMENT PRIMARY KEY,
        path VARCHAR(768) NOT NULL UNIQUE,
        title VARCHAR(255),
        artist VARCHAR(255),
        album VARCHAR(255),
        track_no INT,
        duration_seconds INT,
        format VARCHAR(16) NOT NULL,
        size_bytes BIGINT NOT NULL,
        mtime BIGINT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,
```

- [ ] **Step 5: Run the full suite**

Run: `cd backend && ./venv/bin/python -m pytest tests -q`
Expected: PASS — previously 151 passed, now 153 passed, 8 deselected

- [ ] **Step 6: Verify the DDL actually applies to the real database**

Run:

```bash
cd backend && ./venv/bin/flask --app app init-db
```

Expected: `Tables ready: todo, recipes, habits, blog, track`

Then confirm the unique index is on the whole column, not a prefix:

```bash
/opt/homebrew/opt/mysql/bin/mysql -u root -D livs -e "SHOW INDEX FROM track WHERE Key_name != 'PRIMARY';"
```

Expected: one row, `Column_name` = `path`, `Sub_part` = `NULL`. A non-null `Sub_part` means a prefix index and the column is too wide — stop and report.

- [ ] **Step 7: Commit**

```bash
cd backend
git add database/db.py tests/test_schema.py
git commit -m "feat(music): add track table"
```

---

### Task 3: Tag reading

**Files:**
- Create: `backend/music/tags.py`
- Test: `backend/tests/test_music_tags.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_music_tags.py`:

```python
import pytest

from music.tags import AUDIO_EXTENSIONS, read_tags, track_number


class TestTrackNumber:
    @pytest.mark.parametrize('raw,expected', [
        ('3', 3),
        ('03', 3),
        ('3/12', 3),
        (3, 3),
        (None, None),
        ('', None),
        ('A', None),
        ('/12', None),
    ])
    def test_parses_what_it_can(self, raw, expected):
        assert track_number(raw) == expected


class TestReadTags:
    def test_unreadable_file_falls_back_to_the_filename(self, tmp_path):
        path = tmp_path / 'Some Song.mp3'
        path.write_bytes(b'not really an mp3')

        tags = read_tags(str(path))

        assert tags['title'] == 'Some Song'
        assert tags['artist'] is None
        assert tags['album'] is None
        assert tags['track_no'] is None
        assert tags['duration_seconds'] is None

    def test_missing_file_does_not_raise(self, tmp_path):
        tags = read_tags(str(tmp_path / 'nope.mp3'))

        assert tags['title'] == 'nope'

    def test_returns_every_expected_key(self, tmp_path):
        path = tmp_path / 'x.flac'
        path.write_bytes(b'bogus')

        assert set(read_tags(str(path))) == {
            'title', 'artist', 'album', 'track_no', 'duration_seconds',
        }


def test_audio_extensions_are_lowercase_with_dots():
    for ext in AUDIO_EXTENSIONS:
        assert ext.startswith('.')
        assert ext == ext.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && ./venv/bin/python -m pytest tests/test_music_tags.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'music.tags'`

- [ ] **Step 3: Write the implementation**

Create `backend/music/tags.py`:

```python
import logging
import os

import mutagen

AUDIO_EXTENSIONS = ('.mp3', '.flac', '.m4a', '.ogg', '.wav')

logger = logging.getLogger(__name__)


def track_number(raw):
    """Parse a track number, which arrives as "3", "03" or "3/12"."""
    if raw is None:
        return None
    text = str(raw).split('/')[0].strip()
    try:
        return int(text)
    except ValueError:
        return None


def _first(audio, key):
    """Easy-mode tags are lists; take the first non-empty value."""
    values = audio.get(key) or []
    for value in values:
        if value and str(value).strip():
            return str(value).strip()
    return None


def read_tags(path):
    """Metadata for one audio file. Never raises.

    A corrupt or untagged file must still be indexed and playable, so failures
    degrade to nulls with the filename as the title. mutagen raises a wide
    variety of exception types across formats, hence the broad except.
    """
    audio = None
    try:
        audio = mutagen.File(path, easy=True)
    except Exception as err:
        logger.warning("could not read tags from %s: %s", path, err)

    title = artist = album = None
    number = duration = None

    if audio is not None:
        title = _first(audio, 'title')
        artist = _first(audio, 'artist')
        album = _first(audio, 'album')
        number = track_number(_first(audio, 'tracknumber'))
        length = getattr(getattr(audio, 'info', None), 'length', None)
        if length:
            duration = int(length)

    return {
        'title': title or os.path.splitext(os.path.basename(path))[0],
        'artist': artist,
        'album': album,
        'track_no': number,
        'duration_seconds': duration,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && ./venv/bin/python -m pytest tests/test_music_tags.py -q`
Expected: PASS, 12 passed

- [ ] **Step 5: Commit**

```bash
cd backend
git add music/tags.py tests/test_music_tags.py
git commit -m "feat(music): read audio tags with filename fallback"
```

---

### Task 4: Scanner — index new files

**Files:**
- Create: `backend/music/scanner.py`
- Test: `backend/tests/test_music_scanner.py`

The scanner talks to the database, so its tests stub `execute`, `insert` and `fetch_all` on the `music.scanner` module directly — not via `conftest.py`'s `writes`/`reads` fixtures, which only cover route modules.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_music_scanner.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && ./venv/bin/python -m pytest tests/test_music_scanner.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'music.scanner'`

- [ ] **Step 3: Write the implementation**

Create `backend/music/scanner.py`:

```python
import logging
import os

from database.db import execute, fetch_all, insert
from music.config import MAX_PATH_LENGTH, music_dir
from music.tags import AUDIO_EXTENSIONS, read_tags

logger = logging.getLogger(__name__)

INSERT_TRACK = """
INSERT INTO track
    (path, title, artist, album, track_no, duration_seconds,
     format, size_bytes, mtime)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
"""


def find_audio_files(root):
    """Yield every audio file under `root`, sorted within each directory."""
    for dirpath, _dirnames, filenames in os.walk(root):
        for name in sorted(filenames):
            if name.lower().endswith(AUDIO_EXTENSIONS):
                yield os.path.join(dirpath, name)


def _file_format(path):
    return os.path.splitext(path)[1].lstrip('.').lower()


def _insert_track(path, tags, stat):
    insert(INSERT_TRACK, (
        path, tags['title'], tags['artist'], tags['album'],
        tags['track_no'], tags['duration_seconds'],
        _file_format(path), stat.st_size, int(stat.st_mtime),
    ))


def scan_music():
    """Index MUSIC_DIR into the track table.

    Returns counts of added, updated, unchanged, removed and skipped files.
    """
    root = music_dir()
    counts = {'added': 0, 'updated': 0, 'unchanged': 0,
              'removed': 0, 'skipped': 0}

    for path in find_audio_files(root):
        try:
            stat = os.stat(path)
        except OSError as err:
            logger.error("skipping unreadable file %s: %s", path, err)
            counts['skipped'] += 1
            continue
        _insert_track(path, read_tags(path), stat)
        counts['added'] += 1

    return counts
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && ./venv/bin/python -m pytest tests/test_music_scanner.py -q`
Expected: PASS, 7 passed

- [ ] **Step 5: Commit**

```bash
cd backend
git add music/scanner.py tests/test_music_scanner.py
git commit -m "feat(music): scan a directory into the track table"
```

---

### Task 5: Scanner — incremental skip and removal — DONE, superseded

Implemented in `eacabdf`, `17246a8`, `03902c7`. **The original text of this
task is not what was built** and has been removed to stop it misleading
readers. `backend/music/scanner.py` is the source of truth.

What it specified that is now wrong:

- A `mtime` column and `int(stat.st_mtime)`. The column is `mtime_ns`, holding
  `stat.st_mtime_ns`. Whole seconds would treat a file re-tagged twice inside
  one second as unchanged, and fixing that after data exists is a migration.
- A five-key counts dict. There are six; `unreadable_dirs` was added in Task 4.
- `find_audio_files(root)`. It takes `on_error` so unreadable directories are
  reported rather than silently dropped.

What review added beyond the original scope:

- **Removal is skipped entirely when the walk was incomplete.** An unreadable
  directory hides its files, which is indistinguishable from deletion. Without
  this, one permission glitch deletes every row beneath that directory.
- **`seen.add(path)` happens before `os.stat`, not after.** Placed after, a
  file that exists but cannot be read gets its row deleted — and because it is
  deleted rather than skipped, the next successful scan reinserts it with a new
  id, breaking the id stability this task exists to provide.
- Writes are wrapped in `except (mariadb.IntegrityError, mariadb.DataError)`,
  not `mariadb.Error`. A lost connection must propagate rather than being
  miscounted as thousands of skipped files.

---

### Task 6: Scanner — the removal abort rail — DONE, superseded

Implemented in `2e63fc2`, `7da9e61`. Original text removed for the same reason.

It specified only a zero-files guard. That catches an unmounted drive and
nothing else. Review established that several ordinary events make every
stored path invisible while the walk succeeds perfectly: `MUSIC_DIR` changed
to another readable directory, the same directory spelled differently (paths
are stored resolved, since `music_dir()` calls `realpath()`), or a directory
renamed to start with a dot.

So the rail is proportional: a scan may not delete more than `REMOVAL_LIMIT`
(0.5) of the table, with zero-files as the limiting case. Libraries under
`REMOVAL_FLOOR` (10) rows are exempt, since the check is nuisance at that size.
`scan_music(force_removals=True)` overrides it.

The asymmetry with the unreadable-directory case is deliberate and tested both
ways: an incomplete walk defers removal silently, because we know it was
incomplete; a mass removal after a complete walk raises, because it only looks
destructive and a human should decide.

---

### Task 7: Scanner — over-length paths

**Files:**
- Modify: `backend/music/scanner.py`
- Test: `backend/tests/test_music_scanner.py`

MySQL outside strict mode truncates an over-length value, producing a stored path that cannot stream. Skip and log instead.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_music_scanner.py`:

```python
class TestOverLengthPaths:
    def test_path_longer_than_the_column_is_skipped(self, library, fake_db, caplog):
        # Nested directories, since most filesystems cap a single name at 255.
        deep = library
        for _ in range(6):
            deep = deep / ('d' * 150)
        deep.mkdir(parents=True)
        path = deep / 'song.mp3'
        path.write_bytes(b'audio bytes')
        assert len(str(path)) > scanner.MAX_PATH_LENGTH

        counts = scanner.scan_music()

        assert counts['skipped'] == 1
        assert counts['added'] == 0
        assert [w for w in fake_db['writes'] if w[0] == 'insert'] == []

    def test_skipping_is_logged(self, library, fake_db, caplog):
        deep = library
        for _ in range(6):
            deep = deep / ('d' * 150)
        deep.mkdir(parents=True)
        (deep / 'song.mp3').write_bytes(b'audio bytes')

        with caplog.at_level('ERROR'):
            scanner.scan_music()

        assert any('longer than' in r.message or 'longer than' in r.getMessage()
                   for r in caplog.records)

    def test_a_long_path_does_not_stop_other_files(self, library, fake_db):
        write_audio(library, 'fine.mp3')
        deep = library
        for _ in range(6):
            deep = deep / ('d' * 150)
        deep.mkdir(parents=True)
        (deep / 'too-long.mp3').write_bytes(b'audio bytes')

        counts = scanner.scan_music()

        assert counts['added'] == 1
        assert counts['skipped'] == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && ./venv/bin/python -m pytest tests/test_music_scanner.py -q -k OverLength`
Expected: FAIL — `assert 0 == 1` on `counts['skipped']`; the long file is inserted.

- [ ] **Step 3: Write the implementation**

In `backend/music/scanner.py`, inside the `for path in found:` loop, add as the
first statements in the body — before the `os.stat` call:

```python
        if len(path) > MAX_PATH_LENGTH:
            logger.error(
                "skipping path longer than %d characters (track.path cannot "
                "store it intact): %s", MAX_PATH_LENGTH, path)
            counts['skipped'] += 1
            continue
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && ./venv/bin/python -m pytest tests/test_music_scanner.py -q`
Expected: PASS, 19 passed

- [ ] **Step 5: Commit**

```bash
cd backend
git add music/scanner.py tests/test_music_scanner.py
git commit -m "feat(music): skip paths too long for the column"
```

---

### Task 8: The `scan-music` CLI command

**Files:**
- Modify: `backend/music/scanner.py`
- Modify: `backend/app.py`
- Test: `backend/tests/test_music_scanner.py`

A full scan takes minutes and would pin a gunicorn worker, so it is never reachable over HTTP. This mirrors `init-db` in `database/db.py:159-164`.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_music_scanner.py`:

```python
class TestScanMusicCommand:
    def test_command_is_registered(self):
        from app import app as flask_app

        assert 'scan-music' in flask_app.cli.commands

    def test_command_runs_the_scan_and_reports_counts(self, monkeypatch):
        from app import app as flask_app

        monkeypatch.setattr(scanner, 'scan_music', lambda: {
            'added': 3, 'updated': 2, 'unchanged': 10,
            'removed': 1, 'skipped': 0,
        })

        result = flask_app.test_cli_runner().invoke(args=['scan-music'])

        assert result.exit_code == 0, result.output
        assert 'added 3' in result.output
        assert 'removed 1' in result.output

    def test_command_reports_an_abort_without_a_traceback(self, monkeypatch):
        from app import app as flask_app

        def boom():
            raise scanner.ScanAborted('drive not mounted')

        monkeypatch.setattr(scanner, 'scan_music', boom)

        result = flask_app.test_cli_runner().invoke(args=['scan-music'])

        assert result.exit_code != 0
        assert 'drive not mounted' in result.output
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && ./venv/bin/python -m pytest tests/test_music_scanner.py -q -k Command`
Expected: FAIL — `assert 'scan-music' in flask_app.cli.commands`

- [ ] **Step 3: Write the implementation**

In `backend/music/scanner.py`, add the imports at the top:

```python
import click
from flask.cli import with_appcontext
```

and append at the end of the file:

```python
@click.command('scan-music')
@with_appcontext
def scan_music_command():
    """Index MUSIC_DIR into the track table."""
    try:
        counts = scan_music()
    except ScanAborted as err:
        raise click.ClickException(str(err))
    click.echo(
        "added {added}, updated {updated}, unchanged {unchanged}, "
        "removed {removed}, skipped {skipped}".format(**counts)
    )
```

`click.ClickException` prints the message and exits non-zero without a traceback,
which is the right shape for an operator running this from a timer.

In `backend/app.py`, register it next to the blueprint imports. Add to the import
block:

```python
from music.scanner import scan_music_command
```

and after `db.init_app(app)`:

```python
app.cli.add_command(scan_music_command)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && ./venv/bin/python -m pytest tests/test_music_scanner.py -q`
Expected: PASS, 22 passed

- [ ] **Step 5: Verify it appears in the real CLI**

Run: `cd backend && ./venv/bin/flask --app app --help`
Expected: `scan-music  Index MUSIC_DIR into the track table.` in the command list

- [ ] **Step 6: Commit**

```bash
cd backend
git add music/scanner.py app.py tests/test_music_scanner.py
git commit -m "feat(music): add scan-music CLI command"
```

---

### Task 9: Blueprint and track listing

**Files:**
- Create: `backend/music/music.py`
- Modify: `backend/app.py`
- Modify: `backend/tests/conftest.py`
- Test: `backend/tests/test_music_routes.py`

`conftest.py` must learn about the new module in three places: `SERVICE_MODULES`
(so `writes`/`reads` stub it), and `db_env` (so `MUSIC_DIR` is always set, as the
streaming route reads it).

- [ ] **Step 1: Wire the new module into conftest**

In `backend/tests/conftest.py`, add the import alongside the others:

```python
import music.music
```

and extend the tuple:

```python
SERVICE_MODULES = (blog.blog, habits.habits, music.music,
                   recipes.recipes, todo.todo)
```

Add to the `db_env` fixture body, so no test depends on a real music directory:

```python
    monkeypatch.setenv('MUSIC_DIR', '/tmp/livs-test-music')
```

The `reads` fixture's `fake_fetch_one` returns `fake.row` for every query. The
listing endpoint runs a `COUNT(*)` through `fetch_one`, so tests that exercise it
set `reads.row = {'n': <total>}`.

- [ ] **Step 2: Write the failing tests**

Create `backend/tests/test_music_routes.py`:

```python
import pytest

TRACK_ROW = {
    'id': 1, 'path': '/tmp/livs-test-music/a.mp3', 'title': 'Space Song',
    'artist': 'Beach House', 'album': 'Depression Cherry', 'track_no': 5,
    'duration_seconds': 301, 'format': 'mp3', 'size_bytes': 7_200_000,
    'mtime': 1_700_000_000, 'created_at': None,
}


def test_list_returns_tracks_with_pagination_envelope(client, reads):
    reads.rows = [TRACK_ROW]
    reads.row = {'n': 1}

    res = client.get('/music/tracks')

    assert res.status_code == 200
    body = res.get_json()
    assert body['tracks'][0]['title'] == 'Space Song'
    assert body['total'] == 1
    assert body['limit'] == 50
    assert body['offset'] == 0


def test_list_envelope_is_an_object_not_a_bare_array(client, reads):
    """Unlike the other services: a library is too big to return whole."""
    reads.rows = []
    reads.row = {'n': 0}

    assert isinstance(client.get('/music/tracks').get_json(), dict)


def test_list_runs_a_count_and_a_page_query(client, reads):
    reads.rows = []
    reads.row = {'n': 0}

    client.get('/music/tracks')

    queries = [q for q, _ in reads.queries]
    assert any('COUNT(*)' in q for q in queries)
    assert any('LIMIT ? OFFSET ?' in q for q in queries)


def test_list_orders_deterministically(client, reads):
    reads.rows = []
    reads.row = {'n': 0}

    client.get('/music/tracks')

    page = next(q for q, _ in reads.queries if 'LIMIT' in q)
    assert 'ORDER BY artist, album, track_no, title' in page
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd backend && ./venv/bin/python -m pytest tests/test_music_routes.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'music.music'`

- [ ] **Step 4: Write the implementation**

Create `backend/music/music.py`:

```python
from flask import Blueprint, jsonify, request

from database.db import fetch_all, fetch_one

bp = Blueprint('music', __name__)

DEFAULT_LIMIT = 50
MAX_LIMIT = 200

SELECT_PAGE = (
    "SELECT * FROM track {where} "
    "ORDER BY artist, album, track_no, title LIMIT ? OFFSET ?"
)
COUNT_ALL = "SELECT COUNT(*) AS n FROM track {where}"


@bp.route('/music/tracks', methods=['GET'])
def list_tracks():
    """A page of the library.

    Returns an envelope rather than a bare array — unlike the other services,
    this table holds thousands of rows and the client needs the total to
    paginate.
    """
    limit, offset = DEFAULT_LIMIT, 0
    where, params = '', ()

    total = fetch_one(COUNT_ALL.format(where=where), params)['n']
    rows = fetch_all(SELECT_PAGE.format(where=where), params + (limit, offset))
    return jsonify({
        'tracks': rows, 'total': total, 'limit': limit, 'offset': offset,
    })
```

`where` is interpolated with `.format`, but it only ever holds a fixed literal
defined in this file — every value from the client is a bound `?` parameter.
Task 10 adds the search clause the same way.

In `backend/app.py`, add to the import block:

```python
from music.music import bp as music_bp
```

and register it with the others:

```python
app.register_blueprint(music_bp)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && ./venv/bin/python -m pytest tests/test_music_routes.py -q`
Expected: PASS, 4 passed

- [ ] **Step 6: Run the full suite**

Run: `cd backend && ./venv/bin/python -m pytest tests -q`
Expected: PASS, 201 passed, 8 deselected

- [ ] **Step 7: Commit**

```bash
cd backend
git add music/music.py app.py tests/conftest.py tests/test_music_routes.py
git commit -m "feat(music): add paginated track listing"
```

---

### Task 10: Search and pagination parameters

**Files:**
- Modify: `backend/music/music.py`
- Test: `backend/tests/test_music_routes.py`

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_music_routes.py`:

```python
class TestPagination:
    def test_limit_and_offset_are_honoured(self, client, reads):
        reads.rows = []
        reads.row = {'n': 0}

        res = client.get('/music/tracks?limit=10&offset=20')

        assert res.get_json()['limit'] == 10
        assert res.get_json()['offset'] == 20
        _, params = next((q, p) for q, p in reads.queries if 'LIMIT' in q)
        assert params[-2:] == (10, 20)

    def test_limit_is_clamped_to_the_maximum(self, client, reads):
        reads.rows = []
        reads.row = {'n': 0}

        res = client.get('/music/tracks?limit=99999')

        assert res.get_json()['limit'] == 200

    @pytest.mark.parametrize('query', [
        'limit=abc', 'offset=abc', 'limit=0', 'limit=-1', 'offset=-1',
    ])
    def test_invalid_pagination_is_a_400(self, client, reads, query):
        reads.rows = []
        reads.row = {'n': 0}

        res = client.get(f'/music/tracks?{query}')

        assert res.status_code == 400
        assert 'error' in res.get_json()


class TestSearch:
    def test_query_filters_on_title_artist_and_album(self, client, reads):
        reads.rows = []
        reads.row = {'n': 0}

        client.get('/music/tracks?q=beach')

        page, params = next((q, p) for q, p in reads.queries if 'LIMIT' in q)
        assert 'WHERE title LIKE ? OR artist LIKE ? OR album LIKE ?' in page
        assert params[:3] == ('%beach%', '%beach%', '%beach%')

    def test_query_is_parameterised_not_interpolated(self, client, reads):
        """A quote in the search term must not reach the SQL text."""
        reads.rows = []
        reads.row = {'n': 0}

        client.get("/music/tracks?q=%27%3B%20DROP%20TABLE%20track%3B%20--")

        for query, _ in reads.queries:
            assert 'DROP TABLE' not in query

    def test_count_is_filtered_by_the_same_query(self, client, reads):
        reads.rows = []
        reads.row = {'n': 0}

        client.get('/music/tracks?q=beach')

        count, params = next((q, p) for q, p in reads.queries if 'COUNT(*)' in q)
        assert 'WHERE' in count
        assert params == ('%beach%', '%beach%', '%beach%')

    def test_blank_query_is_treated_as_no_filter(self, client, reads):
        reads.rows = []
        reads.row = {'n': 0}

        client.get('/music/tracks?q=%20%20')

        count, params = next((q, p) for q, p in reads.queries if 'COUNT(*)' in q)
        assert 'WHERE' not in count
        assert params == ()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && ./venv/bin/python -m pytest tests/test_music_routes.py -q -k "Pagination or Search"`
Expected: FAIL — `assert 50 == 10`; parameters are ignored.

- [ ] **Step 3: Write the implementation**

In `backend/music/music.py`, add `abort` to the Flask import:

```python
from flask import Blueprint, abort, jsonify, request
```

Add the two helpers above `list_tracks`:

```python
SEARCH_WHERE = "WHERE title LIKE ? OR artist LIKE ? OR album LIKE ?"


def _positive_int(name, default):
    raw = request.args.get(name)
    if raw is None or raw == '':
        return default
    try:
        value = int(raw)
    except ValueError:
        abort(400, description=f"{name} must be an integer")
    if value < 0:
        abort(400, description=f"{name} cannot be negative")
    return value


def _pagination():
    limit = _positive_int('limit', DEFAULT_LIMIT)
    if limit < 1:
        abort(400, description="limit must be at least 1")
    offset = _positive_int('offset', 0)
    return min(limit, MAX_LIMIT), offset


def _search():
    """The WHERE clause and its bound parameters for ?q=, if given."""
    term = request.args.get('q', '').strip()
    if not term:
        return '', ()
    like = f"%{term}%"
    return SEARCH_WHERE, (like, like, like)
```

Replace the first three statements of `list_tracks`' body:

```python
    limit, offset = DEFAULT_LIMIT, 0
    where, params = '', ()
```

with:

```python
    limit, offset = _pagination()
    where, params = _search()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && ./venv/bin/python -m pytest tests/test_music_routes.py -q`
Expected: PASS, 15 passed

- [ ] **Step 5: Commit**

```bash
cd backend
git add music/music.py tests/test_music_routes.py
git commit -m "feat(music): add search and pagination to the listing"
```

---

### Task 11: Single track and streaming

**Files:**
- Modify: `backend/music/music.py`
- Modify: `backend/tests/test_schema.py`
- Test: `backend/tests/test_music_routes.py`

The client sends a track id and never a path. This is the feature's most
important security property: an endpoint accepting a client-supplied filename
would read any file on the Pi.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_music_routes.py`:

```python
class TestSingleTrack:
    def test_returns_the_track(self, client, reads):
        reads.row = TRACK_ROW

        res = client.get('/music/tracks/1')

        assert res.status_code == 200
        assert res.get_json()['title'] == 'Space Song'

    def test_unknown_id_is_a_404(self, client, reads):
        reads.row = None

        res = client.get('/music/tracks/999')

        assert res.status_code == 404
        assert 'no track with id 999' in res.get_json()['error']

    def test_looks_up_by_bound_id(self, client, reads):
        reads.row = TRACK_ROW

        client.get('/music/tracks/1')

        query, params = reads.queries[0]
        assert params == (1,)


class TestStreaming:
    def test_serves_a_file_inside_the_music_root(self, client, reads,
                                                 monkeypatch, tmp_path):
        monkeypatch.setenv('MUSIC_DIR', str(tmp_path))
        song = tmp_path / 'song.mp3'
        song.write_bytes(b'ID3audiodata')
        reads.row = {**TRACK_ROW, 'path': str(song)}

        res = client.get('/music/tracks/1/stream')

        assert res.status_code == 200
        assert res.get_data() == b'ID3audiodata'

    def test_advertises_range_support(self, client, reads, monkeypatch, tmp_path):
        monkeypatch.setenv('MUSIC_DIR', str(tmp_path))
        song = tmp_path / 'song.mp3'
        song.write_bytes(b'0123456789')
        reads.row = {**TRACK_ROW, 'path': str(song)}

        res = client.get('/music/tracks/1/stream')

        assert res.headers['Accept-Ranges'] == 'bytes'

    def test_range_request_returns_partial_content(self, client, reads,
                                                   monkeypatch, tmp_path):
        """Seeking in an <audio> element depends on this."""
        monkeypatch.setenv('MUSIC_DIR', str(tmp_path))
        song = tmp_path / 'song.mp3'
        song.write_bytes(b'0123456789')
        reads.row = {**TRACK_ROW, 'path': str(song)}

        res = client.get('/music/tracks/1/stream',
                         headers={'Range': 'bytes=2-5'})

        assert res.status_code == 206
        assert res.get_data() == b'2345'
        assert res.headers['Content-Range'] == 'bytes 2-5/10'

    def test_unknown_id_is_a_404(self, client, reads):
        reads.row = None

        assert client.get('/music/tracks/999/stream').status_code == 404

    def test_path_outside_the_root_is_refused(self, client, reads,
                                              monkeypatch, tmp_path):
        """A row pointing outside MUSIC_DIR must not be served."""
        root = tmp_path / 'music'
        root.mkdir()
        secret = tmp_path / 'secret.txt'
        secret.write_bytes(b'password')
        monkeypatch.setenv('MUSIC_DIR', str(root))
        reads.row = {**TRACK_ROW, 'path': str(secret)}

        res = client.get('/music/tracks/1/stream')

        assert res.status_code == 404
        assert b'password' not in res.get_data()

    def test_symlink_escaping_the_root_is_refused(self, client, reads,
                                                  monkeypatch, tmp_path):
        root = tmp_path / 'music'
        root.mkdir()
        secret = tmp_path / 'secret.txt'
        secret.write_bytes(b'password')
        link = root / 'innocent.mp3'
        link.symlink_to(secret)
        monkeypatch.setenv('MUSIC_DIR', str(root))
        reads.row = {**TRACK_ROW, 'path': str(link)}

        res = client.get('/music/tracks/1/stream')

        assert res.status_code == 404
        assert b'password' not in res.get_data()

    def test_refusal_does_not_reveal_that_the_row_exists(self, client, reads,
                                                         monkeypatch, tmp_path):
        root = tmp_path / 'music'
        root.mkdir()
        outside = tmp_path / 'secret.txt'
        outside.write_bytes(b'x')
        monkeypatch.setenv('MUSIC_DIR', str(root))
        reads.row = {**TRACK_ROW, 'path': str(outside)}

        res = client.get('/music/tracks/1/stream')

        assert res.get_json()['error'] == 'no track with id 1'

    def test_indexed_but_missing_file_is_a_clear_404(self, client, reads,
                                                     monkeypatch, tmp_path):
        monkeypatch.setenv('MUSIC_DIR', str(tmp_path))
        reads.row = {**TRACK_ROW, 'path': str(tmp_path / 'deleted.mp3')}

        res = client.get('/music/tracks/1/stream')

        assert res.status_code == 404
        assert 'missing on disk' in res.get_json()['error']

    def test_no_route_accepts_a_client_supplied_path(self):
        """The only way to name a file is by track id."""
        from app import app as flask_app

        for rule in flask_app.url_map.iter_rules():
            if str(rule).startswith('/music'):
                assert 'path' not in rule.arguments
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && ./venv/bin/python -m pytest tests/test_music_routes.py -q -k "SingleTrack or Streaming"`
Expected: FAIL — 404 from Flask's router; the routes do not exist.

- [ ] **Step 3: Write the implementation**

In `backend/music/music.py`, add to the imports:

```python
import os

from flask import Blueprint, abort, jsonify, request, send_file

from database.db import fetch_all, fetch_one
from music.config import resolve_inside_music_dir
```

Append the two routes:

```python
@bp.route('/music/tracks/<int:track_id>', methods=['GET'])
def get_track(track_id):
    track = fetch_one("SELECT * FROM track WHERE id = ? LIMIT 1", (track_id,))
    if track is None:
        abort(404, description=f"no track with id {track_id}")
    return jsonify(track)


@bp.route('/music/tracks/<int:track_id>/stream', methods=['GET'])
def stream_track(track_id):
    """Serve the audio file for a track, supporting range requests.

    The client supplies an id, never a path — the path comes from the row. The
    containment check is defence in depth: the scanner indexes whatever is on
    disk, so a symlink planted in the library would otherwise make this an
    arbitrary-file read. A refusal returns the same 404 as an unknown id so it
    does not confirm the row exists.
    """
    track = fetch_one("SELECT path FROM track WHERE id = ? LIMIT 1", (track_id,))
    if track is None:
        abort(404, description=f"no track with id {track_id}")

    path = resolve_inside_music_dir(track['path'])
    if path is None:
        abort(404, description=f"no track with id {track_id}")
    if not os.path.isfile(path):
        abort(404, description=f"track {track_id} is indexed but missing on disk")

    # conditional=True makes Flask honour Range and return 206, which is what
    # lets an <audio> element seek. Phase 3 replaces this with X-Accel-Redirect
    # so gunicorn workers are not held open for the length of a track.
    return send_file(path, conditional=True)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && ./venv/bin/python -m pytest tests/test_music_routes.py -q`
Expected: PASS, 27 passed

- [ ] **Step 5: Extend the schema guard to the new routes**

In `backend/tests/test_schema.py`, add to `REQUESTS`:

```python
    ('get', '/music/tracks', None),
    ('get', '/music/tracks/1', None),
    ('get', '/music/tracks/1/stream', None),
```

The guard's stub row must satisfy every route it now exercises — the listing
reads `['n']` from the count, and the stream route reads `['path']`. Change:

```python
    reads.row = {'id': 1, 'name': 'x', 'streak': 1, 'last_completed': None}
```

to:

```python
    reads.row = {'id': 1, 'name': 'x', 'streak': 1, 'last_completed': None,
                 'n': 0, 'path': '/tmp/livs-test-music/probe.mp3'}
```

The guard only inspects columns named with `=` or `LIKE`, so extend
`referenced_columns` to catch the search clause. After the existing
`columns |= set(re.findall(r'(\w+)\s*=', sql))` line, add:

```python
    # `title LIKE ?` names a column just as much as `title = ?` does.
    columns |= set(re.findall(r'(\w+)\s+LIKE\b', sql))
```

- [ ] **Step 6: Run the full suite**

Run: `cd backend && ./venv/bin/python -m pytest tests -q`
Expected: PASS, 224 passed, 8 deselected

- [ ] **Step 7: Confirm the schema guard is not vacuous**

Temporarily change `SEARCH_WHERE` in `backend/music/music.py` to use
`titel LIKE ?`, then run:

Run: `cd backend && ./venv/bin/python -m pytest tests/test_schema.py -q`
Expected: FAIL with `references missing column(s) {'titel'}`

Revert the typo and re-run to confirm PASS. If it passed with the typo in place,
the `LIKE` pattern is not working — stop and fix it.

- [ ] **Step 8: Commit**

```bash
cd backend
git add music/music.py tests/test_music_routes.py tests/test_schema.py
git commit -m "feat(music): add single track and range-capable streaming"
```

---

### Task 12: Integration tests against real files and a real database

**Files:**
- Create: `backend/tests/test_integration_music.py`

Stubbed tests are what let the recipes JSON-column bug ship, so the scanner and
streaming get real round trips. Follow the fixture pattern in
`backend/tests/test_integration.py`: `monkeypatch.undo()` to drop conftest's fake
config, skip cleanly when no database is reachable, and clean up rows afterwards.

- [ ] **Step 1: Write the tests**

Create `backend/tests/test_integration_music.py`:

```python
"""Round trips for the music library against a real database and real files.

Deselected by default (see pytest.ini). Run with:  pytest -m integration
"""
import os

import mariadb
import pytest
from dotenv import load_dotenv

from app import app as flask_app
from database import db
from music import scanner

pytestmark = pytest.mark.integration

load_dotenv()


@pytest.fixture
def real_env(monkeypatch, tmp_path):
    """Drop conftest's fake DB config, but keep MUSIC_DIR on a temp library."""
    monkeypatch.undo()
    load_dotenv(override=True)
    monkeypatch.setenv('MUSIC_DIR', str(tmp_path))
    return tmp_path


@pytest.fixture
def live_db(real_env):
    try:
        with flask_app.app_context():
            db.fetch_all("SELECT 1")
    except (mariadb.Error, RuntimeError) as err:
        pytest.skip(f"no database available: {err}")
    yield
    with flask_app.app_context():
        db.execute("DELETE FROM track")


@pytest.fixture
def library(real_env, live_db):
    return real_env


@pytest.fixture
def client(live_db):
    flask_app.config.update(TESTING=True)
    return flask_app.test_client()


def write_audio(root, relative, payload=b'ID3' + b'x' * 2048):
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return path


def test_scan_indexes_real_files(library, client):
    write_audio(library, 'Artist/Album/01 One.mp3')
    write_audio(library, 'Artist/Album/02 Two.flac')

    with flask_app.app_context():
        counts = scanner.scan_music()

    assert counts['added'] == 2

    body = client.get('/music/tracks').get_json()
    assert body['total'] == 2
    assert {t['format'] for t in body['tracks']} == {'mp3', 'flac'}


def test_untagged_file_still_gets_a_title_from_its_filename(library, client):
    write_audio(library, 'Mystery Track.mp3')

    with flask_app.app_context():
        scanner.scan_music()

    titles = [t['title'] for t in client.get('/music/tracks').get_json()['tracks']]
    assert 'Mystery Track' in titles


def test_rescan_is_incremental(library):
    write_audio(library, 'song.mp3')

    with flask_app.app_context():
        first = scanner.scan_music()
        second = scanner.scan_music()

    assert first['added'] == 1
    assert second == {'added': 0, 'updated': 0, 'unchanged': 1,
                      'removed': 0, 'skipped': 0}


def test_rescan_after_edit_updates_in_place_keeping_the_id(library, client):
    path = write_audio(library, 'song.mp3')

    with flask_app.app_context():
        scanner.scan_music()
    before = client.get('/music/tracks').get_json()['tracks'][0]['id']

    path.write_bytes(b'ID3' + b'y' * 4096)
    os.utime(path, (1, 1))
    with flask_app.app_context():
        counts = scanner.scan_music()

    after = client.get('/music/tracks').get_json()['tracks'][0]['id']
    assert counts['updated'] == 1
    assert after == before, "ids must survive an update for playlists later"


def test_rescan_removes_deleted_files(library, client):
    path = write_audio(library, 'gone.mp3')
    write_audio(library, 'kept.mp3')

    with flask_app.app_context():
        scanner.scan_music()
    path.unlink()
    with flask_app.app_context():
        counts = scanner.scan_music()

    assert counts['removed'] == 1
    assert client.get('/music/tracks').get_json()['total'] == 1


def test_scan_aborts_instead_of_emptying_the_library(library, client):
    write_audio(library, 'song.mp3')
    with flask_app.app_context():
        scanner.scan_music()

    for child in library.iterdir():
        child.unlink()

    with flask_app.app_context():
        with pytest.raises(scanner.ScanAborted):
            scanner.scan_music()

    assert client.get('/music/tracks').get_json()['total'] == 1, \
        "the row must survive an aborted scan"


def test_unicode_paths_and_search_round_trip(library, client):
    write_audio(library, 'Sigur Rós/Ágætis byrjun/Svefn-g-englar.mp3')

    with flask_app.app_context():
        scanner.scan_music()

    body = client.get('/music/tracks?q=Svefn').get_json()
    assert body['total'] == 1
    assert 'Svefn' in body['tracks'][0]['title']


def test_stream_returns_the_bytes_on_disk(library, client):
    write_audio(library, 'song.mp3', payload=b'EXACTBYTES')

    with flask_app.app_context():
        scanner.scan_music()
    track_id = client.get('/music/tracks').get_json()['tracks'][0]['id']

    res = client.get(f'/music/tracks/{track_id}/stream')

    assert res.status_code == 200
    assert res.get_data() == b'EXACTBYTES'


def test_stream_honours_a_range_request(library, client):
    write_audio(library, 'song.mp3', payload=b'0123456789')

    with flask_app.app_context():
        scanner.scan_music()
    track_id = client.get('/music/tracks').get_json()['tracks'][0]['id']

    res = client.get(f'/music/tracks/{track_id}/stream',
                     headers={'Range': 'bytes=3-6'})

    assert res.status_code == 206
    assert res.get_data() == b'3456'


def test_pagination_walks_the_whole_library(library, client):
    for i in range(5):
        write_audio(library, f'{i:02d}.mp3')

    with flask_app.app_context():
        scanner.scan_music()

    first = client.get('/music/tracks?limit=2&offset=0').get_json()
    second = client.get('/music/tracks?limit=2&offset=2').get_json()
    third = client.get('/music/tracks?limit=2&offset=4').get_json()

    assert first['total'] == 5
    assert len(first['tracks']) == 2
    assert len(third['tracks']) == 1
    ids = {t['id'] for t in first['tracks']} | {t['id'] for t in second['tracks']}
    assert len(ids) == 4, "pages must not overlap"
```

- [ ] **Step 2: Run the integration tests**

Run: `cd backend && ./venv/bin/python -m pytest tests -m integration -q`
Expected: PASS, 18 passed (10 new plus the existing 8)

If they skip with "no database available", `backend/.env` is missing or MySQL is
not running — see `deploy/README.md`.

- [ ] **Step 3: Confirm the default suite still excludes them and passes**

Run: `cd backend && ./venv/bin/python -m pytest tests -q`
Expected: PASS, 224 passed, 18 deselected

- [ ] **Step 4: Confirm the real database is left clean**

Run:

```bash
/opt/homebrew/opt/mysql/bin/mysql -u root -D livs -e "SELECT COUNT(*) FROM track;"
```

Expected: `0`

- [ ] **Step 5: Commit**

```bash
cd backend
git add tests/test_integration_music.py
git commit -m "test(music): add real-file integration tests"
```

---

### Task 13: Manual verification end to end

**Files:** none — verification only.

- [ ] **Step 1: Build a small real library**

```bash
mkdir -p /tmp/livs-music/Demo
cd /tmp/livs-music/Demo
# Any real audio file will do. If ffmpeg is available, synthesise one:
ffmpeg -f lavfi -i "sine=frequency=440:duration=5" -c:a libmp3lame \
  -metadata title="Test Tone" -metadata artist="Synth" \
  -metadata album="Demo Album" tone.mp3
```

If ffmpeg is unavailable, copy any mp3 or FLAC you have into that directory
instead; the scanner does not require valid tags.

- [ ] **Step 2: Point the app at it and scan**

```bash
cd /Users/ggarb/Desktop/personal/livs_website/backend
MUSIC_DIR=/tmp/livs-music ./venv/bin/flask --app app init-db
MUSIC_DIR=/tmp/livs-music ./venv/bin/flask --app app scan-music
```

Expected: `added 1, updated 0, unchanged 0, removed 0, skipped 0`

- [ ] **Step 3: Serve it and check the endpoints**

```bash
cd /Users/ggarb/Desktop/personal/livs_website/backend
MUSIC_DIR=/tmp/livs-music ./venv/bin/gunicorn --workers 2 \
  --bind 127.0.0.1:5055 app:app &
sleep 3
curl -s 'localhost:5055/music/tracks' | head -c 400; echo
curl -s 'localhost:5055/music/tracks?q=tone' | head -c 200; echo
curl -s -o /dev/null -w 'full:%{http_code} %{size_download} bytes\n' \
  localhost:5055/music/tracks/1/stream
curl -s -o /dev/null -H 'Range: bytes=0-99' \
  -w 'range:%{http_code} %{size_download} bytes\n' \
  localhost:5055/music/tracks/1/stream
```

Expected: the listing shows `"total": 1` with `"title": "Test Tone"`; the search
returns it; the full request is `200` with the file's full size; the range
request is `206` with exactly `100 bytes`.

- [ ] **Step 4: Confirm a rescan is a no-op**

```bash
MUSIC_DIR=/tmp/livs-music ./venv/bin/flask --app app scan-music
```

Expected: `added 0, updated 0, unchanged 1, removed 0, skipped 0`

- [ ] **Step 5: Confirm the abort rail on a real empty directory**

```bash
mkdir -p /tmp/livs-music-empty
MUSIC_DIR=/tmp/livs-music-empty ./venv/bin/flask --app app scan-music; echo "exit=$?"
```

Expected: an error mentioning the row count and "Is the drive mounted?", with a
non-zero exit and no traceback. Then confirm nothing was deleted:

```bash
curl -s 'localhost:5055/music/tracks' | head -c 120; echo
```

Expected: still `"total": 1`

- [ ] **Step 6: Tear down**

```bash
kill %1
cd /Users/ggarb/Desktop/personal/livs_website/backend
./venv/bin/python -c "
from app import app
from database import db
with app.app_context():
    db.execute('DELETE FROM track')
    print('track rows:', len(db.fetch_all('SELECT * FROM track')))
"
rm -rf /tmp/livs-music /tmp/livs-music-empty
```

- [ ] **Step 7: Commit nothing; report results**

No code changes in this task. Report the observed output of each step.

---

## Deferred to later phases

Explicitly out of scope here, recorded so they are not half-built: playlists and
`playlist_track`, favourites, embedded artwork extraction, authentication,
public exposure, `X-Accel-Redirect`, the nightly systemd timer, video and
Jellyfin. Renaming `playlist/` is unnecessary — this plan creates `music/`
directly and leaves the empty `playlist/` directory alone.

## Spec coverage

| Spec requirement | Task |
| --- | --- |
| `MUSIC_DIR`, required, read at use time | 1 |
| `MAX_PATH_LENGTH` matching the column | 1 |
| Path containment after symlink resolution | 1, 11 |
| `track` DDL, `VARCHAR(768)` full unique index | 2 |
| `mtime` as integer epoch | 2 |
| Tag reading with filename fallback | 3 |
| Per-file tag failure tolerance | 3 |
| Audio extension list | 3 |
| Recursive walk, upsert by path | 4 |
| Incremental skip on size and mtime | 5 |
| Update in place, never delete-and-reinsert | 5, 12 |
| Removal detection | 5 |
| Zero-files abort rail | 6, 12 |
| Over-length paths skipped and logged | 7 |
| CLI invocation, not reachable over HTTP | 8 |
| Paginated envelope with total | 9 |
| `?q=` across title, artist, album, parameterised | 10 |
| `limit` default 50, max 200; 400 on bad input | 10 |
| Single track endpoint | 11 |
| Range streaming, `206` | 11, 12 |
| Client never supplies a path | 11 |
| Indexed-but-missing file is a 404 | 11 |
| Unicode round trip | 12 |
| `mutagen` pinned | 1 |
