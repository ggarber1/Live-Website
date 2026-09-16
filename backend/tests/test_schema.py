"""Guards that TABLE_DDL actually covers the SQL the routes run.

The routes queried `todo(task)` while the schema created `todo_list(item)`, which
no unit test noticed because every test stubs the database out. These tests read
the real SQL back off the stubs and check it against the real DDL.
"""
import re

import pytest

from database.db import TABLE_DDL

# One request per route, so every statement in the app gets collected.
REQUESTS = [
    ('get', '/api/todo', None),
    ('post', '/api/todo', {'task': 'buy milk'}),
    ('put', '/api/todo/1', {'task': 'buy milk'}),
    ('delete', '/api/todo/1', None),
    ('get', '/api/habits', None),
    ('post', '/api/habits', {'name': 'floss'}),
    ('put', '/api/habits/1', {'name': 'floss'}),
    ('delete', '/api/habits/1', None),
    ('post', '/api/habits/1/complete', None),
    ('get', '/api/blog', None),
    ('post', '/api/blog', {'title': 'hi', 'content': 'there'}),
    ('put', '/api/blog/1', {'title': 'hi', 'content': 'there'}),
    ('delete', '/api/blog/1', None),
    ('get', '/api/recipes', None),
    ('post', '/api/recipes', {'title': 't', 'ingredients': ['a'], 'instructions': ['b']}),
    ('put', '/api/recipes/1', {'title': 't', 'ingredients': ['a'], 'instructions': ['b']}),
    ('delete', '/api/recipes/1', None),
    ('get', '/api/music/tracks', None),
    ('get', '/api/photos', None),
    ('get', '/api/photos/1', None),
    ('put', '/api/photos/1', {'caption': 'us'}),
    # With ?q=, so the search clause is actually executed. Without it the
    # route takes the no-filter branch and the LIKE columns are never checked.
    ('get', '/api/music/tracks?q=beach', None),
    ('get', '/api/music/tracks/1', None),
    ('get', '/api/music/tracks/1/stream', None),
]

# Every type used in TABLE_DDL has to be listed here, or its columns are
# invisible to this guard: BIGINT was missing, which silently hid size_bytes
# and mtime. Position within the alternation does not matter — none of these
# types is a prefix of another, so each branch is only ever tried at the one
# position after the column name.
COLUMN_TYPES = 'BIGINT|INT|VARCHAR|TEXT|JSON|TIMESTAMP|DATETIME|DATE'


def ddl_columns(ddl):
    return set(re.findall(rf'^\s*(\w+)\s+(?:{COLUMN_TYPES})', ddl, re.M))


def table_of(sql):
    match = re.search(r'\b(?:FROM|INTO|UPDATE)\s+(\w+)', sql)
    assert match, f"could not find a table name in: {sql}"
    return match.group(1)


def referenced_columns(sql):
    """Every column name the statement names explicitly."""
    columns = set()

    insert_list = re.search(r'INSERT INTO \w+ \(([^)]*)\)', sql)
    if insert_list:
        columns |= {name.strip() for name in insert_list.group(1).split(',')}

    # Anything assigned or compared: `SET streak = ?`, `WHERE id = ?`.
    columns |= set(re.findall(r'(\w+)\s*=', sql))

    # `title LIKE ?` names a column just as much as `title = ?` does.
    columns |= set(re.findall(r'(\w+)\s+LIKE\b', sql))

    order_by = re.search(r'ORDER BY (.+?)$', sql)
    if order_by:
        columns |= {term.strip().split()[0] for term in order_by.group(1).split(',')}

    return columns


@pytest.mark.parametrize('method,path,body', REQUESTS)
def test_route_sql_matches_the_schema(client, writes, reads, method, path, body):
    # A row has to exist or routes that look one up bail before their write.
    reads.row = {'id': 1, 'name': 'x', 'streak': 1, 'last_completed': None,
                 'n': 0, 'path': '/tmp/livs-test-music/probe.mp3'}
    kwargs = {'json': body} if body is not None else {}
    getattr(client, method)(path, **kwargs)

    statements = [sql for sql, _ in writes.queries + reads.queries]
    assert statements, f"{method.upper()} {path} ran no SQL"

    for sql in statements:
        table = table_of(sql)
        assert table in TABLE_DDL, f"{sql!r} hits unknown table {table!r}"
        unknown = referenced_columns(sql) - ddl_columns(TABLE_DDL[table])
        assert not unknown, f"{sql!r} references missing column(s) {unknown}"


def test_ddl_key_matches_the_table_it_creates():
    for name, ddl in TABLE_DDL.items():
        assert re.search(rf'CREATE TABLE IF NOT EXISTS {name}\b', ddl)


def test_every_table_has_an_id_and_created_at():
    for name, ddl in TABLE_DDL.items():
        assert {'id', 'created_at'} <= ddl_columns(ddl), name


def test_track_table_exists_with_the_columns_the_scanner_needs():
    columns = ddl_columns(TABLE_DDL['track'])

    assert {'id', 'path', 'title', 'artist', 'album', 'track_no',
            'duration_seconds', 'format', 'size_bytes', 'mtime_ns',
            'created_at'} <= columns


def test_track_path_is_uniquely_indexed_in_full():
    """A prefix index would let two long paths collide into one track.

    Matched against the `path` line specifically: a bare `'VARCHAR(768)' in ddl`
    would also be satisfied by some other column happening to be 768 wide.
    """
    ddl = TABLE_DDL['track']

    assert re.search(r'^\s*path\s+VARCHAR\(768\)\s+NOT NULL\s+UNIQUE\s*,\s*$',
                     ddl, re.M)
    assert 'path(' not in ddl, "a prefix index only enforces uniqueness on the prefix"


@pytest.fixture
def ddl_run(monkeypatch):
    """Record the statements create_tables would execute."""
    from database import db

    ran = []
    monkeypatch.setattr(db, 'execute', lambda sql, params=None: ran.append(sql))
    return ran


def test_create_tables_runs_every_ddl(ddl_run):
    from database import db

    db.create_tables()

    assert ddl_run == list(TABLE_DDL.values())


def test_init_db_command_creates_the_tables(ddl_run):
    from app import app as flask_app

    result = flask_app.test_cli_runner().invoke(args=['init-db'])

    assert result.exit_code == 0, result.output
    assert ddl_run == list(TABLE_DDL.values())
    for table in TABLE_DDL:
        assert table in result.output


def test_init_db_command_is_registered():
    from app import app as flask_app

    assert 'init-db' in flask_app.cli.commands


def test_max_path_length_matches_the_track_path_column():
    """The scanner skips over-length paths; its limit must track the column."""
    from music.config import MAX_PATH_LENGTH

    assert re.search(rf'^\s*path\s+VARCHAR\({MAX_PATH_LENGTH}\)',
                     TABLE_DDL['track'], re.M)


def test_track_int_columns_can_hold_the_tag_bounds():
    """tags.py clamps to these; a narrowed column must narrow the clamp too."""
    from music.tags import MAX_SIGNED_INT, MAX_TRACK_NUMBER

    ddl = TABLE_DDL['track']
    for column in ('track_no', 'duration_seconds'):
        assert re.search(rf'^\s*{column}\s+INT\b', ddl, re.M), column
    assert MAX_SIGNED_INT == 2147483647
    assert MAX_TRACK_NUMBER <= MAX_SIGNED_INT


def test_track_text_columns_match_the_tag_truncation():
    """tags.py truncates to MAX_TEXT_LENGTH; the columns must be that wide."""
    from music.tags import MAX_TEXT_LENGTH

    ddl = TABLE_DDL['track']
    for column in ('title', 'artist', 'album'):
        assert re.search(rf'^\s*{column}\s+VARCHAR\({MAX_TEXT_LENGTH}\)',
                         ddl, re.M), column


def test_track_listing_index_matches_the_listing_sort():
    """The index only removes the filesort if its columns are the ORDER BY.

    Column order matters: an index on (album, artist, ...) is useless to a sort
    on (artist, album, ...). `id` has to be listed explicitly: InnoDB appends
    the primary key to every secondary index, but the optimizer ignores that
    implicit column when matching an ORDER BY, and the index goes unused.
    """
    from music.music import SELECT_PAGE

    order_by = re.search(r'ORDER BY (.+?) LIMIT', SELECT_PAGE).group(1)
    sort_columns = [c.strip() for c in order_by.split(',')]
    assert sort_columns[-1] == 'id'

    index = re.search(r'INDEX track_listing \((.+?)\)', TABLE_DDL['track'])
    assert index, 'track has no track_listing index'
    index_columns = [c.strip() for c in index.group(1).split(',')]

    assert index_columns == sort_columns


def test_photo_table_exists_with_the_columns_the_scanner_needs():
    columns = ddl_columns(TABLE_DDL['photo'])

    assert {'id', 'path', 'taken_at', 'width', 'height', 'format', 'size_bytes',
            'mtime_ns', 'caption', 'created_at'} <= columns


def test_photo_path_is_uniquely_indexed_in_full():
    assert re.search(r'^\s*path\s+VARCHAR\(768\)\s+NOT NULL\s+UNIQUE\s*,\s*$',
                     TABLE_DDL['photo'], re.M)


def test_photo_recent_index_lists_id_explicitly():
    index = re.search(r'INDEX photo_recent \((.+?)\)', TABLE_DDL['photo'])

    assert index, 'photo has no photo_recent index'
    assert [c.strip() for c in index.group(1).split(',')] == ['taken_at', 'id']


def test_taken_at_is_never_null():
    """The newest-first sort has one key; a null would sort unpredictably."""
    assert re.search(r'^\s*taken_at\s+DATETIME\s+NOT NULL', TABLE_DDL['photo'], re.M)


def test_photo_recent_index_matches_the_listing_sort():
    from photos.photos import SELECT_PAGE

    order_by = re.search(r'ORDER BY (.+?) LIMIT', SELECT_PAGE).group(1)
    sort_columns = [c.strip().split()[0] for c in order_by.split(',')]
    index = re.search(r'INDEX photo_recent \((.+?)\)', TABLE_DDL['photo'])

    assert [c.strip() for c in index.group(1).split(',')] == sort_columns
