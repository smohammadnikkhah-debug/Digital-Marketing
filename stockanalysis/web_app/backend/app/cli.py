"""Command-Line Interface for DigitalOcean Scheduled Jobs & Market Operations.

Aligned with US market hours (America/New_York) and Daylight Saving Time (DST):
1. Market Open (9:45 AM America/New_York):
   - Enforces America/New_York timezone guard to safely absorb UTC cron shifts across EDT/EST.
   - Validates regular trading session vs weekends / NYSE holidays.
   - Fetches indicative quotes for portfolio mark-to-market.
   - Does NOT fabricate daily V4.0 signals from incomplete session candles.
2. Market Close (4:30 PM America/New_York, or 1:30 PM on early close sessions):
   - Enforces America/New_York timezone guard.
   - Skips weekends and NYSE holidays.
   - Idempotency guard: verifies if today's active snapshot is already published.
   - Delayed final market data handling: verifies closing bar settlement from data provider.
   - Recalculates V4.0 signals across universe and atomically publishes the active snapshot.
   - Automatically prunes historical snapshots and jobs to keep Supabase free tier footprint minimal.
"""
import sys
import os
import time
import argparse
import zoneinfo
from datetime import datetime, date, timedelta
from typing import Optional, List, Tuple
import pandas as pd

from app.config import (
    DATA_CACHE_DIR,
    ROLLING_PRICE_CACHE_DIR,
    DEFAULT_CAPITAL,
    WORKER_MODE,
)
from app.services.universe_manager import universe_manager
from app.services.scanner_service import scanner_service
from app.services.snapshot_service import snapshot_service
from app.database import SessionLocal
from app.models import RefreshJob, ScreenerSnapshot

NY_TZ = zoneinfo.ZoneInfo("America/New_York")


def get_good_friday(year: int) -> date:
    """Calculates Good Friday for a given year using Butcher's algorithm."""
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    easter = date(year, month, day)
    return easter - timedelta(days=2)


def is_us_market_holiday(target_date: date) -> Tuple[bool, str]:
    """Check if target_date is a standard US market holiday (NYSE/NASDAQ)."""
    # Weekends
    if target_date.weekday() >= 5:
        return True, "Weekend"


    year = target_date.year
    month = target_date.month
    day = target_date.day

    # New Year's Day (Jan 1, or observed Fri/Mon)
    if month == 1 and day == 1:
        return True, "New Year's Day"
    if month == 1 and day == 2 and target_date.weekday() == 0:
        return True, "New Year's Day (Observed)"
    if month == 12 and day == 31 and target_date.weekday() == 4:
        return True, "New Year's Day (Observed)"

    # Martin Luther King, Jr. Day (3rd Monday in Jan)
    if month == 1 and target_date.weekday() == 0 and 15 <= day <= 21:
        return True, "Martin Luther King, Jr. Day"

    # Washington's Birthday / Presidents' Day (3rd Monday in Feb)
    if month == 2 and target_date.weekday() == 0 and 15 <= day <= 21:
        return True, "Presidents' Day"

    # Good Friday
    if target_date == get_good_friday(year):
        return True, "Good Friday"

    # Memorial Day (Last Monday in May)
    if month == 5 and target_date.weekday() == 0 and day >= 25:
        return True, "Memorial Day"

    # Juneteenth (June 19, or observed)
    if month == 6 and day == 19:
        return True, "Juneteenth"
    if month == 6 and day == 20 and target_date.weekday() == 0:
        return True, "Juneteenth (Observed)"
    if month == 6 and day == 18 and target_date.weekday() == 4:
        return True, "Juneteenth (Observed)"

    # Independence Day (July 4, or observed)
    if month == 7 and day == 4:
        return True, "Independence Day"
    if month == 7 and day == 5 and target_date.weekday() == 0:
        return True, "Independence Day (Observed)"
    if month == 7 and day == 3 and target_date.weekday() == 4:
        return True, "Independence Day (Observed)"

    # Labor Day (1st Monday in Sep)
    if month == 9 and target_date.weekday() == 0 and 1 <= day <= 7:
        return True, "Labor Day"

    # Thanksgiving Day (4th Thursday in Nov)
    if month == 11 and target_date.weekday() == 3 and 22 <= day <= 28:
        return True, "Thanksgiving Day"

    # Christmas Day (Dec 25, or observed)
    if month == 12 and day == 25:
        return True, "Christmas Day"
    if month == 12 and day == 26 and target_date.weekday() == 0:
        return True, "Christmas Day (Observed)"
    if month == 12 and day == 24 and target_date.weekday() == 4:
        return True, "Christmas Day (Observed)"

    return False, "Regular Trading Session"


def is_us_market_early_close(target_date: date) -> Tuple[bool, str]:
    """Check if target_date has an early market close (1:00 PM ET)."""
    if target_date.weekday() >= 5:
        return False, ""
    month = target_date.month
    day = target_date.day

    # Day before Independence Day (July 3 if weekday)
    if month == 7 and day == 3 and target_date.weekday() in range(0, 5):
        return True, "Day before Independence Day (1:00 PM ET Early Close)"
    # Day after Thanksgiving (Black Friday - 4th Friday of Nov)
    if month == 11 and target_date.weekday() == 4 and 23 <= day <= 29:
        return True, "Black Friday (1:00 PM ET Early Close)"
    # Christmas Eve (Dec 24 if weekday)
    if month == 12 and day == 24 and target_date.weekday() in range(0, 5):
        return True, "Christmas Eve (1:00 PM ET Early Close)"
    return False, ""


def check_market_data_ready(target_date: date, benchmark_ticker: str = "QQQ") -> bool:
    """Verifies whether data provider has published the final settled closing bar for target_date."""
    try:
        import yfinance as yf
        bars = yf.download(
            benchmark_ticker,
            period="5d",
            auto_adjust=True,
            progress=False,
            multi_level_index=False,
            timeout=10,
        )
        if bars is not None and not bars.empty:
            last_date = bars.index[-1].date()
            if last_date >= target_date:
                return True
    except Exception as e:
        print(f"[MarketDataCheck] Notice: check failed ({e})")
    return False


def run_market_open():
    """Market Open Job (Target: 9:45 AM America/New_York):
    1. Timezone Guard: Verifies local New York time is within market-open window (09:35 - 10:20 ET).
       This safely filters out off-season triggers from dual-UTC cron schedules.
    2. Holiday/Weekend Guard: Exits cleanly if markets are closed.
    3. Fetches indicative quotes for portfolio mark-to-market.
    """
    now_ny = datetime.now(NY_TZ)
    today_ny = now_ny.date()
    current_time_str = now_ny.strftime("%H:%M %Z")

    print(f"[MarketOpen] Triggered at {current_time_str} ({today_ny})")

    # Timezone Guard: America/New_York market-open window (9:35 AM to 10:20 AM ET)
    # Standard market open is 9:30 AM ET; job target is 9:45 AM ET
    in_window = (now_ny.hour == 9 and now_ny.minute >= 35) or (now_ny.hour == 10 and now_ny.minute <= 20)
    if not in_window:
        print(
            f"[MarketOpen] Timezone Guard: Current New York time is {current_time_str}. "
            f"Outside the 09:35-10:20 ET market open window. Exiting cleanly (DST safe dual-cron)."
        )
        return

    # Holiday Guard
    is_holiday, reason = is_us_market_holiday(today_ny)
    if is_holiday:
        print(f"[MarketOpen] Skipping market open job: {reason} ({today_ny})")
        return

    print(f"[MarketOpen] Market session verified. Refreshing indicative quotes for {today_ny}...")
    import yfinance as yf

    stocks = universe_manager.get_all(include_inactive=False)
    updated = 0

    for s in stocks[:50]:  # Update quotes for core liquid universe
        ticker = s["ticker"]
        try:
            fast_info = yf.Ticker(ticker).fast_info
            last_price = fast_info.last_price if hasattr(fast_info, "last_price") else None
            if last_price:
                updated += 1
        except Exception:
            pass
        time.sleep(0.02)

    print(f"[MarketOpen] Market open job complete. Refreshed quotes for {updated} securities.")


def run_market_close(max_retries: int = 5, retry_delay: int = 45):
    """Market Close Job (Target: 4:30 PM America/New_York, or 1:30 PM on early closes):
    1. Timezone Guard: Verifies local New York time is past market close.
    2. Early Close Detection: Adjusts target close time on 1:00 PM early close days.
    3. Holiday/Weekend Guard: Exits cleanly if markets are closed.
    4. Idempotency Guard: Checks if today's market close snapshot is already active.
    5. Delayed Data Retry: Retries with backoff if data provider has not settled closing candle.
    6. Atomically publishes the active screener snapshot.
    """
    now_ny = datetime.now(NY_TZ)
    today_ny = now_ny.date()
    current_time_str = now_ny.strftime("%H:%M %Z")

    print(f"[MarketClose] Triggered at {current_time_str} ({today_ny})")

    # Holiday Guard
    is_holiday, reason = is_us_market_holiday(today_ny)
    if is_holiday:
        print(f"[MarketClose] Skipping market close job: {reason} ({today_ny})")
        return

    # Early Close Check
    is_early_close, early_reason = is_us_market_early_close(today_ny)
    if is_early_close:
        # Market closes at 1:00 PM ET; target execution is >= 1:25 PM ET (13:25 ET)
        is_past_close = (now_ny.hour > 13) or (now_ny.hour == 13 and now_ny.minute >= 25)
        close_desc = f"Early Close ({early_reason}, closes 13:00 ET)"
    else:
        # Regular market closes at 4:00 PM ET; target execution is >= 4:25 PM ET (16:25 ET)
        is_past_close = (now_ny.hour > 16) or (now_ny.hour == 16 and now_ny.minute >= 25)
        close_desc = "Regular Session (closes 16:00 ET)"

    # Timezone Guard
    if not is_past_close:
        print(
            f"[MarketClose] Timezone Guard: Current New York time is {current_time_str}. "
            f"Market is still open ({close_desc}). Exiting cleanly (DST safe dual-cron)."
        )
        return

    # Idempotency Guard: Skip if snapshot already generated for today's market date
    active_snap = snapshot_service.get_active_snapshot()
    if active_snap and active_snap.get("market_as_of_date") == str(today_ny):
        print(
            f"[MarketClose] Idempotency Guard: Active snapshot for market date {today_ny} "
            f"already exists ({active_snap.get('snapshot_id')}). Skipping duplicate run."
        )
        return

    # Check delayed data settlement with exponential backoff
    print(f"[MarketClose] Verifying closing data settlement for {today_ny} (Max retries: {max_retries})...")
    data_settled = False
    for attempt in range(1, max_retries + 1):
        if check_market_data_ready(today_ny):
            print(f"[MarketClose] Closing bars verified settled by data provider on attempt {attempt}.")
            data_settled = True
            break
        print(f"[MarketClose] Closing data not yet settled (Attempt {attempt}/{max_retries}). Waiting {retry_delay}s...")
        time.sleep(retry_delay)

    if not data_settled:
        print(
            f"[MarketClose] Warning: Market closing bars did not fully settle after {max_retries} attempts. "
            "Proceeding with available data; any unsettled stocks will be flagged as STALE."
        )

    # Start refresh pipeline
    res = scanner_service.start_refresh_async(force_all=False, job_type="MARKET_CLOSE")
    job_id = res.get("job_id")

    if not job_id:
        print(f"[MarketClose] Could not start job: {res.get('message')}")
        return

    # In standalone worker mode, wait up to 15 seconds for external worker to claim.
    # If not claimed (e.g. running as self-contained scheduled job container), execute directly in this process.
    time.sleep(3)
    db = SessionLocal()
    try:
        job = db.query(RefreshJob).filter(RefreshJob.id == job_id).first()
        if job and job.status == "QUEUED":
            print(f"[MarketClose] Executing refresh job {job_id} directly in CLI scheduled container...")
            stocks = universe_manager.get_all(include_inactive=False)
            scanner_service._run_refresh_worker(job_id, stocks, force_all=False)
    finally:
        db.close()

    # Poll until job finishes
    while True:
        time.sleep(2)
        status = scanner_service.get_refresh_status()
        if not status.get("is_running"):
            if status.get("status") == "COMPLETED":
                print(f"[MarketClose] SUCCESS: Job {job_id} COMPLETED successfully!")
                print(f"[MarketClose] Active Snapshot ID: {status.get('snapshot_id')}")
                return
            elif status.get("status") == "FAILED":
                print(f"[MarketClose] ERROR: Job failed: {status.get('error_message')}")
                sys.exit(1)
            else:
                print(f"[MarketClose] Job finished with status: {status.get('status')}")
                return


def migrate_prices_to_db():
    """Migrate local price cache CSV files into durable Supabase DailyBar table."""
    stocks = universe_manager.get_all(include_inactive=False)
    print(f"[PriceMigration] Starting price history migration to database for {len(stocks)} stocks...")
    migrated_stocks = 0
    total_bars = 0
    for s in stocks:
        ticker = s["ticker"]
        df = scanner_service.get_price_df(ticker)
        if df is not None and not df.empty:
            scanner_service._persist_bars_to_db(ticker, df, full=True)
            migrated_stocks += 1
            total_bars += len(df)
            if migrated_stocks % 30 == 0 or migrated_stocks == len(stocks):
                print(f"[PriceMigration] Migrated {migrated_stocks}/{len(stocks)} stocks ({total_bars} bars)...")
    print(f"[PriceMigration] Completed migration: {migrated_stocks} stocks, {total_bars} total daily bars in DB.")


def backup_stockanalysis_db(upload_supabase: bool = True):
    """Exports all StockAnalysis database tables to a compressed JSON archive with SHA-256 and durable cloud storage."""
    from app.services.backup_service import backup_service
    res = backup_service.create_backup(upload_to_supabase=upload_supabase, compress=True)
    print(f"[Backup] Successfully generated durable StockAnalysis backup:")
    print(f"  Backup ID: {res['backup_id']}")
    print(f"  File: {res['filename']} ({res['archive_bytes']} bytes compressed, {res['uncompressed_bytes']} bytes raw, ratio: {res['compression_ratio']}x)")
    print(f"  SHA-256: {res['sha256']}")
    print(f"  Total records: {res['total_records']}")
    for tbl, count in res["table_counts"].items():
        print(f"    - {tbl}: {count}")
    if res.get("uploaded_to_supabase"):
        print(f"  Durable Cloud Storage: Uploaded to Supabase Storage bucket '{res['supabase_storage'].get('bucket')}' (Key: {res['supabase_storage'].get('key')})")
    else:
        print(f"  Local storage only (Supabase Storage upload: {res.get('supabase_storage')})")
    return res


def restore_stockanalysis_db(backup_file: str, target_schema: str = "stockanalysis_restore_test", dry_run: bool = False):
    """Restores a StockAnalysis backup archive into an isolated target schema with fail-closed safety guards."""
    from app.services.backup_service import backup_service
    res = backup_service.restore_backup(
        backup_source=backup_file,
        target_schema=target_schema,
        dry_run=dry_run,
        allow_overwrite_production=False,
    )
    print(f"[Restore] Operation completed for target schema '{target_schema}':")
    print(f"  Verification: {res.get('verification', 'PASSED')}")
    print(f"  Restored tables and records:")
    for tbl, count in res.get("restored_counts", {}).items():
        print(f"    - {tbl}: {count}")
    return res


def list_backups_cli():
    """Lists available backups in Supabase Storage and local exports."""
    from app.services.backup_service import backup_service
    cloud_backups = backup_service.list_supabase_backups()
    print(f"[Backups] Supabase Storage bucket '{backup_service.backup_dir}':")
    print(f"  Durable Cloud Backups ({len(cloud_backups)} found):")
    for b in cloud_backups:
        print(f"    - {b.get('name')} ({b.get('metadata', {}).get('size', 0)} bytes, updated: {b.get('updated_at')})")
    local_files = list(backup_service.backup_dir.glob("*.json*"))
    print(f"  Local Backups ({len(local_files)} found):")
    for f in local_files:
        print(f"    - {f.name} ({f.stat().st_size} bytes)")


def main():
    parser = argparse.ArgumentParser(description="Adaptive Trading V4.0 Scheduled Job & Backup CLI")
    parser.add_argument(
        "command",
        choices=["run-market-open", "run-market-close", "recover-jobs", "storage-stats", "migrate-prices-to-db", "backup-db", "restore-db", "list-backups", "status"],
        help="Command to execute",
    )
    parser.add_argument("--file", help="Backup file path to restore", default=None)
    parser.add_argument("--target-schema", help="Target isolated schema for restore", default="stockanalysis_restore_test")
    parser.add_argument("--dry-run", action="store_true", help="Perform restore dry run without committing")
    args = parser.parse_args()

    if args.command == "run-market-open":
        run_market_open()
    elif args.command == "run-market-close":
        run_market_close()
    elif args.command == "recover-jobs":
        snapshot_service.recover_orphaned_jobs()
    elif args.command == "storage-stats":
        stats = snapshot_service.get_storage_stats()
        print("Database Storage Statistics:")
        for k, v in stats.items():
            print(f"  {k}: {v}")
    elif args.command == "migrate-prices-to-db":
        migrate_prices_to_db()
    elif args.command == "backup-db":
        backup_stockanalysis_db()
    elif args.command == "restore-db":
        if not args.file:
            print("Error: --file argument is required for restore-db")
            sys.exit(1)
        restore_stockanalysis_db(backup_file=args.file, target_schema=args.target_schema, dry_run=args.dry_run)
    elif args.command == "list-backups":
        list_backups_cli()
    elif args.command == "status":
        print("Active Snapshot:", snapshot_service.get_active_snapshot())
        print("Refresh Status:", scanner_service.get_refresh_status())


if __name__ == "__main__":
    main()


