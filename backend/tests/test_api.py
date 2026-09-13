import datetime

import mariadb
import pytest

LIST_PATHS = ['/todo', '/habits', '/blog', '/recipes']

CREATE_CASES = [
    ('/todo', {'task': 'buy milk'}, ('buy milk',)),
    ('/habits', {'name': 'floss'}, ('floss',)),
    ('/blog', {'title': 'hi', 'content': 'there'}, ('hi', 'there')),
    (
        # The API takes real arrays; the route serializes them for storage.
        '/recipes',
        {'title': 'toast', 'ingredients': ['bread'], 'instructions': ['toast it']},
        ('toast', '["bread"]', '["toast it"]'),
    ),
]


@pytest.mark.parametrize('path', LIST_PATHS)
def test_list_returns_rows_as_json(client, reads, path):
    reads.rows = [{'id': 1, 'title': 'first'}, {'id': 2, 'title': 'second'}]

    res = client.get(path)

    assert res.status_code == 200
    assert res.mimetype == 'application/json'
    assert res.get_json() == reads.rows


@pytest.mark.parametrize('path', LIST_PATHS)
def test_list_runs_a_select(client, reads, path):
    client.get(path)

    query, params = reads.queries[0]
    assert query.startswith('SELECT * FROM')
    assert params is None


@pytest.mark.parametrize('path', LIST_PATHS)
def test_list_returns_empty_array_when_no_rows(client, reads, path):
    reads.rows = []

    res = client.get(path)

    assert res.status_code == 200
    assert res.get_json() == []


@pytest.mark.parametrize('path', LIST_PATHS)
def test_list_serializes_timestamps(client, reads, path):
    reads.rows = [{'id': 1, 'created_at': datetime.datetime(2026, 9, 5, 12, 30)}]

    res = client.get(path)

    assert res.status_code == 200
    assert res.get_json()[0]['created_at'].startswith('Sat, 05 Sep 2026')


@pytest.mark.parametrize('path', LIST_PATHS)
def test_list_does_not_swallow_query_errors(client, reads, path):
    reads.error = mariadb.Error('table is gone')

    with pytest.raises(mariadb.Error):
        client.get(path)


@pytest.mark.parametrize('path,body,expected_params', CREATE_CASES)
def test_create_passes_body_fields_to_query(client, writes, path, body, expected_params):
    res = client.post(path, json=body)

    assert res.status_code == 201
    assert len(writes.queries) == 1
    query, params = writes.queries[0]
    assert query.startswith('INSERT INTO')
    assert params == expected_params


@pytest.mark.parametrize('path,body,expected_params', CREATE_CASES)
def test_create_returns_new_id(client, writes, path, body, expected_params):
    writes.new_id = 99

    res = client.post(path, json=body)

    assert res.status_code == 201
    assert res.get_json() == {'id': 99}


@pytest.mark.parametrize('path,body,expected_params', CREATE_CASES)
def test_update_passes_url_id_and_body_fields_to_query(
    client, writes, path, body, expected_params
):
    res = client.put(f'{path}/7', json=body)

    assert res.status_code == 204
    query, params = writes.queries[0]
    assert query.startswith('UPDATE')
    assert params == (*expected_params, 7)


@pytest.mark.parametrize('path,body,expected_params', CREATE_CASES)
def test_update_404s_when_no_row_matched(client, writes, path, body, expected_params):
    writes.rowcount = 0

    res = client.put(f'{path}/7', json=body)

    assert res.status_code == 404
    assert 'id 7' in res.get_json()['error']


@pytest.mark.parametrize('path', LIST_PATHS)
def test_delete_passes_url_id_to_query(client, writes, path):
    res = client.delete(f'{path}/7')

    assert res.status_code == 204
    query, params = writes.queries[0]
    assert query.startswith('DELETE FROM')
    assert params == (7,)


@pytest.mark.parametrize('path', LIST_PATHS)
def test_delete_404s_when_no_row_matched(client, writes, path):
    writes.rowcount = 0

    res = client.delete(f'{path}/7')

    assert res.status_code == 404
    assert 'id 7' in res.get_json()['error']


@pytest.mark.parametrize('path,body,expected_params', CREATE_CASES)
def test_create_rejects_missing_fields(client, writes, path, body, expected_params):
    res = client.post(path, json={})

    assert res.status_code == 400
    assert 'missing fields' in res.get_json()['error']
    assert writes.queries == []


@pytest.mark.parametrize('path', LIST_PATHS)
def test_create_rejects_non_object_body(client, writes, path):
    res = client.post(path, json=['not', 'an', 'object'])

    assert res.status_code == 400
    assert res.get_json()['error'] == 'expected a JSON object body'
    assert writes.queries == []


@pytest.mark.parametrize('path', LIST_PATHS)
def test_create_rejects_missing_body(client, writes, path):
    res = client.post(path)

    assert res.status_code == 400
    assert writes.queries == []


@pytest.mark.parametrize('path', LIST_PATHS)
def test_update_rejects_non_integer_id(client, writes, path):
    res = client.put(f'{path}/abc', json={'task': 'x', 'name': 'x'})

    assert res.status_code == 404
    assert writes.queries == []
