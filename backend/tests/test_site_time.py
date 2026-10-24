import datetime
from zoneinfo import ZoneInfo

import pytest

from site_time import site_timezone, site_today

UTC = datetime.timezone.utc


@pytest.fixture(autouse=True)
def no_zone_override(monkeypatch):
    monkeypatch.delenv('LIVS_TIMEZONE', raising=False)


def test_defaults_to_eastern():
    assert site_timezone() == ZoneInfo('America/New_York')


def test_ten_at_night_eastern_is_still_that_day():
    """02:06 UTC on the 24th is 10:06pm on the 23rd in New York."""
    assert site_today(datetime.datetime(2026, 10, 24, 2, 6, tzinfo=UTC)) == datetime.date(2026, 10, 23)


def test_the_day_turns_over_at_local_midnight():
    assert site_today(datetime.datetime(2026, 10, 24, 4, 0, tzinfo=UTC)) == datetime.date(2026, 10, 24)


def test_winter_time_is_five_hours_behind():
    assert site_today(datetime.datetime(2026, 1, 15, 4, 59, tzinfo=UTC)) == datetime.date(2026, 1, 14)


def test_the_zone_can_be_overridden(monkeypatch):
    monkeypatch.setenv('LIVS_TIMEZONE', 'Asia/Tokyo')

    assert site_today(datetime.datetime(2026, 10, 23, 20, 0, tzinfo=UTC)) == datetime.date(2026, 10, 24)


def test_without_an_argument_it_is_a_real_date():
    assert isinstance(site_today(), datetime.date)


@pytest.mark.parametrize('name', ['Mars/Olympus_Mons', '../../etc/passwd', 'not a zone'])
def test_an_unknown_zone_names_the_variable(monkeypatch, name):
    monkeypatch.setenv('LIVS_TIMEZONE', name)

    with pytest.raises(RuntimeError) as err:
        site_timezone()

    assert 'LIVS_TIMEZONE' in str(err.value)
