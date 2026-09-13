import pathlib

import mariadb
import pytest

from app import app as flask_app
from database import db


class FakeCursor:
    def __init__(self, dictionary=False):
        self.dictionary = dictionary
        self.calls = []
        self.closed = False
        self.rowcount = 1
        self.lastrowid = 7
        self.rows = []
        self.error = None

    def execute(self, query, params=None):
        self.calls.append((query, params))
        if self.error is not None:
            raise self.error

    def fetchall(self):
        return self.rows

    def close(self):
        self.closed = True


class FakeConnection:
    def __init__(self):
        self.actions = []
        self.cursors = []
        self.closed = False
        # Seeded onto every cursor this connection hands out, so a test can set
        # them up before the code under test creates its own cursor.
        self.cursor_error = None
        self.cursor_rows = []
        self.cursor_rowcount = 1
        self.cursor_lastrowid = 7

    def cursor(self, dictionary=False, **kwargs):
        cursor = FakeCursor(dictionary=dictionary)
        cursor.error = self.cursor_error
        cursor.rows = self.cursor_rows
        cursor.rowcount = self.cursor_rowcount
        cursor.lastrowid = self.cursor_lastrowid
        self.cursors.append(cursor)
        return cursor

    def commit(self):
        self.actions.append('commit')

    def rollback(self):
        self.actions.append('rollback')

    def close(self):
        self.closed = True


@pytest.fixture
def connections(monkeypatch):
    """Replace mariadb.connect and hand back every connection it produced."""
    created = []

    def fake_connect(**kwargs):
        conn = FakeConnection()
        conn.config = kwargs
        created.append(conn)
        return conn

    monkeypatch.setattr(db.mariadb, 'connect', fake_connect)
    return created


class TestDbConfig:
    def test_reads_credentials_from_the_environment(self, monkeypatch):
        monkeypatch.setenv('DB_USER', 'liv')
        monkeypatch.setenv('DB_PASSWORD', 'hunter2')
        monkeypatch.setenv('DB_NAME', 'livs')

        config = db.db_config()

        assert config['user'] == 'liv'
        assert config['password'] == 'hunter2'
        assert config['database'] == 'livs'

    def test_host_and_port_have_defaults(self):
        config = db.db_config()

        assert config['host'] == 'localhost'
        assert config['port'] == 3306

    def test_host_and_port_are_overridable(self, monkeypatch):
        monkeypatch.setenv('DB_HOST', '10.0.0.5')
        monkeypatch.setenv('DB_PORT', '3307')

        config = db.db_config()

        assert config['host'] == '10.0.0.5'
        assert config['port'] == 3307

    def test_port_is_an_int_not_a_string(self, monkeypatch):
        monkeypatch.setenv('DB_PORT', '3307')

        assert isinstance(db.db_config()['port'], int)

    @pytest.mark.parametrize('name', db.REQUIRED_ENV)
    def test_missing_credential_names_the_variable(self, monkeypatch, name):
        monkeypatch.delenv(name)

        with pytest.raises(RuntimeError) as err:
            db.db_config()

        assert name in str(err.value)

    @pytest.mark.parametrize('name', db.REQUIRED_ENV)
    def test_blank_credential_is_treated_as_missing(self, monkeypatch, name):
        monkeypatch.setenv(name, '')

        with pytest.raises(RuntimeError) as err:
            db.db_config()

        assert name in str(err.value)

    def test_no_placeholder_credentials_remain(self):
        source = (pathlib.Path(db.__file__)).read_text()

        assert 'your_username' not in source
        assert 'your_password' not in source


def test_connection_uses_the_configured_credentials(connections):
    with flask_app.app_context():
        db.get_connection()

    assert connections[0].config['user'] == 'test_user'
    assert connections[0].config['database'] == 'test_db'


@pytest.fixture
def conn(connections):
    """A single request-scoped connection, with an app context pushed."""
    with flask_app.app_context():
        yield db.get_connection()


def test_connection_is_reused_within_one_request(connections):
    with flask_app.app_context():
        first = db.get_connection()
        second = db.get_connection()

    assert first is second
    assert len(connections) == 1


def test_each_request_gets_its_own_connection(connections):
    with flask_app.app_context():
        db.get_connection()
    with flask_app.app_context():
        db.get_connection()

    assert len(connections) == 2
    assert connections[0] is not connections[1]


def test_connection_is_closed_when_the_request_ends(connections):
    with flask_app.app_context():
        db.get_connection()
        assert not connections[0].closed

    assert connections[0].closed


def test_teardown_is_a_noop_when_no_connection_was_opened(connections):
    with flask_app.app_context():
        pass

    assert connections == []


def test_execute_commits(conn):
    db.execute("UPDATE todo SET task = ? WHERE id = ?", ('milk', 3))

    cursor = conn.cursors[0]
    assert cursor.calls == [("UPDATE todo SET task = ? WHERE id = ?", ('milk', 3))]
    assert conn.actions == ['commit']


def test_execute_returns_rows_affected(conn):
    conn.cursor_rowcount = 3

    assert db.execute("DELETE FROM todo WHERE id < ?", (99,)) == 3


def test_execute_returns_zero_when_nothing_matched(conn):
    conn.cursor_rowcount = 0

    assert db.execute("DELETE FROM todo WHERE id = ?", (99,)) == 0


def test_execute_passes_empty_params_when_none_given(conn):
    db.execute("CREATE TABLE IF NOT EXISTS todo (id INT)")

    assert conn.cursors[0].calls == [("CREATE TABLE IF NOT EXISTS todo (id INT)", ())]
    assert conn.actions == ['commit']


def test_execute_closes_its_cursor(conn):
    db.execute("DELETE FROM todo WHERE id = ?", (1,))

    assert conn.cursors[0].closed


def test_execute_rolls_back_and_reraises_on_error(conn):
    conn.cursor_error = mariadb.Error('duplicate key')

    with pytest.raises(mariadb.Error):
        db.execute("INSERT INTO todo (task) VALUES (?)", ('milk',))

    assert conn.actions == ['rollback']
    assert conn.cursors[0].closed


def test_insert_commits_and_returns_new_id(conn):
    conn.cursor_lastrowid = 12

    assert db.insert("INSERT INTO todo (task) VALUES (?)", ('milk',)) == 12
    assert conn.actions == ['commit']


def test_insert_rolls_back_and_reraises_on_error(conn):
    conn.cursor_error = mariadb.Error('column missing')

    with pytest.raises(mariadb.Error):
        db.insert("INSERT INTO todo (nope) VALUES (?)", ('milk',))

    assert conn.actions == ['rollback']


def test_fetch_all_returns_rows_from_a_dictionary_cursor(conn):
    conn.cursor_rows = [{'id': 1, 'task': 'milk'}]

    rows = db.fetch_all("SELECT * FROM todo ORDER BY id")

    assert rows == [{'id': 1, 'task': 'milk'}]
    assert conn.cursors[0].dictionary is True
    assert conn.cursors[0].closed
    assert conn.actions == []


def test_fetch_all_reraises_and_closes_cursor_on_error(conn):
    conn.cursor_error = mariadb.Error('no such table')

    with pytest.raises(mariadb.Error):
        db.fetch_all("SELECT * FROM todo")

    assert conn.cursors[0].closed
