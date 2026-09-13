import pytest

import blog.blog
import habits.habits
import music.music
import recipes.recipes
import todo.todo
from app import app as flask_app

SERVICE_MODULES = (blog.blog, habits.habits, music.music,
                   recipes.recipes, todo.todo)


@pytest.fixture(autouse=True)
def db_env(monkeypatch):
    """Give every test a complete DB config.

    Autouse so no test depends on the developer's real .env, and so a test that
    reaches the connection layer fails on its stub rather than on config.
    """
    monkeypatch.setenv('DB_USER', 'test_user')
    monkeypatch.setenv('DB_PASSWORD', 'test_password')
    monkeypatch.setenv('DB_NAME', 'test_db')
    monkeypatch.delenv('DB_HOST', raising=False)
    monkeypatch.delenv('DB_PORT', raising=False)
    monkeypatch.setenv('MUSIC_DIR', '/tmp/livs-test-music')


class FakeWrites:
    """What the stubbed execute/insert return, plus the statements they were given."""

    def __init__(self):
        self.queries = []
        self.rowcount = 1
        self.new_id = 42


@pytest.fixture
def writes(monkeypatch):
    """Stub execute and insert in every service module and record their calls.

    Each service did `from database.db import execute, insert`, so the names
    have to be replaced per module, not just on database.db.
    """
    fake = FakeWrites()

    def fake_execute(query, params=None):
        fake.queries.append((query, params))
        return fake.rowcount

    def fake_insert(query, params=None):
        fake.queries.append((query, params))
        return fake.new_id

    for module in SERVICE_MODULES:
        # Only some service modules write. music imports just fetch_all/fetch_one.
        monkeypatch.setattr(module, 'execute', fake_execute, raising=False)
        monkeypatch.setattr(module, 'insert', fake_insert, raising=False)
    return fake


class FakeReads:
    """Rows the stubbed reads hand back, plus the SELECTs they were asked to run."""

    def __init__(self):
        self.rows = []
        self.row = None
        self.queries = []
        self.error = None


@pytest.fixture
def reads(monkeypatch):
    fake = FakeReads()

    def fake_fetch_all(query, params=None):
        fake.queries.append((query, params))
        if fake.error is not None:
            raise fake.error
        return fake.rows

    def fake_fetch_one(query, params=None):
        fake.queries.append((query, params))
        if fake.error is not None:
            raise fake.error
        return fake.row

    for module in SERVICE_MODULES:
        monkeypatch.setattr(module, 'fetch_all', fake_fetch_all)
        # Only habits imports fetch_one so far.
        monkeypatch.setattr(module, 'fetch_one', fake_fetch_one, raising=False)
    return fake


@pytest.fixture
def client():
    flask_app.config.update(TESTING=True)
    return flask_app.test_client()
