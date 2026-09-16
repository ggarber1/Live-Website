"""Round trips against a real database.

Every other test stubs the database out, which is exactly why they all passed
while GET /recipes returned a 500 for any row that existed: MySQL hands JSON
columns back as bytes, and no stub ever produced bytes. These tests exist so
driver-level type behaviour can't hide again.

Deselected by default (see pytest.ini). Run with:  pytest -m integration
"""
import datetime

import mariadb
import pytest
from dotenv import load_dotenv

from app import app as flask_app
from database import db

pytestmark = pytest.mark.integration

load_dotenv()


@pytest.fixture(autouse=True)
def real_env(monkeypatch):
    """Undo conftest's fake DB_* values so we hit the configured database."""
    monkeypatch.undo()
    load_dotenv(override=True)


@pytest.fixture
def live_db(real_env):
    """Skip cleanly when there's no reachable database."""
    try:
        with flask_app.app_context():
            db.fetch_all("SELECT 1")
    except (mariadb.Error, RuntimeError) as err:
        pytest.skip(f"no database available: {err}")


@pytest.fixture
def client(live_db):
    flask_app.config.update(TESTING=True)
    return flask_app.test_client()


@pytest.fixture
def cleanup(live_db):
    """Delete whatever a test created, whether or not it passed."""
    created = []
    yield created
    with flask_app.app_context():
        for table, row_id in created:
            db.execute(f"DELETE FROM {table} WHERE id = ?", (row_id,))


def test_recipe_round_trips_as_real_arrays(client, cleanup):
    body = {
        'title': 'toast',
        'ingredients': ['bread', 'butter'],
        'instructions': ['toast the bread', 'butter it'],
    }

    res = client.post('/api/recipes', json=body)
    assert res.status_code == 201, res.get_data(as_text=True)
    recipe_id = res.get_json()['id']
    cleanup.append(('recipes', recipe_id))

    listed = client.get('/api/recipes')
    assert listed.status_code == 200, listed.get_data(as_text=True)

    row = next(r for r in listed.get_json() if r['id'] == recipe_id)
    assert row['ingredients'] == ['bread', 'butter']
    assert row['instructions'] == ['toast the bread', 'butter it']
    assert row['title'] == 'toast'


def test_recipe_list_does_not_500_with_rows_present(client, cleanup):
    """The original bug: one stored recipe took down the whole list endpoint."""
    res = client.post('/api/recipes', json={
        'title': 'x', 'ingredients': ['a'], 'instructions': ['b'],
    })
    cleanup.append(('recipes', res.get_json()['id']))

    assert client.get('/api/recipes').status_code == 200


def test_recipe_update_round_trips(client, cleanup):
    res = client.post('/api/recipes', json={
        'title': 'x', 'ingredients': ['a'], 'instructions': ['b'],
    })
    recipe_id = res.get_json()['id']
    cleanup.append(('recipes', recipe_id))

    assert client.put(f'/api/recipes/{recipe_id}', json={
        'title': 'y', 'ingredients': ['c', 'd'], 'instructions': ['e'],
    }).status_code == 204

    row = next(r for r in client.get('/api/recipes').get_json() if r['id'] == recipe_id)
    assert row['ingredients'] == ['c', 'd']


def test_empty_arrays_round_trip(client, cleanup):
    res = client.post('/api/recipes', json={
        'title': 'empty', 'ingredients': [], 'instructions': [],
    })
    cleanup.append(('recipes', res.get_json()['id']))

    row = next(r for r in client.get('/api/recipes').get_json()
               if r['id'] == cleanup[0][1])
    assert row['ingredients'] == []


def test_unicode_survives_the_json_column(client, cleanup):
    res = client.post('/api/recipes', json={
        'title': 'crème brûlée', 'ingredients': ['crème', 'sucre'], 'instructions': ['brûler'],
    })
    cleanup.append(('recipes', res.get_json()['id']))

    row = next(r for r in client.get('/api/recipes').get_json() if r['id'] == cleanup[0][1])
    assert row['ingredients'] == ['crème', 'sucre']
    assert row['title'] == 'crème brûlée'


def test_todo_write_actually_commits(client, cleanup):
    res = client.post('/api/todo', json={'task': 'integration probe'})
    todo_id = res.get_json()['id']
    cleanup.append(('todo', todo_id))

    # A separate request means a separate connection: only a committed row shows.
    rows = client.get('/api/todo').get_json()
    assert any(r['id'] == todo_id and r['task'] == 'integration probe' for r in rows)


def test_habit_streak_advances_across_days(client, cleanup):
    res = client.post('/api/habits', json={'name': 'integration probe'})
    habit_id = res.get_json()['id']
    cleanup.append(('habits', habit_id))

    assert client.post(f'/api/habits/{habit_id}/complete').get_json()['streak'] == 1
    assert client.post(f'/api/habits/{habit_id}/complete').get_json()['streak'] == 1

    with flask_app.app_context():
        db.execute("UPDATE habits SET last_completed = ? WHERE id = ?",
                   (datetime.date.today() - datetime.timedelta(days=1), habit_id))

    assert client.post(f'/api/habits/{habit_id}/complete').get_json()['streak'] == 2

    with flask_app.app_context():
        db.execute("UPDATE habits SET last_completed = ? WHERE id = ?",
                   (datetime.date.today() - datetime.timedelta(days=5), habit_id))

    assert client.post(f'/api/habits/{habit_id}/complete').get_json()['streak'] == 1


def test_blog_round_trips(client, cleanup):
    res = client.post('/api/blog', json={'title': 'probe', 'content': 'body'})
    post_id = res.get_json()['id']
    cleanup.append(('blog', post_id))

    row = next(r for r in client.get('/api/blog').get_json() if r['id'] == post_id)
    assert row['content'] == 'body'
