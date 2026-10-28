"""Compute next US regular-session sampling times and print Windows schedule plan.

Uses America/New_York for exchange schedule, converts to Australia/Melbourne.
Does not create tasks by itself — prints JSON plan for the PowerShell scheduler.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

NY = ZoneInfo("America/New_York")
MEL = ZoneInfo("Australia/Melbourne")

# Approximate NYSE holidays 2026 (fail-closed: skip these dates)
US_MARKET_HOLIDAYS_2026 = {
    date(2026, 1, 1),
    date(2026, 1, 19),
    date(2026, 2, 16),
    date(2026, 4, 3),
    date(2026, 5, 25),
    date(2026, 6, 19),
    date(2026, 7, 3),
    date(2026, 9, 7),
    date(2026, 11, 26),
    date(2026, 12, 25),
}

SESSIONS = (
    ("open_plus_15", 15, 9, 45),
    ("open_plus_60", 60, 10, 30),
    ("open_plus_180", 180, 12, 30),
)


def next_us_trading_day(after: date | None = None) -> date:
    d = after or datetime.now(NY).date()
    # Prefer a future trading day (strictly after 'after' when provided as today)
    c = d + timedelta(days=1)
    while True:
        if c.weekday() < 5 and c not in US_MARKET_HOLIDAYS_2026:
            return c
        c += timedelta(days=1)


def build_plan(trading_day: date | None = None) -> dict:
    day = trading_day or next_us_trading_day()
    sessions = []
    for sid, mins, hh, mm in SESSIONS:
        ny_dt = datetime(day.year, day.month, day.day, hh, mm, tzinfo=NY)
        mel_dt = ny_dt.astimezone(MEL)
        stem = f"iex_validation_{day.strftime('%Y%m%d')}_{hh:02d}{mm:02d}ET_{sid}"
        sessions.append(
            {
                "session_id": sid,
                "minutes_after_open": mins,
                "ny_local": ny_dt.isoformat(),
                "melbourne_local": mel_dt.isoformat(),
                "windows_local_date": mel_dt.strftime("%Y-%m-%d"),
                "windows_local_time": mel_dt.strftime("%H:%M"),
                "task_name": f"StockAnalysis-Alpaca-IEX-{sid}",
                "evidence_stem": stem,
                "json_path": f"alpaca_adapter/evidence/{stem}.json",
                "log_path": f"alpaca_adapter/evidence/{stem}.log",
            }
        )
    return {
        "us_trading_day": day.isoformat(),
        "ny_tz": "America/New_York",
        "melbourne_tz": "Australia/Melbourne",
        "sessions": sessions,
    }


if __name__ == "__main__":
    print(json.dumps(build_plan(), indent=2))
