"""Date rules for habit completions.

A completion date becomes a DynamoDB sort key and the range read uses lexical
BETWEEN, so only canonical zero-padded YYYY-MM-DD is allowed through.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

# Inclusive of both ends, so the default window is `to` and the 29 days before it.
DEFAULT_WINDOW_DAYS = 30


class InvalidDate(ValueError):
    """Raised when a caller-supplied date is not a canonical ISO date."""


def canonical_date(value: str) -> str:
    """Return `value` unchanged if it is canonical YYYY-MM-DD, else raise.

    date.fromisoformat() is lenient on Python 3.11+ and accepts forms such as
    '20260903'. Such a string would parse fine and then sort nowhere near its
    neighbours as a sort key, so anything that does not survive an
    isoformat() round trip is rejected rather than quietly rewritten.
    """
    if not isinstance(value, str):
        raise InvalidDate(f'Expected an ISO date string, got {type(value).__name__}')

    try:
        parsed = date.fromisoformat(value)
    except ValueError as e:
        raise InvalidDate(f'"{value}" is not a valid date, expected YYYY-MM-DD') from e

    if parsed.isoformat() != value:
        raise InvalidDate(f'"{value}" is not canonical, expected {parsed.isoformat()}')

    return value


def resolve_window(from_param: str | None, to_param: str | None) -> tuple[str, str]:
    """Turn optional from/to params into an inclusive (from, to) date range.

    `to` defaults to today in UTC and `from` to a DEFAULT_WINDOW_DAYS window
    ending at `to`. A server-side UTC "today" is deliberate here: a window
    boundary being a few hours out shows the same grid, whereas mis-dating a
    completion would be a real bug, and the client always supplies that date.

    A param must be `None` to be treated as omitted -- Flask's
    `request.args.get()` returns `''` for a present-but-valueless query
    string key, and that should 400 via canonical_date(), not be silently
    treated as "not given".
    """
    to_date = canonical_date(to_param) if to_param is not None else _utc_today().isoformat()

    if from_param is not None:
        from_date = canonical_date(from_param)
    else:
        window_start = date.fromisoformat(to_date) - timedelta(
            days=DEFAULT_WINDOW_DAYS - 1
        )
        from_date = window_start.isoformat()

    if from_date > to_date:
        raise InvalidDate(f'"from" ({from_date}) is after "to" ({to_date})')

    return from_date, to_date


def _utc_today() -> date:
    return datetime.now(timezone.utc).date()
