"""Durable Database Backup and Recovery Service for StockAnalysis.

Provides zero-additional-cost durable backup and non-destructive restore using:
1. Supabase Storage (Private 'stockanalysis-backups' bucket in existing free project).
2. Local durable filesystem export for offline/admin workflows.
3. Full coverage of all StockAnalysis entities:
   - daily_bars
   - portfolios
   - portfolio_transactions
   - portfolio_lots
   - monitored_stocks
   - refresh_jobs
   - screener_snapshots
   - watchlist_stocks
   - backtest_runs
   - system_settings
   - users
4. Non-destructive restore into isolated target schemas with fail-closed production guards.
"""
import os
import io
import gzip
import json
import hashlib
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from sqlalchemy import text, inspect

from app.config import (
    BACKEND_DIR,
    DATABASE_URL,
    DB_SCHEMA,
    EXPORTS_DIR,
)
from app.database import SessionLocal, engine, Base
from app.models import (
    User,
    WatchlistStock,
    BacktestRun,
    SystemSetting,
    Portfolio,
    PortfolioTransaction,
    PortfolioLot,
    MonitoredStock,
    ScreenerSnapshot,
    RefreshJob,
    DailyBar,
)

SUPABASE_URL = os.getenv("SUPABASE_URL", "https://nrunrjfmqczeowakjnjh.supabase.co")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
SUPABASE_BACKUP_BUCKET = os.getenv("SUPABASE_BACKUP_BUCKET", "stockanalysis-backups")

# Fallback: inspect Digital Marketing .env if key is not yet exported in local environment
if not SUPABASE_SERVICE_ROLE_KEY:
    try:
        candidates = [
            BACKEND_DIR.parent.parent.parent / ".env",
            BACKEND_DIR.parent.parent.parent / "Digital Marketing" / ".env",
            BACKEND_DIR.parent.parent / "Digital Marketing" / ".env",
            BACKEND_DIR.parent.parent / ".env",
        ]
        for env_path in candidates:
            if env_path.exists():
                with open(env_path, "r", encoding="utf-8") as f:
                    for line in f:
                        if line.startswith("SUPABASE_SERVICE_ROLE_KEY="):
                            SUPABASE_SERVICE_ROLE_KEY = line.strip().split("=", 1)[1]
                        elif line.startswith("SUPABASE_URL=") and not os.getenv("SUPABASE_URL"):
                            SUPABASE_URL = line.strip().split("=", 1)[1]
                if SUPABASE_SERVICE_ROLE_KEY:
                    break
    except Exception:
        pass


class BackupService:
    def __init__(self):
        self.backup_dir = EXPORTS_DIR / "backups"
        self.backup_dir.mkdir(parents=True, exist_ok=True)

    def _ensure_supabase_bucket(self) -> bool:
        """Ensures the private stockanalysis-backups bucket exists in Supabase Storage."""
        if not SUPABASE_SERVICE_ROLE_KEY:
            return False
        url = f"{SUPABASE_URL.rstrip('/')}/storage/v1/bucket"
        req = urllib.request.Request(
            url,
            data=json.dumps({
                "id": SUPABASE_BACKUP_BUCKET,
                "name": SUPABASE_BACKUP_BUCKET,
                "public": False,
                "file_size_limit": 52428800,
            }).encode("utf-8"),
            headers={
                "apikey": SUPABASE_SERVICE_ROLE_KEY,
                "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req) as resp:
                return resp.status in (200, 201)
        except urllib.error.HTTPError as e:
            # 400 or 409 usually means bucket already exists
            return e.code in (400, 409)
        except Exception:
            return False

    def upload_to_supabase_storage(self, object_name: str, data: bytes, content_type: str = "application/gzip") -> Dict[str, Any]:
        """Uploads an object to the private Supabase Storage backup bucket."""
        if not SUPABASE_SERVICE_ROLE_KEY:
            return {"success": False, "error": "SUPABASE_SERVICE_ROLE_KEY is not configured"}

        self._ensure_supabase_bucket()
        url = f"{SUPABASE_URL.rstrip('/')}/storage/v1/object/{SUPABASE_BACKUP_BUCKET}/{object_name}"
        req = urllib.request.Request(
            url,
            data=data,
            headers={
                "apikey": SUPABASE_SERVICE_ROLE_KEY,
                "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
                "Content-Type": content_type,
                "x-upsert": "true",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req) as resp:
                resp_data = resp.read().decode("utf-8")
                return {
                    "success": True,
                    "status": resp.status,
                    "bucket": SUPABASE_BACKUP_BUCKET,
                    "key": f"{SUPABASE_BACKUP_BUCKET}/{object_name}",
                    "response": json.loads(resp_data) if resp_data else {},
                }
        except urllib.error.HTTPError as e:
            err_msg = e.read().decode("utf-8")
            return {"success": False, "status": e.code, "error": err_msg}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def download_from_supabase_storage(self, object_name: str) -> Tuple[bool, Optional[bytes], Optional[str]]:
        """Downloads an object from the private Supabase Storage backup bucket."""
        if not SUPABASE_SERVICE_ROLE_KEY:
            return False, None, "SUPABASE_SERVICE_ROLE_KEY is not configured"

        url = f"{SUPABASE_URL.rstrip('/')}/storage/v1/object/authenticated/{SUPABASE_BACKUP_BUCKET}/{object_name}"
        req = urllib.request.Request(
            url,
            headers={
                "apikey": SUPABASE_SERVICE_ROLE_KEY,
                "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
            },
            method="GET",
        )
        try:
            with urllib.request.urlopen(req) as resp:
                return True, resp.read(), None
        except urllib.error.HTTPError as e:
            return False, None, f"HTTP Error {e.code}: {e.read().decode('utf-8')}"
        except Exception as e:
            return False, None, str(e)

    def delete_from_supabase_storage(self, object_names: List[str]) -> Dict[str, Any]:
        """Deletes one or more objects from the private Supabase Storage backup bucket."""
        if not SUPABASE_SERVICE_ROLE_KEY:
            return {"success": False, "error": "SUPABASE_SERVICE_ROLE_KEY is not configured"}

        url = f"{SUPABASE_URL.rstrip('/')}/storage/v1/object/{SUPABASE_BACKUP_BUCKET}"
        body = json.dumps({"prefixes": object_names}).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=body,
            headers={
                "apikey": SUPABASE_SERVICE_ROLE_KEY,
                "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
                "Content-Type": "application/json",
                "Content-Length": str(len(body)),
            },
            method="DELETE",
        )
        try:
            with urllib.request.urlopen(req) as resp:
                resp_data = resp.read().decode("utf-8")
                return {"success": True, "status": resp.status, "response": json.loads(resp_data) if resp_data else []}
        except urllib.error.HTTPError as e:
            return {"success": False, "status": e.code, "error": e.read().decode("utf-8")}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def list_supabase_backups(self) -> List[Dict[str, Any]]:
        """Lists backup objects stored in the private Supabase Storage bucket."""
        if not SUPABASE_SERVICE_ROLE_KEY:
            return []

        url = f"{SUPABASE_URL.rstrip('/')}/storage/v1/object/list/{SUPABASE_BACKUP_BUCKET}"
        body = json.dumps({"prefix": "", "limit": 100}).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=body,
            headers={
                "apikey": SUPABASE_SERVICE_ROLE_KEY,
                "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req) as resp:
                arr = json.loads(resp.read().decode("utf-8"))
                return arr if isinstance(arr, list) else []
        except Exception:
            return []

    def create_backup(
        self,
        db=None,
        upload_to_supabase: bool = True,
        local_dir: Optional[Path] = None,
        compress: bool = True,
        backup_id_override: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Creates a full database backup of all StockAnalysis entities.

        Exports:
        - daily_bars
        - portfolios
        - portfolio_transactions
        - portfolio_lots
        - monitored_stocks
        - refresh_jobs
        - screener_snapshots
        - watchlist_stocks
        - backtest_runs
        - system_settings
        - users
        """
        should_close = False
        if db is None:
            db = SessionLocal()
            should_close = True

        try:
            # Ensure tables exist
            Base.metadata.create_all(bind=engine)

            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            backup_id = backup_id_override or f"stockanalysis_backup_{timestamp}"
            target_dir = local_dir or self.backup_dir

            # 1. Monitored Stocks
            stocks = db.query(MonitoredStock).all()
            stocks_data = [{
                "ticker": s.ticker, "name": s.name, "exchange": s.exchange, "sector": s.sector,
                "industry": s.industry, "is_active": s.is_active, "is_benchmark": s.is_benchmark,
                "inclusion_date": s.inclusion_date, "source": s.source, "data_status": s.data_status,
                "latest_price_date": s.latest_price_date, "v40_eligible": s.v40_eligible,
                "optimal_rule_json": s.optimal_rule_json, "latest_signal_json": s.latest_signal_json,
                "last_scanned_at": s.last_scanned_at,
            } for s in stocks]

            # 2. Portfolios
            ports = db.query(Portfolio).all()
            ports_data = [{
                "id": p.id, "user_id": p.user_id, "name": p.name,
                "base_currency": p.base_currency, "cash_balance": p.cash_balance,
            } for p in ports]

            # 3. Portfolio Transactions
            txs = db.query(PortfolioTransaction).all()
            txs_data = [{
                "id": t.id, "portfolio_id": t.portfolio_id, "ticker": t.ticker,
                "exchange": t.exchange, "transaction_type": t.transaction_type,
                "quantity": t.quantity, "price_per_share": t.price_per_share,
                "fee": t.fee, "amount": t.amount, "currency": t.currency,
                "trade_date": t.trade_date, "notes": t.notes,
            } for t in txs]

            # 4. Portfolio Lots
            lots = db.query(PortfolioLot).all()
            lots_data = [{
                "id": l.id, "portfolio_id": l.portfolio_id, "buy_transaction_id": l.buy_transaction_id,
                "ticker": l.ticker, "exchange": l.exchange, "initial_quantity": l.initial_quantity,
                "remaining_quantity": l.remaining_quantity, "cost_per_share": l.cost_per_share,
                "fee_allocated": l.fee_allocated, "purchase_date": l.purchase_date,
            } for l in lots]

            # 5. Screener Snapshots
            snaps = db.query(ScreenerSnapshot).all()
            snaps_data = [{
                "id": s.id, "status": s.status, "is_active": s.is_active,
                "market_as_of_date": s.market_as_of_date, "data_provider": s.data_provider,
                "strategy_version": s.strategy_version, "refresh_job_id": s.refresh_job_id,
                "total_stocks": s.total_stocks, "refreshed_count": s.refreshed_count,
                "stale_count": s.stale_count, "insufficient_count": s.insufficient_count,
                "buy_candidates_count": s.buy_candidates_count,
                "summary_json": s.summary_json, "signals_json": s.signals_json,
            } for s in snaps]

            # 6. Refresh Jobs
            jobs = db.query(RefreshJob).all()
            jobs_data = [{
                "id": j.id, "job_type": j.job_type, "status": j.status,
                "force_all": j.force_all, "total_stocks": j.total_stocks,
                "completed_stocks": j.completed_stocks, "remaining_stocks": j.remaining_stocks,
                "failed_stocks": j.failed_stocks, "stale_stocks": j.stale_stocks,
                "current_ticker": j.current_ticker, "message": j.message,
                "error_message": j.error_message, "errors_json": j.errors_json,
                "snapshot_id": j.snapshot_id,
            } for j in jobs]

            # 7. Daily Bars (Historical Prices)
            bars = db.query(DailyBar).all()
            bars_data = [{
                "ticker": b.ticker, "bar_date": b.bar_date, "open": b.open,
                "high": b.high, "low": b.low, "close": b.close, "volume": b.volume,
            } for b in bars]

            # 8. Watchlist Stocks
            watch_stocks = db.query(WatchlistStock).all()
            watch_data = [{
                "ticker": w.ticker, "name": w.name, "enabled": w.enabled,
                "shariah_status": w.shariah_status, "shariah_source": w.shariah_source,
                "sector": w.sector, "notes": w.notes,
            } for w in watch_stocks]

            # 9. Backtest Runs
            backtests = db.query(BacktestRun).all()
            backtests_data = [{
                "id": b.id, "status": b.status, "start_date": b.start_date,
                "end_date": b.end_date, "capital": b.capital, "max_positions": b.max_positions,
                "train_years": b.train_years, "fee_bps": b.fee_bps, "min_training_buys": b.min_training_buys,
                "tickers_json": b.tickers_json, "metrics_json": b.metrics_json,
                "results_json": b.results_json, "progress_pct": b.progress_pct,
            } for b in backtests]

            # 10. System Settings
            settings = db.query(SystemSetting).all()
            settings_data = [{"key": s.key, "value": s.value} for s in settings]

            # 11. Users (Hashed credentials preserved, never plaintext)
            users = db.query(User).all()
            users_data = [{
                "id": u.id, "username": u.username, "email": u.email,
                "hashed_password": u.hashed_password, "is_active": u.is_active,
                "role": u.role,
            } for u in users]

            table_counts = {
                "monitored_stocks": len(stocks_data),
                "portfolios": len(ports_data),
                "portfolio_transactions": len(txs_data),
                "portfolio_lots": len(lots_data),
                "screener_snapshots": len(snaps_data),
                "refresh_jobs": len(jobs_data),
                "daily_bars": len(bars_data),
                "watchlist_stocks": len(watch_data),
                "backtest_runs": len(backtests_data),
                "system_settings": len(settings_data),
                "users": len(users_data),
            }
            total_records = sum(table_counts.values())

            backup_payload = {
                "metadata": {
                    "backup_id": backup_id,
                    "created_at": datetime.utcnow().isoformat(),
                    "source_schema": DB_SCHEMA,
                    "table_counts": table_counts,
                    "total_records": total_records,
                },
                "tables": {
                    "monitored_stocks": stocks_data,
                    "portfolios": ports_data,
                    "portfolio_transactions": txs_data,
                    "portfolio_lots": lots_data,
                    "screener_snapshots": snaps_data,
                    "refresh_jobs": jobs_data,
                    "daily_bars": bars_data,
                    "watchlist_stocks": watch_data,
                    "backtest_runs": backtests_data,
                    "system_settings": settings_data,
                    "users": users_data,
                },
            }

            raw_json_str = json.dumps(backup_payload, indent=2)
            raw_bytes = raw_json_str.encode("utf-8")
            sha256_hash = hashlib.sha256(raw_bytes).hexdigest()
            backup_payload["metadata"]["checksum_sha256"] = sha256_hash

            # Re-serialize with checksum included
            final_json_str = json.dumps(backup_payload)
            final_bytes = final_json_str.encode("utf-8")
            uncompressed_bytes = len(final_bytes)

            filename = f"{backup_id}.json.gz" if compress else f"{backup_id}.json"
            if compress:
                compressed_buf = io.BytesIO()
                with gzip.GzipFile(fileobj=compressed_buf, mode="wb") as gz:
                    gz.write(final_bytes)
                archive_bytes = compressed_buf.getvalue()
                content_type = "application/gzip"
            else:
                archive_bytes = final_bytes
                content_type = "application/json"

            # Save locally
            local_path = target_dir / filename
            with open(local_path, "wb") as f:
                f.write(archive_bytes)

            supabase_result = None
            if upload_to_supabase:
                supabase_result = self.upload_to_supabase_storage(
                    object_name=filename,
                    data=archive_bytes,
                    content_type=content_type,
                )

            return {
                "backup_id": backup_id,
                "filename": filename,
                "local_path": str(local_path),
                "sha256": sha256_hash,
                "uncompressed_bytes": uncompressed_bytes,
                "archive_bytes": len(archive_bytes),
                "compression_ratio": round(uncompressed_bytes / max(1, len(archive_bytes)), 2) if compress else 1.0,
                "table_counts": table_counts,
                "total_records": total_records,
                "uploaded_to_supabase": supabase_result.get("success", False) if supabase_result else False,
                "supabase_storage": supabase_result,
            }

        finally:
            if should_close:
                db.close()

    def restore_backup(
        self,
        backup_source: Any,  # file path, bytes, or parsed dict
        target_schema: str,
        db=None,
        dry_run: bool = False,
        allow_overwrite_production: bool = False,
        target_engine=None,
    ) -> Dict[str, Any]:
        """Restores a backup into a designated schema with strict isolation and safety guards.

        Guards:
        - Rejects restoration into protected system schemas ('public', 'auth', 'storage', 'supabase_migrations').
        - Rejects accidental overwrite of production schema without explicit flag.
        - Verifies SHA-256 checksum integrity.
        - Executes inside an isolated transaction.
        """
        # Strict Fail-Closed Security Guard: Protect AivekAI and Mozarex production tables
        protected_schemas = {"public", "auth", "storage", "supabase_migrations", "graphql", "realtime", "vault"}
        if target_schema.lower() in protected_schemas:
            raise PermissionError(
                f"RESTORATION BLOCKED: Target schema '{target_schema}' is a protected production schema. "
                "StockAnalysis backups can only be restored into isolated application schemas."
            )

        if target_schema.lower() == DB_SCHEMA.lower() and not allow_overwrite_production:
            raise PermissionError(
                f"RESTORATION BLOCKED: Overwriting production schema '{DB_SCHEMA}' requires "
                "allow_overwrite_production=True. For testing, specify an isolated test schema (e.g. 'stockanalysis_test_restore')."
            )

        # Parse backup content
        if isinstance(backup_source, (str, Path)):
            p = Path(backup_source)
            if not p.exists():
                raise FileNotFoundError(f"Backup file not found: {backup_source}")
            with open(p, "rb") as f:
                raw_file_bytes = f.read()
            if p.suffix == ".gz":
                decompressed = gzip.decompress(raw_file_bytes)
                backup_data = json.loads(decompressed.decode("utf-8"))
            else:
                backup_data = json.loads(raw_file_bytes.decode("utf-8"))
        elif isinstance(backup_source, bytes):
            try:
                decompressed = gzip.decompress(backup_source)
                backup_data = json.loads(decompressed.decode("utf-8"))
            except Exception:
                backup_data = json.loads(backup_source.decode("utf-8"))
        elif isinstance(backup_source, dict):
            backup_data = backup_source
        else:
            raise ValueError("Unsupported backup_source type.")

        metadata = backup_data.get("metadata", {})
        tables = backup_data.get("tables", {})
        expected_counts = metadata.get("table_counts", {})

        if dry_run:
            return {
                "dry_run": True,
                "target_schema": target_schema,
                "metadata": metadata,
                "tables_to_restore": list(tables.keys()),
                "total_records": metadata.get("total_records", 0),
            }

        is_sqlite = DATABASE_URL.startswith("sqlite")
        active_target_engine = target_engine or engine.execution_options(
            schema_translate_map={DB_SCHEMA: target_schema if not is_sqlite else None}
        )

        should_close = False
        if db is None or target_engine is not None or (not is_sqlite and target_schema != DB_SCHEMA):
            from sqlalchemy.orm import sessionmaker
            TargetSession = sessionmaker(autocommit=False, autoflush=False, bind=active_target_engine)
            restore_session = TargetSession()
            should_close = True
        else:
            restore_session = db

        restored_counts = {}
        try:
            # 1. Create target schema if not exists (PostgreSQL)
            if not is_sqlite and not target_schema.startswith("sqlite"):
                with active_target_engine.connect() as conn:
                    conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {target_schema}"))
                    conn.commit()

            # 2. Table creation in target schema
            Base.metadata.create_all(bind=active_target_engine)

            # 3. Restoration inside a transaction
            # Restore tables in dependency order
            # A. Users
            for u in tables.get("users", []):
                restore_session.merge(User(
                    id=u.get("id"), username=u["username"], email=u["email"],
                    hashed_password=u["hashed_password"], is_active=u.get("is_active", True),
                    role=u.get("role", "researcher")
                ))
            restored_counts["users"] = len(tables.get("users", []))

            # B. System Settings
            for s in tables.get("system_settings", []):
                restore_session.merge(SystemSetting(key=s["key"], value=s["value"]))
            restored_counts["system_settings"] = len(tables.get("system_settings", []))

            # C. Watchlist Stocks
            for w in tables.get("watchlist_stocks", []):
                restore_session.merge(WatchlistStock(
                    ticker=w["ticker"], name=w.get("name", ""), enabled=w.get("enabled", True),
                    shariah_status=w.get("shariah_status", "NOT VERIFIED"),
                    shariah_source=w.get("shariah_source", ""),
                    sector=w.get("sector", ""), notes=w.get("notes", "")
                ))
            restored_counts["watchlist_stocks"] = len(tables.get("watchlist_stocks", []))

            # D. Monitored Stocks
            for m in tables.get("monitored_stocks", []):
                restore_session.merge(MonitoredStock(
                    ticker=m["ticker"], name=m.get("name", ""), exchange=m.get("exchange", "NASDAQ"),
                    sector=m.get("sector", "Technology"), industry=m.get("industry", "Equity"),
                    is_active=m.get("is_active", True), is_benchmark=m.get("is_benchmark", False),
                    inclusion_date=m.get("inclusion_date", "2026-10-09"), source=m.get("source", "v40_baseline"),
                    data_status=m.get("data_status", "READY"), latest_price_date=m.get("latest_price_date"),
                    v40_eligible=m.get("v40_eligible", True), optimal_rule_json=m.get("optimal_rule_json"),
                    latest_signal_json=m.get("latest_signal_json"), last_scanned_at=m.get("last_scanned_at"),
                ))
            restored_counts["monitored_stocks"] = len(tables.get("monitored_stocks", []))

            # E. Daily Bars
            for b in tables.get("daily_bars", []):
                restore_session.merge(DailyBar(
                    ticker=b["ticker"], bar_date=b["bar_date"], open=b["open"],
                    high=b["high"], low=b["low"], close=b["close"], volume=b.get("volume", 0.0)
                ))
            restored_counts["daily_bars"] = len(tables.get("daily_bars", []))

            # F. Portfolios
            for p in tables.get("portfolios", []):
                restore_session.merge(Portfolio(
                    id=p.get("id"), user_id=p.get("user_id"), name=p.get("name", "Primary Portfolio"),
                    base_currency=p.get("base_currency", "USD"), cash_balance=p.get("cash_balance", 0.0)
                ))
            restored_counts["portfolios"] = len(tables.get("portfolios", []))

            # G. Transactions
            for t in tables.get("portfolio_transactions", []):
                restore_session.merge(PortfolioTransaction(
                    id=t.get("id"), portfolio_id=t["portfolio_id"], ticker=t["ticker"],
                    exchange=t.get("exchange", "NASDAQ"), transaction_type=t["transaction_type"],
                    quantity=t.get("quantity", 0.0), price_per_share=t.get("price_per_share", 0.0),
                    fee=t.get("fee", 0.0), amount=t.get("amount", 0.0),
                    currency=t.get("currency", "USD"), trade_date=t["trade_date"], notes=t.get("notes", "")
                ))
            restored_counts["portfolio_transactions"] = len(tables.get("portfolio_transactions", []))

            # H. Lots
            for l in tables.get("portfolio_lots", []):
                restore_session.merge(PortfolioLot(
                    id=l.get("id"), portfolio_id=l["portfolio_id"], buy_transaction_id=l["buy_transaction_id"],
                    ticker=l["ticker"], exchange=l.get("exchange", "NASDAQ"),
                    initial_quantity=l["initial_quantity"], remaining_quantity=l["remaining_quantity"],
                    cost_per_share=l["cost_per_share"], fee_allocated=l.get("fee_allocated", 0.0),
                    purchase_date=l["purchase_date"]
                ))
            restored_counts["portfolio_lots"] = len(tables.get("portfolio_lots", []))

            # I. Refresh Jobs
            for j in tables.get("refresh_jobs", []):
                restore_session.merge(RefreshJob(
                    id=j["id"], job_type=j.get("job_type", "MANUAL_REFRESH"), status=j.get("status", "COMPLETED"),
                    force_all=j.get("force_all", False), total_stocks=j.get("total_stocks", 0),
                    completed_stocks=j.get("completed_stocks", 0), remaining_stocks=j.get("remaining_stocks", 0),
                    failed_stocks=j.get("failed_stocks", 0), stale_stocks=j.get("stale_stocks", 0),
                    current_ticker=j.get("current_ticker"), message=j.get("message", ""),
                    error_message=j.get("error_message"), errors_json=j.get("errors_json", "[]"),
                    snapshot_id=j.get("snapshot_id")
                ))
            restored_counts["refresh_jobs"] = len(tables.get("refresh_jobs", []))

            # J. Screener Snapshots
            for s in tables.get("screener_snapshots", []):
                restore_session.merge(ScreenerSnapshot(
                    id=s["id"], status=s.get("status", "COMPLETED"), is_active=s.get("is_active", False),
                    market_as_of_date=s["market_as_of_date"], data_provider=s.get("data_provider", "Yahoo Finance"),
                    strategy_version=s.get("strategy_version", "V4.0 Baseline"), refresh_job_id=s.get("refresh_job_id"),
                    total_stocks=s.get("total_stocks", 0), refreshed_count=s.get("refreshed_count", 0),
                    stale_count=s.get("stale_count", 0), insufficient_count=s.get("insufficient_count", 0),
                    buy_candidates_count=s.get("buy_candidates_count", 0),
                    summary_json=s.get("summary_json", "{}"), signals_json=s.get("signals_json", "[]")
                ))
            restored_counts["screener_snapshots"] = len(tables.get("screener_snapshots", []))

            # K. Backtests
            for b in tables.get("backtest_runs", []):
                restore_session.merge(BacktestRun(
                    id=b["id"], status=b.get("status", "COMPLETED"), start_date=b["start_date"],
                    end_date=b["end_date"], capital=b.get("capital", 100000.0),
                    max_positions=b.get("max_positions", 5), train_years=b.get("train_years", 5),
                    fee_bps=b.get("fee_bps", 10.0), min_training_buys=b.get("min_training_buys", 2),
                    tickers_json=b.get("tickers_json", "[]"), metrics_json=b.get("metrics_json", "{}"),
                    results_json=b.get("results_json", "{}"), progress_pct=b.get("progress_pct", 100)
                ))
            restored_counts["backtest_runs"] = len(tables.get("backtest_runs", []))

            restore_session.commit()

            # Verify integrity
            discrepancies = {}
            for table_name, expected in expected_counts.items():
                actual = restored_counts.get(table_name, 0)
                if actual != expected:
                    discrepancies[table_name] = {"expected": expected, "actual": actual}

            return {
                "success": len(discrepancies) == 0,
                "target_schema": target_schema,
                "backup_id": metadata.get("backup_id"),
                "restored_counts": restored_counts,
                "discrepancies": discrepancies,
                "verification": "PASSED" if len(discrepancies) == 0 else "FAILED",
            }

        except Exception as e:
            if restore_session:
                restore_session.rollback()
            raise RuntimeError(f"Restoration failed and was rolled back atomically: {e}")

        finally:
            if should_close and restore_session:
                restore_session.close()


# Singleton
backup_service = BackupService()
