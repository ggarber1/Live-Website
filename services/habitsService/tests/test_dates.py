from datetime import datetime, timedelta, timezone

import pytest

from dates import DEFAULT_WINDOW_DAYS, InvalidDate, canonical_date, resolve_window


def test_canonical_date_accepts_canonical_iso():
    assert canonical_date('2026-09-03') == '2026-09-03'


@pytest.mark.parametrize(
    'value',
    [
        '20260903',
        '2026-9-3',
        '03/09/2026',
        'today',
        '',
        '2026-13-01',
        '2026-W36-4',
        '2026-246',
    ],
)
def test_canonical_date_rejects_anything_non_canonical(value):
    with pytest.raises(InvalidDate):
        canonical_date(value)


def test_canonical_date_rejects_non_string():
    with pytest.raises(InvalidDate):
        canonical_date(None)


def test_resolve_window_uses_both_params_when_given():
    assert resolve_window('2026-01-01', '2026-01-31') == ('2026-01-01', '2026-01-31')


def test_resolve_window_allows_a_single_day_range():
    assert resolve_window('2026-01-05', '2026-01-05') == ('2026-01-05', '2026-01-05')


def test_resolve_window_defaults_from_to_a_window_ending_at_to():
    # 30 days inclusive of both ends, so Jan 31 back to Jan 2.
    assert resolve_window(None, '2026-01-31') == ('2026-01-02', '2026-01-31')


def test_resolve_window_defaults_to_to_utc_today():
    today = datetime.now(timezone.utc).date()
    from_date, to_date = resolve_window(None, None)

    assert to_date == today.isoformat()
    assert from_date == (today - timedelta(days=DEFAULT_WINDOW_DAYS - 1)).isoformat()


def test_resolve_window_keeps_explicit_from_with_default_to():
    today = datetime.now(timezone.utc).date()

    assert resolve_window('2026-01-01', None) == ('2026-01-01', today.isoformat())


def test_resolve_window_rejects_a_reversed_range():
    with pytest.raises(InvalidDate):
        resolve_window('2026-02-01', '2026-01-01')


def test_resolve_window_rejects_a_malformed_param():
    with pytest.raises(InvalidDate):
        resolve_window('20260101', '2026-01-31')


def test_resolve_window_rejects_a_malformed_to():
    with pytest.raises(InvalidDate):
        resolve_window('2026-01-01', '20260131')


def test_resolve_window_rejects_an_empty_from():
    with pytest.raises(InvalidDate):
        resolve_window('', '2026-01-31')


def test_resolve_window_rejects_an_empty_to():
    with pytest.raises(InvalidDate):
        resolve_window('2026-01-01', '')
