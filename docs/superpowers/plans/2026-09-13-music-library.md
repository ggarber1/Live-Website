# Music Library (Phase 1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A LAN-only music library: scan an on-disk music directory into the database, then browse, search and play it in a browser.

**Architecture:** Disk is the source of truth; the `track` table is a rebuildable index. A CLI-invoked scanner walks `MUSIC_DIR`, reads tags with mutagen, and upserts rows keyed by path. A Flask blueprint serves a paginated, searchable listing plus a byte-range streaming endpoint. Clients only ever send a track id — never a path.

**Tech Stack:** Python 3.9, Flask 3.1.3, MySQL/MariaDB via the `mariadb` driver, mutagen for tags, pytest.

Spec: `docs/superpowers/specs/2026-09-09-media-library-design.md`

---

## START HERE — handoff, 2026-09-15

**Phase 1 is functionally complete. Tasks 1-12 are done; Task 13 (manual
end-to-end verification) is the only one left, and its section near the bottom
of this file has been rewritten with correct expectations.**

Branch `feat/music-library`, 37 commits ahead of `main`, nothing uncommitted.

```bash
cd backend
./venv/bin/python -m pytest tests -q                 # 295 passed, 29 deselected
./venv/bin/python -m pytest tests -m integration -q  #  29 passed (needs MySQL + .env)
```

### Do this first

**`MUSIC_DIR` is not set in `backend/.env`.** Tests supply their own value, so
nothing caught it, but the app cannot serve music without it. Add a real
absolute path before running Task 13.

### Known gaps, deliberately not done

Neither is a defect; both are recorded rather than forgotten.

- **No index on the sort columns.** `ORDER BY artist, album, track_no, title, id`
  cannot use an index, so every listing request filesorts the whole matched set.
  Fine at thousands of rows on a Pi; matters in the tens of thousands. The fix
  is a composite index, not keyset pagination.
- **Search is single-term substring.** `?q=beach house depression` matches
  nothing, because no single column holds all three words. This is exactly what
  the design spec specifies; a later task could split on whitespace or add a
  fulltext index.

### Do not trust the code blocks in Tasks 1-4

They predate the fixes that review forced. `backend/music/` and its tests are
the specification. Tasks 5-12 have been rewritten to record what was actually
built and why; Tasks 1-4 are left as-is for their reasoning and TDD sequence.

The `git log` on this branch is unusually informative — most commit messages
explain the failure mode being closed, not just the change.

### What exists

**Scanner** — `scan_music(force_removals=False)` returns nine counts:
`added`, `updated`, `unchanged`, `removed`, `skipped`, `skipped_too_long`,
`skipped_unreadable`, `skipped_rejected`, `unreadable_dirs`. Raises
`ScanAborted` rather than gutting the table. Handles, each distinctly and each
with a test that fails when the handling is removed: an empty library, an
unmounted drive, a reconfigured root, an unreadable directory, an unreadable
file, a malformed tag, an oversized numeric value, over-length text, an
over-length path, a duplicate row, and a dropped connection.

**CLI** — `flask --app app scan-music [--force-removals]`. Exit 0 when the
scan completed even if files were skipped; non-zero when it refused to act or
could not finish. Nightly timer units in `deploy/`.

**HTTP** — `GET /music/tracks` (paginated, searchable), `/music/tracks/<id>`,
`/music/tracks/<id>/stream` (byte ranges). No response ever contains `path`.

### Two conventions worth keeping

- Clear bytecode between mutation checks: `find . -name __pycache__ -type d
  -not -path "./venv/*" -exec rm -rf {} +`. Python invalidates `.pyc` on
  mtime+size, so two edits inside one second can leave stale bytecode and make
  a restored file look broken. This wasted a debugging cycle.
- Every new guard gets proved load-bearing by breaking it deliberately and
  watching a named test fail. Three tests in this project passed for the wrong
  reason until that was applied — `768 == 768`, `'Traceback' not in output`,
  and `isinstance(body, dict)` against a 404 error body.

### Review state

Tasks 1-11 each passed a spec-compliance review and a code-quality review.
**Task 12's two reviews were not run** — the session ended first. The tests
pass and were verified by hand, but they have not had an independent read.

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

### Task 7: Scanner — over-length paths — DONE, superseded

Implemented in `1955859`, `2ce1271`. Original text removed; it put the check in
the wrong place and predates the counts split.

`track.path` is `VARCHAR(768)`, which is exactly the widest full unique index
InnoDB allows (3072 bytes / 4 bytes per utf8mb4 character). Paths longer than
that are skipped and logged rather than truncated into something that can never
stream. There is no character-versus-byte gap: the guard counts codepoints and
the column counts characters, and at 768 those coincide even for all-emoji
paths.

**Placement is the substance of this task.** The check sits after
`found_any = True` and `seen.add(path)`, before `os.stat`:

- after `found_any`, because that flag means "the walk yielded a candidate",
  not "something was indexed" — a library whose paths are all too long is not
  an unmounted drive and must reach the proportional rail, not the
  "Is the drive mounted?" abort;
- after `seen.add`, because the file exists and nothing about it should look
  deleted.

Review also split the `skipped` counter. It had collapsed three problems with
three different remedies into one number: rename the file, repair permissions,
correct the tag data. `skipped` remains as the rollup, with
`skipped_too_long`, `skipped_unreadable` and `skipped_rejected` beneath it, so
the nine-key counts dict is what `scan_music` now returns.

---

### Task 8: The `scan-music` CLI command — DONE, superseded

Implemented in `1759511`, `e7c570d`, `53f4f15`, `b057d96`. Original text removed;
it predates the nine-key dict and the force option.

`scan_music_command` wraps `scan_music(force_removals=...)` and is registered in
`app.py`. It is deliberately not reachable over HTTP: a full scan takes minutes
and would pin a gunicorn worker.

The **exit-code policy** is the substance, and was not in the original plan:

| Outcome | Exit | Why |
| --- | --- | --- |
| `ScanAborted` | non-zero | The scan refused to act. |
| `unreadable_dirs > 0` | non-zero, after printing counts | Removal detection was skipped, so the index is knowingly stale. An unreadable directory disables removal for the whole table, not just that subtree — cumulative, and it worsens. |
| skipped files only | zero | A per-file data problem is not a scan failure. One permanently broken file must not fail a nightly timer forever. |

Counts print before the failure is raised, so the operator keeps the numbers.

Two things review corrected that are worth not re-introducing:

- The abort messages said "Pass force_removals" — the Python kwarg. From a
  shell the flag is `--force-removals`. Fixed at the source in
  `_refuse_mass_removal`, since `scan_music` has exactly one caller.
- `assert 'Traceback' not in result.output` was vacuous: Click's `CliRunner`
  catches exceptions, so no traceback ever reaches output either way. The test
  asserts on `result.exception` instead.

Operations live in `deploy/README.md` section 6, with `deploy/livs-scan.service`
and `deploy/livs-scan.timer` for the nightly run. Note the documented
convention that `MUSIC_DIR` points at a subdirectory, not a filesystem root: a
root-owned `lost+found` would be permanently unreadable, and "fix the
permissions" is not actionable advice for it.

---

### Tasks 9-11: the HTTP layer — DONE, superseded

Implemented across `a27f382`, `5e72303`, `59c26d7` (listing), `7e9ca25`,
`b2e673a` (search and pagination), `aaae113`, `1ec5acc`, `5cda9ba` (single
track and streaming), plus `608d1cf` (threaded workers, a deploy change).

Original text removed. `backend/music/music.py` and
`backend/tests/test_music_routes.py` are the specification.

**Endpoints:**

| Method | Path | Behaviour |
| --- | --- | --- |
| GET | `/music/tracks` | Envelope `{tracks, total, limit, offset}`. `?q=`, `?limit=` (default 50, max 200), `?offset=`. |
| GET | `/music/tracks/<id>` | One track, or 404. |
| GET | `/music/tracks/<id>/stream` | The audio file, byte ranges supported. |

**Decisions review forced, which the original text did not have:**

- **`TRACK_COLUMNS`, never `SELECT *`.** `path` and `mtime_ns` are excluded
  from every client-facing response. `path` is the Pi's filesystem layout, and
  `mtime_ns` (~1.7e18) exceeds JavaScript's `Number.MAX_SAFE_INTEGER`, so a
  browser doing `JSON.parse` would corrupt it silently. Both routes use it.
- **`ORDER BY ... , id`.** The sort ends on the primary key. Without a unique
  tiebreaker, untagged tracks — all NULL artist/album/track_no — tie on title
  too, their order between queries is undefined, and a client paging through
  sees duplicates and misses rows.
- **`ESCAPE '!'`, stated explicitly.** `%` and `_` are LIKE metacharacters, and
  filename-derived titles are full of underscores, so `my_song` must not match
  `myXsong`. `!` rather than the default backslash because a backslash in an
  ESCAPE clause is itself subject to `sql_mode`: under `NO_BACKSLASH_ESCAPES`
  the literal `'\\'` is two characters and ESCAPE rejects it. `_like_term`
  escapes the escape character first.
- **Audio mimetypes registered with `mimetypes.add_type`.** Only `.mp3` and
  `.wav` are in CPython's built-in table; `.flac`, `.m4a` and `.ogg` resolve
  only if the host ships `/etc/mime.types`, which a Pi OS Lite image may not.
  Without this, three of five formats serve `application/octet-stream` and
  browsers refuse to play them. `audio/mp4` for `.m4a` — the system table's
  `audio/mp4a-latm` is an RTP transport type that never plays.
- **A containment refusal returns the unknown-id 404 verbatim**, so it does not
  confirm the row exists. The missing-file 404 is deliberately distinct.
- **`gthread` workers.** `send_file` streams through the worker, so a 40 MB
  FLAC over weak wifi holds it for minutes; with sync workers three listeners
  would block every request including `/todo`. Safe only because connections
  are per-request on `flask.g`, which is thread-local — verified eight
  concurrent contexts produce eight distinct connections.

---

### Task 12: Integration tests — DONE, superseded

Implemented in `6329e31`. 21 new tests, 29 integration total, in
`backend/tests/test_integration_music.py`. Deselected by default; run with
`pytest tests -m integration`.

Original text removed: it asserted a five-key counts dict and covered only
happy-path round trips.

This task exists because every other test stubs the database, which is how
`GET /recipes` once shipped returning 500 for any stored row — MySQL hands
`JSON` columns back as bytes and no stub ever produced bytes. So it verifies
the things a stub structurally cannot represent:

- the real JSON response contains no `path` and no `mtime_ns`, and the
  filesystem root appears nowhere in the payload;
- `mtime_ns` and `size_bytes` come back as Python `int`, which is what makes
  the incremental skip fire rather than rewriting every file every scan;
- MySQL's own LIKE semantics — an underscore search matches one row, not all;
- a 500-character tag stores truncated rather than failing the insert against
  `VARCHAR(255)` in strict mode;
- an over-length path is skipped while its siblings still index;
- a 4-byte character (emoji) survives the utf8mb4 column;
- real mimetypes from real files through the real route;
- pagination covers every row exactly once with no overlap.

Demonstrated rather than asserted: reverting `TRACK_COLUMNS` to `*` fails the
response test, and breaking `_like_term` makes an underscore search return
every row in the library — a consequence no stub can observe.

---

### Task 13: Manual verification end to end — THE ONLY TASK REMAINING

**Files:** none. Verification only.

The plan's original steps are stale — they predate the skip breakdown in the
CLI output and the fifth table. Use these.

**Prerequisite, and the reason this has not been run yet:** `MUSIC_DIR` is not
set in `backend/.env`. Tests supply their own, so nothing caught it. Add it
before starting:

```
MUSIC_DIR=/absolute/path/to/a/music/directory
```

- [ ] **Step 1: build a small real library**

```bash
mkdir -p /tmp/livs-music/Demo
ffmpeg -f lavfi -i "sine=frequency=440:duration=5" -c:a libmp3lame \
  -metadata title="Test Tone" -metadata artist="Synth" \
  -metadata album="Demo Album" /tmp/livs-music/Demo/tone.mp3
```

If ffmpeg is unavailable, copy any real mp3 or flac in instead — the scanner
does not require valid tags.

- [ ] **Step 2: point the app at it and index**

```bash
cd backend
MUSIC_DIR=/tmp/livs-music ./venv/bin/flask --app app init-db
MUSIC_DIR=/tmp/livs-music ./venv/bin/flask --app app scan-music
```

Expect `Tables ready: todo, recipes, habits, blog, track` then
`added 1, updated 0, unchanged 0, removed 0`. A clean run prints no second
line; a skip line appears only when something was skipped.

- [ ] **Step 3: serve it and exercise every endpoint**

```bash
cd backend
MUSIC_DIR=/tmp/livs-music ./venv/bin/gunicorn --workers 2 \
  --worker-class gthread --threads 4 --bind 127.0.0.1:5055 app:app &
sleep 3
curl -s 'localhost:5055/music/tracks' | head -c 400; echo
curl -s 'localhost:5055/music/tracks?q=tone' | head -c 200; echo
curl -s -o /dev/null -w 'full:  %{http_code} %{size_download} bytes %{content_type}\n' \
  localhost:5055/music/tracks/1/stream
curl -s -o /dev/null -H 'Range: bytes=0-99' \
  -w 'range: %{http_code} %{size_download} bytes\n' \
  localhost:5055/music/tracks/1/stream
```

Expect: the listing shows `"total": 1` with `"title": "Test Tone"` and **no
`path` key**; the search finds it; the full request is `200` with
`audio/mpeg`; the range request is `206` with exactly `100 bytes`.

- [ ] **Step 4: confirm a rescan is a no-op**

```bash
MUSIC_DIR=/tmp/livs-music ./venv/bin/flask --app app scan-music
```

Expect `added 0, updated 0, unchanged 1, removed 0`. If it says `updated 1`,
the incremental skip is not firing — investigate rather than shrugging.

- [ ] **Step 5: confirm the abort rail on a real empty directory**

```bash
mkdir -p /tmp/livs-music-empty
MUSIC_DIR=/tmp/livs-music-empty ./venv/bin/flask --app app scan-music; echo "exit=$?"
```

Expect a non-zero exit and a message naming the row count and asking whether
the drive is mounted, with no traceback. Then confirm nothing was deleted:

```bash
curl -s 'localhost:5055/music/tracks' | head -c 120; echo
```

Expect still `"total": 1`.

- [ ] **Step 6: play it in an actual browser**

The only step no test covers. Open a page with
`<audio controls src="http://localhost:5055/music/tracks/1/stream">`, press
play, and drag the scrubber. Seeking is what the `206` support exists for.

- [ ] **Step 7: tear down**

```bash
kill %1
cd backend && ./venv/bin/python -c "
from app import app
from database import db
with app.app_context():
    db.execute('DELETE FROM track')
    print('track rows:', len(db.fetch_all('SELECT * FROM track')))
"
rm -rf /tmp/livs-music /tmp/livs-music-empty
```

- [ ] **Step 8: report, do not commit**

No code changes. Report the observed output of each step.

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
| `mtime_ns` as integer nanoseconds | 2, corrected in 4 |
| Tag reading with filename fallback | 3 |
| Per-file tag failure tolerance | 3 |
| Audio extension list | 3 |
| Recursive walk, upsert by path | 4 |
| Incremental skip on size and `mtime_ns` | 5 |
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
