from datetime import datetime, timedelta, timezone

import pytest


@pytest.fixture
def habit_id(client):
    return client.post('/habits', json={'name': 'floss'}).get_json()['id']


def _dates_for(client, habit_id, query=''):
    body = client.get(f'/habits{query}').get_json()
    match = next((habit for habit in body if habit['id'] == habit_id), None)
    assert match is not None, f'habit {habit_id} missing from {body}'
    return match['dates']


def test_mark_done_records_the_date(client, habit_id):
    response = client.put(f'/habits/{habit_id}/completions/2026-09-03')

    assert response.status_code == 200
    assert response.get_json() == {'id': habit_id, 'date': '2026-09-03'}
    assert _dates_for(
        client, habit_id, '?from=2026-09-01&to=2026-09-30'
    ) == ['2026-09-03']


def test_mark_done_twice_leaves_exactly_one_date(client, habit_id):
    first = client.put(f'/habits/{habit_id}/completions/2026-09-03')
    second = client.put(f'/habits/{habit_id}/completions/2026-09-03')

    assert first.status_code == 200
    assert second.status_code == 200
    assert _dates_for(
        client, habit_id, '?from=2026-09-01&to=2026-09-30'
    ) == ['2026-09-03']


def test_dates_come_back_sorted_ascending(client, habit_id):
    for day in ('2026-09-07', '2026-09-02', '2026-09-05'):
        client.put(f'/habits/{habit_id}/completions/{day}')

    assert _dates_for(client, habit_id, '?from=2026-09-01&to=2026-09-30') == [
        '2026-09-02',
        '2026-09-05',
        '2026-09-07',
    ]


def test_window_boundaries_are_inclusive(client, habit_id):
    for day in ('2026-09-01', '2026-09-15', '2026-09-30'):
        client.put(f'/habits/{habit_id}/completions/{day}')

    assert _dates_for(client, habit_id, '?from=2026-09-01&to=2026-09-30') == [
        '2026-09-01',
        '2026-09-15',
        '2026-09-30',
    ]


def test_dates_outside_the_window_are_excluded(client, habit_id):
    client.put(f'/habits/{habit_id}/completions/2026-08-31')
    client.put(f'/habits/{habit_id}/completions/2026-09-15')
    client.put(f'/habits/{habit_id}/completions/2026-10-01')

    assert _dates_for(
        client, habit_id, '?from=2026-09-01&to=2026-09-30'
    ) == ['2026-09-15']


def test_default_window_is_the_last_30_days(client, habit_id):
    today = datetime.now(timezone.utc).date()
    inside = today - timedelta(days=5)
    outside = today - timedelta(days=40)
    client.put(f'/habits/{habit_id}/completions/{inside.isoformat()}')
    client.put(f'/habits/{habit_id}/completions/{outside.isoformat()}')

    assert _dates_for(client, habit_id) == [inside.isoformat()]


def test_future_dates_are_allowed(client, habit_id):
    """Rejecting them would need a trusted server-side "today", which this
    design deliberately does not rely on."""
    future = (datetime.now(timezone.utc).date() + timedelta(days=30)).isoformat()

    response = client.put(f'/habits/{habit_id}/completions/{future}')

    assert response.status_code == 200
    assert _dates_for(client, habit_id, f'?from={future}&to={future}') == [future]


def test_mark_done_rejects_a_non_canonical_date(client, habit_id):
    response = client.put(f'/habits/{habit_id}/completions/20260903')

    assert response.status_code == 400
    assert _dates_for(client, habit_id, '?from=2026-09-01&to=2026-09-30') == []


def test_mark_done_on_unknown_habit_is_404_and_writes_nothing(client):
    response = client.put('/habits/not-a-real-id/completions/2026-09-03')

    assert response.status_code == 404
    # GET /habits queries PK='HABIT' and would never surface a row at
    # PK='HABIT#not-a-real-id', so read the completion partition directly --
    # otherwise this assertion passes whether or not an orphan was written.
    import store

    assert store._completion_dates('not-a-real-id', '2026-01-01', '2026-12-31') == []


def test_unmark_done_removes_the_date(client, habit_id):
    client.put(f'/habits/{habit_id}/completions/2026-09-03')

    response = client.delete(f'/habits/{habit_id}/completions/2026-09-03')

    assert response.status_code == 200
    assert _dates_for(client, habit_id, '?from=2026-09-01&to=2026-09-30') == []


def test_unmark_done_is_idempotent_when_never_marked(client, habit_id):
    response = client.delete(f'/habits/{habit_id}/completions/2026-09-03')

    assert response.status_code == 200


def test_unmark_done_on_unknown_habit_is_404(client):
    response = client.delete('/habits/not-a-real-id/completions/2026-09-03')

    assert response.status_code == 404


def test_unmark_done_rejects_a_non_canonical_date(client, habit_id):
    response = client.delete(f'/habits/{habit_id}/completions/20260903')

    assert response.status_code == 400


def test_habit_exists_uses_a_strongly_consistent_read(client, habit_id):
    """moto is always strongly consistent, so only the call args can prove this.

    Without ConsistentRead, marking a habit done right after creating it can
    404 on a habit that exists.
    """
    import store

    calls = []
    real_get_item = store.dynamodb_client.get_item

    def recording_get_item(**kwargs):
        calls.append(kwargs)
        return real_get_item(**kwargs)

    store.dynamodb_client.get_item = recording_get_item
    try:
        assert store.habit_exists(habit_id) is True
    finally:
        store.dynamodb_client.get_item = real_get_item

    assert calls[0]['ConsistentRead'] is True


def test_store_rejects_a_non_canonical_date_even_when_called_directly(client, habit_id):
    """app.py validates too, but store owns the sort-key invariant."""
    import dates
    import store

    with pytest.raises(dates.InvalidDate):
        store.mark_done(habit_id, '20260903')

    assert store._completion_dates(habit_id, '2026-01-01', '2026-12-31') == []
