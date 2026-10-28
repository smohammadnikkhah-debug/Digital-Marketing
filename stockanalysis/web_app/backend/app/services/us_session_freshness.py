"""US equity session freshness helpers (Stage D2.4C).

Uses the NYSE/NASDAQ calendar (weekends + holidays + early closes).
Does not treat raw elapsed calendar hours as sufficient freshness.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Optional, Tuple
from zoneinfo import ZoneInfo

from app.cli import is_us_market_holiday
from app.services.market_data_service import MarketDataService

NY_TZ = ZoneInfo("America/New_York")


def previous_open_session(day: date) -> date:
    """Walk backward to the previous non-holiday weekday session."""
    cursor = day - timedelta(days=1)
    for _ in range(15):
        closed, _ = is_us_market_holiday(cursor)
        if not closed:
            return cursor
        cursor -= timedelta(days=1)
    return cursor


def last_completed_us_equity_session(now_utc: Optional[datetime] = None) -> date:
    """Return the most recently *completed* regular US equity session date.

    - During PRE_MARKET / REGULAR: prior completed session (yesterday or earlier).
    - During POST_MARKET / overnight CLOSED after a trading day: that trading day.
    - On weekends/holidays: last open session before today.
    """
    if now_utc is None:
        now_utc = datetime.now(timezone.utc)
    elif now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=timezone.utc)

    now_ny = now_utc.astimezone(NY_TZ)
    today = now_ny.date()
    session, _detail = MarketDataService.get_market_session(now_utc)

    holiday, _ = is_us_market_holiday(today)
    if holiday:
        return previous_open_session(today)

    if session in ("PRE_MARKET", "REGULAR"):
        return previous_open_session(today)

    # POST_MARKET or CLOSED after the cash session finished → today is complete
    if session in ("POST_MARKET", "CLOSED"):
        return today

    return previous_open_session(today)


def parse_market_as_of(raw) -> Optional[date]:
    if raw is None:
        return None
    text = str(raw).strip()[:10]
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def evaluate_signal_session_freshness(
    market_as_of,
    now_utc: Optional[datetime] = None,
) -> Tuple[bool, str, Optional[date], Optional[date]]:
    """Compare signal market_as_of_date to last completed US session.

    Returns (is_fresh, reason_code, market_as_of, expected_session).
    """
    as_of = parse_market_as_of(market_as_of)
    expected = last_completed_us_equity_session(now_utc)
    if as_of is None:
        return False, "MISSING_MARKET_AS_OF", None, expected
    if as_of > expected:
        return False, "FUTURE_MARKET_AS_OF", as_of, expected
    if as_of < expected:
        return False, "STALE_MARKET_AS_OF", as_of, expected
    return True, "SESSION_FRESH", as_of, expected
