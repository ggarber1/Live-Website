import json

import pytest
from werkzeug.exceptions import BadRequest

from app import app as flask_app
from recipes.recipes import from_json_columns, to_json_column

VALID_BODY = {'title': 'toast', 'ingredients': ['bread'], 'instructions': ['toast it']}


class TestToJsonColumn:
    def test_serializes_an_array_of_strings(self):
        assert to_json_column('ingredients', ['bread', 'jam']) == '["bread", "jam"]'

    def test_empty_array_is_fine(self):
        assert to_json_column('ingredients', []) == '[]'

    @pytest.mark.parametrize('bad', [
        '["bread"]',        # the old pre-serialized form
        'bread',
        {'a': 1},
        None,
        42,
        ['bread', 7],       # not all strings
    ])
    def test_rejects_anything_but_an_array_of_strings(self, bad):
        with flask_app.test_request_context():
            with pytest.raises(BadRequest) as err:
                to_json_column('ingredients', bad)

        assert 'ingredients must be an array of strings' in err.value.description


class TestFromJsonColumns:
    def test_decodes_bytes_as_mysql_returns_them(self):
        row = {'id': 1, 'ingredients': b'["bread"]', 'instructions': b'["toast it"]'}

        assert from_json_columns(row)['ingredients'] == ['bread']

    def test_decodes_str_as_mariadb_returns_them(self):
        row = {'id': 1, 'ingredients': '["bread"]', 'instructions': '["toast it"]'}

        assert from_json_columns(row)['ingredients'] == ['bread']

    def test_leaves_other_columns_alone(self):
        row = {'id': 1, 'title': 'toast', 'ingredients': b'[]', 'instructions': b'[]'}

        decoded = from_json_columns(row)

        assert decoded['id'] == 1
        assert decoded['title'] == 'toast'

    def test_does_not_mutate_the_input_row(self):
        row = {'id': 1, 'ingredients': b'["bread"]', 'instructions': b'[]'}

        from_json_columns(row)

        assert row['ingredients'] == b'["bread"]'

    def test_tolerates_a_missing_column(self):
        assert from_json_columns({'id': 1})['id'] == 1


def test_get_returns_arrays_not_bytes(client, reads):
    reads.rows = [{
        'id': 1, 'title': 'toast',
        'ingredients': b'["bread"]', 'instructions': b'["toast it"]',
    }]

    res = client.get('/api/recipes')

    assert res.status_code == 200
    assert res.get_json()[0]['ingredients'] == ['bread']
    assert res.get_json()[0]['instructions'] == ['toast it']


def test_create_stores_serialized_json(client, writes):
    res = client.post('/api/recipes', json=VALID_BODY)

    assert res.status_code == 201
    _, params = writes.queries[0]
    assert params[1] == '["bread"]'
    assert json.loads(params[1]) == ['bread']


@pytest.mark.parametrize('field', ['ingredients', 'instructions'])
def test_create_rejects_a_pre_serialized_string(client, writes, field):
    body = {**VALID_BODY, field: '["bread"]'}

    res = client.post('/api/recipes', json=body)

    assert res.status_code == 400
    assert f'{field} must be an array of strings' in res.get_json()['error']
    assert writes.queries == []


def test_update_stores_serialized_json(client, writes):
    res = client.put('/api/recipes/1', json=VALID_BODY)

    assert res.status_code == 204
    _, params = writes.queries[0]
    assert params[1] == '["bread"]'


def test_update_rejects_a_bad_array(client, writes):
    res = client.put('/api/recipes/1', json={**VALID_BODY, 'ingredients': 'bread'})

    assert res.status_code == 400
    assert writes.queries == []
