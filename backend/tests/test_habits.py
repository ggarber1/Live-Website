import datetime

import pytest

from habits.habits import next_streak

TODAY = datetime.date(2026, 9, 5)
YESTERDAY = datetime.date(2026, 9, 4)


class TestNextStreak:
    def test_never_completed_starts_at_one(self):
        assert next_streak(None, 0, TODAY) == 1

    def test_completed_yesterday_continues_the_streak(self):
        assert next_streak(YESTERDAY, 4, TODAY) == 5

    def test_completed_today_leaves_the_streak_alone(self):
        assert next_streak(TODAY, 4, TODAY) == 4

    def test_two_day_gap_starts_over(self):
        assert next_streak(datetime.date(2026, 9, 3), 9, TODAY) == 1

    def test_long_gap_starts_over(self):
        assert next_streak(datetime.date(2025, 1, 1), 300, TODAY) == 1

    def test_streak_survives_a_month_boundary(self):
        assert next_streak(datetime.date(2026, 8, 31), 7, datetime.date(2026, 9, 1)) == 8

    def test_streak_survives_a_leap_day(self):
        assert next_streak(datetime.date(2028, 2, 29), 2, datetime.date(2028, 3, 1)) == 3


@pytest.fixture
def habit(reads):
    """An existing habit, completed yesterday with a streak of 4."""
    reads.row = {
        'id': 3,
        'name': 'floss',
        'streak': 4,
        'last_completed': datetime.date.today() - datetime.timedelta(days=1),
        'created_at': datetime.datetime(2026, 9, 1, 8, 0),
    }
    return reads.row


def test_complete_returns_the_updated_habit(client, habit, writes):
    res = client.post('/habits/3/complete')

    assert res.status_code == 200
    body = res.get_json()
    assert body['id'] == 3
    assert body['name'] == 'floss'
    assert body['streak'] == 5


def test_complete_writes_the_new_streak_and_today(client, habit, writes):
    client.post('/habits/3/complete')

    query, params = writes.queries[0]
    assert query == "UPDATE habits SET streak = ?, last_completed = ? WHERE id = ?"
    assert params == (5, datetime.date.today(), 3)


def test_complete_is_idempotent_within_a_day(client, reads, writes):
    reads.row = {
        'id': 3,
        'name': 'floss',
        'streak': 4,
        'last_completed': datetime.date.today(),
        'created_at': datetime.datetime(2026, 9, 1, 8, 0),
    }

    res = client.post('/habits/3/complete')

    assert res.get_json()['streak'] == 4
    _, params = writes.queries[0]
    assert params == (4, datetime.date.today(), 3)


def test_complete_404s_for_an_unknown_habit(client, reads, writes):
    reads.row = None

    res = client.post('/habits/99/complete')

    assert res.status_code == 404
    assert 'no habit with id 99' in res.get_json()['error']
    assert writes.queries == []


def test_complete_looks_the_habit_up_by_id(client, habit, reads, writes):
    client.post('/habits/3/complete')

    query, params = reads.queries[0]
    assert query == "SELECT * FROM habits WHERE id = ? LIMIT 1"
    assert params == (3,)


def test_complete_rejects_a_non_integer_id(client, reads, writes):
    res = client.post('/habits/abc/complete')

    assert res.status_code == 404
    assert writes.queries == []
