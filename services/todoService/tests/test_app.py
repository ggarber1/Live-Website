import pytest


def test_create_todo_returns_id(client):
    response = client.post('/todo', json={'todo': 'buy compost bin'})

    assert response.status_code == 201
    body = response.get_json()
    assert body['todo'] == 'buy compost bin'
    assert body['id']


def test_create_todo_without_text_is_rejected(client):
    response = client.post('/todo', json={})

    assert response.status_code == 400
    assert 'todo' in response.get_json()['error']


def test_get_todo_lists_created_items(client):
    created = [
        client.post('/todo', json={'todo': text}).get_json()
        for text in ('water plants', 'call mom')
    ]

    response = client.get('/todo')

    assert response.status_code == 200
    assert sorted(response.get_json(), key=lambda t: t['todo']) == sorted(
        created, key=lambda t: t['todo']
    )


def test_get_todo_is_empty_before_anything_is_created(client):
    response = client.get('/todo')

    assert response.status_code == 200
    assert response.get_json() == []


def test_update_todo_changes_the_text(client):
    todo_id = client.post('/todo', json={'todo': 'walk dog'}).get_json()['id']

    response = client.put('/todo', json={'id': todo_id, 'todo': 'walk dog twice'})

    assert response.status_code == 200
    assert client.get('/todo').get_json() == [
        {'id': todo_id, 'todo': 'walk dog twice'}
    ]


def test_update_todo_with_unknown_id_is_404_and_creates_nothing(client):
    response = client.put('/todo', json={'id': 'not-a-real-id', 'todo': 'ghost'})

    assert response.status_code == 404
    assert client.get('/todo').get_json() == []


def test_update_todo_without_id_is_rejected(client):
    response = client.put('/todo', json={'todo': 'no id here'})

    assert response.status_code == 400


def test_delete_todo_removes_the_item(client):
    todo_id = client.post('/todo', json={'todo': 'take out trash'}).get_json()['id']

    response = client.delete('/todo', json={'id': todo_id})

    assert response.status_code == 200
    assert client.get('/todo').get_json() == []


def test_delete_todo_with_unknown_id_is_404(client):
    response = client.delete('/todo', json={'id': 'not-a-real-id'})

    assert response.status_code == 404


def test_request_without_json_body_is_rejected_not_crashed(client):
    response = client.post('/todo', data='todo=plain+text')

    assert response.status_code == 400


@pytest.mark.parametrize('method', ['post', 'put', 'delete'])
def test_non_object_json_body_is_rejected_not_crashed(client, method):
    """A JSON array parses fine but has no .get -- must be a 400, not a 500."""
    response = getattr(client, method)('/todo', json=[1, 2, 3])

    assert response.status_code == 400
    assert response.get_json()['error']
