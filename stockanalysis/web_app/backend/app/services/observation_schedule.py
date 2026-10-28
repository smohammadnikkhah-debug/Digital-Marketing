"""DST-aware US market observation schedule (Stage D2.4K).

Config-only: describes when observation runs *should* fire.
Does NOT create Windows tasks or DigitalOcean cron entries.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

from app.cli import is_us_market_early_close, is_us_market_holiday
from app.config import DATA_CACHE_DIR

NY_TZ = ZoneInfo("America/New_York")
UTC = timezone.utc
SCHEDULE_PATH = DATA_CACHE_DIR / "observation" / "schedule_config.json"

# Local observation slots (America/New_York wall clock; DST automatic via zoneinfo)
DEFAULT_SLOTS = [
    {
        "id": "post_close_research",
        "mode": "post_close",
        "et_hour": 16,
        "et_minute": 30,
        "early_close_et_hour": 13,
        "early_close_et_minute": 30,
        "description": (
            "After regular close once research bars become available "
            "(16:30 ET; 13:30 ET on early-close sessions)."
        ),
    },
    {
        "id": "next_session_validate",
        "mode": "next_session",
        "et_hour": 9,
        "et_minute": 45,
        "early_close_et_hour": 9,
        "early_close_et_minute": 45,
        "description": (
            "Next regular session open+15m for quote freshness and "
            "simulated proposal validation."
        ),
    },
]


def ensure_schedule_config(path: Optional[Path] = None) -> Dict[str, Any]:
    """Write default local schedule config if missing. Never activates tasks."""
    dest = Path(path) if path else SCHEDULE_PATH
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        try:
            return json.loads(dest.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            pass
    cfg = {
        "version": "D2.4K",
        "timezone": "America/New_York",
        "dst_handling": "zoneinfo America/New_York (EDT/EST automatic)",
        "slots": DEFAULT_SLOTS,
        "activation": {
            "windows_task_enabled": False,
            "digitalocean_cron_enabled": False,
            "unattended_enabled": False,
            "note": (
                "Configuration only. Do not activate Windows Task Scheduler or "
                "DigitalOcean cron without explicit approval."
            ),
        },
        "holiday_source": "app.cli.is_us_market_holiday / is_us_market_early_close",
    }
    dest.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    return cfg


def is_observation_trading_day(day: date) -> Tuple[bool, str]:
    """True when US equities have a regular or early-close session."""
    closed, reason = is_us_market_holiday(day)
    if closed:
        return False, reason
    return True, "Regular Trading Session"


def next_observation_trading_day(after: Optional[date] = None) -> date:
    cursor = (after or datetime.now(NY_TZ).date()) + timedelta(days=1)
    for _ in range(20):
        ok, _ = is_observation_trading_day(cursor)
        if ok:
            return cursor
        cursor += timedelta(days=1)
    return cursor


def pair_post_close_to_next_session(
    post_close_day: date,
    *,
    config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Pair a post-close research day with the next eligible regular session.

    Post-close on day D → next_session validate on next_observation_trading_day(D).
    Skips weekends/holidays via is_observation_trading_day.
    """
    cfg = config or ensure_schedule_config()
    trading, reason = is_observation_trading_day(post_close_day)
    if not trading:
        return {
            "valid_pair": False,
            "reason_code": "POST_CLOSE_DAY_NOT_TRADING",
            "holiday_or_weekend": reason,
            "post_close_day": post_close_day.isoformat(),
        }

    post_slot = next(
        (s for s in (cfg.get("slots") or []) if s.get("mode") == "post_close"),
        DEFAULT_SLOTS[0],
    )
    next_slot = next(
        (s for s in (cfg.get("slots") or []) if s.get("mode") == "next_session"),
        DEFAULT_SLOTS[1],
    )
    next_day = next_observation_trading_day(post_close_day)
    post_dt = slot_datetime_et(post_close_day, post_slot)
    next_dt = slot_datetime_et(next_day, next_slot)
    return {
        "valid_pair": True,
        "post_close_day": post_close_day.isoformat(),
        "post_close_slot_id": post_slot.get("id"),
        "post_close_et": post_dt.isoformat(),
        "next_session_day": next_day.isoformat(),
        "next_session_slot_id": next_slot.get("id"),
        "next_session_et": next_dt.isoformat(),
        "gap_calendar_days": (next_day - post_close_day).days,
        "early_close_post": is_us_market_early_close(post_close_day)[0],
        "activation": cfg.get("activation"),
    }


def plan_soak_pairs(
    *,
    from_day: Optional[date] = None,
    pairs: int = 3,
    config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Plan N post-close → next-session pairs (informational; not activated).

    Consecutive pairs chain: post-close on D → next-session on D+n; the following
    post-close is typically on that next-session calendar day (AM validate, PM research).
    """
    cfg = config or ensure_schedule_config()
    day = from_day or datetime.now(NY_TZ).date()
    out_pairs: List[Dict[str, Any]] = []
    guard = 0
    while len(out_pairs) < pairs and guard < 40:
        guard += 1
        ok, _ = is_observation_trading_day(day)
        if ok:
            pair = pair_post_close_to_next_session(day, config=cfg)
            if pair.get("valid_pair"):
                out_pairs.append(pair)
                # Next post-close candidate = the paired next-session day
                day = date.fromisoformat(str(pair["next_session_day"]))
                continue
        day += timedelta(days=1)
    return {
        "timezone": "America/New_York",
        "pairs_requested": pairs,
        "pairs": out_pairs,
        "activation": cfg.get("activation"),
        "note": "Plan only — unattended schedules not activated",
        "soak_complete_requires_distinct_observed_sessions": pairs,
    }


def slot_datetime_et(day: date, slot: Dict[str, Any]) -> datetime:
    """Wall-clock ET datetime for a slot on a trading day (early-close aware)."""
    early, _ = is_us_market_early_close(day)
    if early and slot.get("mode") == "post_close":
        hh = int(slot.get("early_close_et_hour", 13))
        mm = int(slot.get("early_close_et_minute", 30))
    else:
        hh = int(slot.get("et_hour", 16))
        mm = int(slot.get("et_minute", 30))
    return datetime(day.year, day.month, day.day, hh, mm, tzinfo=NY_TZ)


def should_run_slot(
    slot_id: str,
    *,
    now_utc: Optional[datetime] = None,
    window_minutes: int = 45,
    config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Gate: whether *now* falls in the local observation window for slot_id."""
    cfg = config or ensure_schedule_config()
    now = now_utc or datetime.now(UTC)
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    now_ny = now.astimezone(NY_TZ)
    today = now_ny.date()

    slot = next((s for s in cfg.get("slots") or [] if s.get("id") == slot_id), None)
    if not slot:
        return {
            "should_run": False,
            "reason_code": "UNKNOWN_SLOT",
            "slot_id": slot_id,
            "now_et": now_ny.isoformat(),
        }

    trading, reason = is_observation_trading_day(today)
    if not trading:
        return {
            "should_run": False,
            "reason_code": "MARKET_CLOSED",
            "holiday_or_weekend": reason,
            "slot_id": slot_id,
            "now_et": now_ny.isoformat(),
            "mode": slot.get("mode"),
        }

    target = slot_datetime_et(today, slot)
    delta_min = (now_ny - target).total_seconds() / 60.0
    in_window = 0 <= delta_min <= float(window_minutes)
    return {
        "should_run": in_window,
        "reason_code": "IN_WINDOW" if in_window else "OUTSIDE_WINDOW",
        "slot_id": slot_id,
        "mode": slot.get("mode"),
        "target_et": target.isoformat(),
        "now_et": now_ny.isoformat(),
        "minutes_since_target": round(delta_min, 2),
        "window_minutes": window_minutes,
        "early_close": is_us_market_early_close(today)[0],
        "activation_flags": cfg.get("activation"),
    }


def plan_upcoming_slots(
    *,
    from_utc: Optional[datetime] = None,
    trading_days: int = 5,
    config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build an upcoming schedule plan (informational; does not activate)."""
    cfg = config or ensure_schedule_config()
    now = from_utc or datetime.now(UTC)
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    start = now.astimezone(NY_TZ).date()
    events: List[Dict[str, Any]] = []
    day = start
    found_days = 0
    while found_days < trading_days:
        ok, reason = is_observation_trading_day(day)
        if ok:
            found_days += 1
            for slot in cfg.get("slots") or []:
                target = slot_datetime_et(day, slot)
                events.append(
                    {
                        "us_trading_day": day.isoformat(),
                        "slot_id": slot.get("id"),
                        "mode": slot.get("mode"),
                        "et_local": target.isoformat(),
                        "utc": target.astimezone(UTC).isoformat(),
                        "early_close": is_us_market_early_close(day)[0],
                    }
                )
        else:
            events.append(
                {
                    "us_trading_day": day.isoformat(),
                    "skipped": True,
                    "reason": reason,
                }
            )
        day += timedelta(days=1)
        if (day - start).days > 21:
            break
    return {
        "timezone": "America/New_York",
        "activation": cfg.get("activation"),
        "events": events,
        "note": "Plan only — Windows/DO cron not activated",
    }
