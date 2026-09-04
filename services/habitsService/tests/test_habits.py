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


def test_rename_habit_changes_the_name(client):
    habit_id = client.post('/habits', json={'name': 'floss'}).get_json()['id']

    response = client.put(f'/habits/{habit_id}', json={'name': 'floss nightly'})

    assert response.status_code == 200
    assert response.get_json() == {'id': habit_id, 'name': 'floss nightly'}
    assert client.get('/habits').get_json()[0]['name'] == 'floss nightly'


def test_rename_habit_with_unknown_id_is_404_and_creates_nothing(client):
    response = client.put('/habits/not-a-real-id', json={'name': 'ghost'})

    assert response.status_code == 404
    # Body, not just status: Flask's router also 404s an unmatched path, so this
    # is what proves the response came from our handler rather than the router.
    assert 'not-a-real-id' in response.get_json()['error']
    assert client.get('/habits').get_json() == []


def test_rename_habit_without_a_name_is_rejected(client):
    habit_id = client.post('/habits', json={'name': 'floss'}).get_json()['id']

    response = client.put(f'/habits/{habit_id}', json={})

    assert response.status_code == 400
    assert client.get('/habits').get_json()[0]['name'] == 'floss'


def test_delete_habit_removes_it(client):
    habit_id = client.post('/habits', json={'name': 'floss'}).get_json()['id']

    response = client.delete(f'/habits/{habit_id}')

    assert response.status_code == 200
    assert client.get('/habits').get_json() == []


def test_delete_habit_with_unknown_id_is_404(client):
    response = client.delete('/habits/not-a-real-id')

    assert response.status_code == 404
    # Body, not just status: Flask's router also 404s, so this proves the
    # response came from our handler.
    assert 'not-a-real-id' in response.get_json()['error']


def test_delete_habit_leaves_no_completions_behind(client):
    habit_id = client.post('/habits', json={'name': 'floss'}).get_json()['id']
    for day in ('2026-09-01', '2026-09-02', '2026-09-03'):
        client.put(f'/habits/{habit_id}/completions/{day}')

    assert client.delete(f'/habits/{habit_id}').status_code == 200

    # GET /habits queries PK='HABIT' and would never surface a row at
    # PK='HABIT#<id>', so read the completion partition directly.
    import store

    assert store._completion_dates(habit_id, '2026-01-01', '2026-12-31') == []


def test_delete_habit_cascades_past_one_batch_write(client):
    """BatchWriteItem caps at 25 items, so a cascade must chunk correctly."""
    habit_id = client.post('/habits', json={'name': 'floss'}).get_json()['id']
    for day in range(1, 29):
        client.put(f'/habits/{habit_id}/completions/2026-09-{day:02d}')

    assert client.delete(f'/habits/{habit_id}').status_code == 200

    import store

    assert store._completion_dates(habit_id, '2026-01-01', '2026-12-31') == []


def test_cascade_never_sends_more_than_25_items_per_batch(client):
    """moto accepts oversized batches, so only the call args can prove chunking.

    Real BatchWriteItem caps at 25 and would raise ValidationException.
    """
    import store

    habit_id = client.post('/habits', json={'name': 'floss'}).get_json()['id']
    for day in range(1, 29):
        client.put(f'/habits/{habit_id}/completions/2026-09-{day:02d}')

    batch_sizes = []
    real_batch_write = store.dynamodb_client.batch_write_item

    def recording_batch_write(**kwargs):
        batch_sizes.append(len(kwargs['RequestItems'][store.LIVS_TABLE]))
        return real_batch_write(**kwargs)

    store.dynamodb_client.batch_write_item = recording_batch_write
    try:
        assert client.delete(f'/habits/{habit_id}').status_code == 200
    finally:
        store.dynamodb_client.batch_write_item = real_batch_write

    assert batch_sizes == [25, 3]
    assert max(batch_sizes) <= store.BATCH_WRITE_LIMIT


def test_cascade_gives_up_instead_of_retrying_forever(client):
    """A backend that never drains UnprocessedItems must not busy-loop."""
    import store

    habit_id = client.post('/habits', json={'name': 'floss'}).get_json()['id']
    client.put(f'/habits/{habit_id}/completions/2026-09-03')

    stuck = {
        'UnprocessedItems': {
            store.LIVS_TABLE: [
                {'DeleteRequest': {'Key': {'PK': {'S': 'x'}, 'SK': {'S': 'y'}}}}
            ]
        }
    }
    calls = []
    real_batch_write = store.dynamodb_client.batch_write_item

    def never_drains(**kwargs):
        calls.append(kwargs)
        return stuck

    store.dynamodb_client.batch_write_item = never_drains
    try:
        response = client.delete(f'/habits/{habit_id}')
    finally:
        store.dynamodb_client.batch_write_item = real_batch_write

    assert response.status_code == 500
    assert len(calls) == store.BATCH_WRITE_MAX_ATTEMPTS


def test_deleting_one_habit_leaves_another_habits_dates_alone(client):
    keep = client.post('/habits', json={'name': 'floss'}).get_json()['id']
    drop = client.post('/habits', json={'name': 'run'}).get_json()['id']
    client.put(f'/habits/{keep}/completions/2026-09-03')
    client.put(f'/habits/{drop}/completions/2026-09-03')

    client.delete(f'/habits/{drop}')

    body = client.get('/habits?from=2026-09-01&to=2026-09-30').get_json()
    assert body == [{'id': keep, 'name': 'floss', 'dates': ['2026-09-03']}]
