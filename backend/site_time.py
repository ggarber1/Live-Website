"""What day it is for the people using the site, not for the server.

The server's clock runs in UTC, so its date turns over at 8pm Eastern.
Anything counted in calendar days (habit streaks) asks here instead.
"""
import datetime
import os
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

DEFAULT_TIMEZONE = 'America/New_York'


def site_timezone():
    """The zone named by LIVS_TIMEZONE, or Eastern when it is unset."""
    name = os.environ.get('LIVS_TIMEZONE') or DEFAULT_TIMEZONE
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        raise RuntimeError(
            f"LIVS_TIMEZONE={name!r} is not a known time zone; "
            "use a name like America/New_York."
        ) from None


def site_today(now=None):
    """Today's date in the site's zone. `now` is an aware datetime, for tests."""
    now = now or datetime.datetime.now(datetime.timezone.utc)
    return now.astimezone(site_timezone()).date()
