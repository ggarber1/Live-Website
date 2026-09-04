def test_create_habit_returns_id_and_name(client):
    response = client.post('/habits', json={'name': 'floss'})

    assert response.status_code == 201
    body = response.get_json()
    assert body['name'] == 'floss'
    assert body['id']


def test_create_habit_strips_surrounding_whitespace(client):
    response = client.post('/habits', json={'name': '  floss  '})

    assert response.status_code == 201
    assert response.get_json()['name'] == 'floss'


def test_create_habit_without_a_name_is_rejected(client):
    response = client.post('/habits', json={})

    assert response.status_code == 400
    assert 'name' in response.get_json()['error']


def test_create_habit_with_a_blank_name_is_rejected(client):
    response = client.post('/habits', json={'name': '   '})

    assert response.status_code == 400


def test_create_habit_without_a_json_body_is_rejected_not_crashed(client):
    response = client.post('/habits', data='name=floss')

    assert response.status_code == 400


def test_create_habit_with_a_non_object_json_body_is_rejected(client):
    """A JSON array parses fine but has no .get -- must be a 400, not a 500."""
    response = client.post('/habits', json=[1, 2, 3])

    assert response.status_code == 400
    assert response.get_json()['error']


def test_list_habits_is_empty_before_anything_is_created(client):
    response = client.get('/habits')

    assert response.status_code == 200
    assert response.get_json() == []


def test_list_habits_returns_created_habits_with_no_dates(client):
    client.post('/habits', json={'name': 'floss'})

    response = client.get('/habits')

    assert response.status_code == 200
    body = response.get_json()
    assert len(body) == 1
    assert body[0]['name'] == 'floss'
    assert body[0]['dates'] == []


def test_habits_may_share_a_name_and_stay_distinct(client):
    first = client.post('/habits', json={'name': 'floss'}).get_json()['id']
    second = client.post('/habits', json={'name': 'floss'}).get_json()['id']

    assert first != second
    assert len(client.get('/habits').get_json()) == 2


def test_list_habits_rejects_a_malformed_date_param(client):
    response = client.get('/habits?from=20260101')

    assert response.status_code == 400


def test_list_habits_rejects_a_reversed_range(client):
    response = client.get('/habits?from=2026-02-01&to=2026-01-01')

    assert response.status_code == 400


def test_query_all_follows_the_continuation_token(client, monkeypatch):
    """A Query returning LastEvaluatedKey must be followed, or dates go missing.

    Not reachable over HTTP without pushing a habit past 1MB, so the paginator
    is driven directly with a stubbed client.
    """
    import store

    pages = [
        {'Items': [{'SK': {'S': 'a'}}], 'LastEvaluatedKey': {'SK': {'S': 'a'}}},
        {'Items': [{'SK': {'S': 'b'}}]},
    ]
    calls = []

    def fake_query(**kwargs):
        calls.append(kwargs)
        return pages[len(calls) - 1]

    monkeypatch.setattr(store.dynamodb_client, 'query', fake_query)

    assert store._query_all(TableName='t') == [{'SK': {'S': 'a'}}, {'SK': {'S': 'b'}}]
    assert 'ExclusiveStartKey' not in calls[0]
    assert calls[1]['ExclusiveStartKey'] == {'SK': {'S': 'a'}}
