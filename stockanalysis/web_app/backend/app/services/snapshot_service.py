"""Snapshot & Background Job Management Service for Adaptive Trading V4.0.

Provides durable transactional storage for:
1. Monitored Ticker Universe (PostgreSQL / SQLite via MonitoredStock model).
2. Immutable, versioned Screener Snapshots (ScreenerSnapshot model).
3. Persistent Background Refresh Jobs (RefreshJob model).
4. Atomic snapshot publication with zero dirty reads and automatic crash recovery.
"""
import json
import os
import uuid
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.database import SessionLocal
from app.models import MonitoredStock, ScreenerSnapshot, RefreshJob
from app.config import (
    UNIVERSE_REGISTRY_PATH,
    DATA_PROVENANCE,
    SIGNAL_PALETTE,
    DATABASE_URL,
    DB_SCHEMA,
    SNAPSHOT_RETENTION_COUNT,
    JOB_RETENTION_COUNT,
)


_snapshot_lock = threading.Lock()


class SnapshotService:
    def __init__(self):
        self._cached_active_snapshot: Optional[Dict[str, Any]] = None
        self._ensure_tables_and_seed()

    def _ensure_tables_and_seed(self):
        """Seed initial database records from universe_registry.json if database is empty."""
        db: Session = SessionLocal()
        try:
            # Check if monitored_stocks table is empty
            count = db.query(MonitoredStock).count()
            if count == 0:
                self._migrate_from_json_registry(db)

            # Check if an active snapshot exists
            active = db.query(ScreenerSnapshot).filter(ScreenerSnapshot.is_active == True).first()
            if not active:
                self._create_initial_snapshot(db)

            # Recover any orphaned jobs from server restart
            self.recover_orphaned_jobs(db)
        except Exception as e:
            print(f"[SnapshotService] Database initialization notice: {e}")
        finally:
            db.close()

    def _migrate_from_json_registry(self, db: Session):
        """Migrate legacy data_cache/universe_registry.json stocks into MonitoredStock table."""
        if not UNIVERSE_REGISTRY_PATH.exists():
            return

        try:
            with open(UNIVERSE_REGISTRY_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)

            print(f"[SnapshotService] Migrating {len(data)} securities from JSON to database...")
            for ticker, item in data.items():
                t = ticker.strip().upper()
                opt_rule = json.dumps(item.get("optimal_rule")) if item.get("optimal_rule") else None
                sig_json = json.dumps(item.get("latest_signal")) if item.get("latest_signal") else None

                stock = MonitoredStock(
                    ticker=t,
                    name=item.get("name", t),
                    exchange=item.get("exchange", "NASDAQ"),
                    sector=item.get("sector", "Technology"),
                    industry=item.get("industry", "Equity"),
                    is_active=item.get("is_active", True),
                    is_benchmark=item.get("is_benchmark", False),
                    inclusion_date=item.get("inclusion_date", "2026-10-09"),
                    source=item.get("source", "curated_expansion"),
                    data_status=item.get("data_status", "READY"),
                    latest_price_date=item.get("latest_price_date"),
                    v40_eligible=item.get("v40_eligible", True),
                    optimal_rule_json=opt_rule,
                    latest_signal_json=sig_json,
                    last_scanned_at=item.get("last_scanned_at"),
                )
                db.merge(stock)
            db.commit()
            print(f"[SnapshotService] Migration complete. MonitoredStock count: {db.query(MonitoredStock).count()}")
        except Exception as ex:
            db.rollback()
            print(f"[SnapshotService] Error during JSON registry migration: {ex}")

    def _create_initial_snapshot(self, db: Session):
        """Create baseline active ScreenerSnapshot from existing database stocks."""
        stocks = db.query(MonitoredStock).filter(MonitoredStock.is_active == True).all()
        if not stocks:
            return

        signals_list = []
        latest_date = "2026-10-09"
        refreshed = 0
        stale = 0
        insufficient = 0
        signal_counts = {
            "BUY CANDIDATE": 0,
            "WATCH": 0,
            "HOLD": 0,
            "EXIT": 0,
            "AVOID": 0,
            "SHORT": 0,
            "INSUFFICIENT_DATA": 0,
        }

        for s in stocks:
            sig = None
            if s.latest_signal_json:
                try:
                    sig = json.loads(s.latest_signal_json)
                except Exception:
                    sig = None

            if sig:
                sig_type = sig.get("signal", "").upper()
                if sig_type in ("BUY", "BUY CANDIDATE"):
                    signal_counts["BUY CANDIDATE"] += 1
                elif sig_type == "WATCH":
                    signal_counts["WATCH"] += 1
                elif sig_type == "HOLD":
                    signal_counts["HOLD"] += 1
                elif sig_type == "EXIT":
                    signal_counts["EXIT"] += 1
                elif sig_type == "AVOID":
                    signal_counts["AVOID"] += 1
                as_of = sig.get("as_of")
                if as_of and as_of > latest_date:
                    latest_date = as_of

                if s.data_status == "READY":
                    refreshed += 1
                elif s.data_status == "STALE":
                    stale += 1
                elif s.data_status == "INSUFFICIENT_DATA":
                    insufficient += 1
                signals_list.append(sig)

        signal_counts["INSUFFICIENT_DATA"] = insufficient
        summary = {
            "total_universe": len(stocks),
            "active_monitored": len(stocks),
            "refreshed_count": refreshed,
            "analysed_count": len(signals_list),
            "stale_count": stale,
            "insufficient_data_count": insufficient,
            "signals": signal_counts,
            "short_candidates_validated": 0,
            "short_status_notice": "RESEARCH ONLY — Audited V4.0 strategy is long-only. No short strategy validated.",
            "latest_market_date": latest_date,
            "data_provenance": DATA_PROVENANCE,
        }

        snap_id = f"snap_baseline_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
        snapshot = ScreenerSnapshot(
            id=snap_id,
            status="COMPLETED",
            is_active=True,
            market_as_of_date=latest_date,
            calculated_at=datetime.utcnow(),
            saved_at=datetime.utcnow(),
            data_provider="Audited Baseline & Yahoo Finance",
            strategy_version="Adaptive Trading V4.0 Baseline",
            total_stocks=len(stocks),
            refreshed_count=refreshed,
            stale_count=stale,
            insufficient_count=insufficient,
            buy_candidates_count=signal_counts["BUY CANDIDATE"],
            summary_json=json.dumps(summary),
            signals_json=json.dumps(signals_list),
        )
        db.add(snapshot)
        db.commit()
        print(f"[SnapshotService] Created initial active snapshot: {snap_id}")

    def recover_orphaned_jobs(self, db: Optional[Session] = None):
        """Mark any jobs left in RUNNING or QUEUED status from a past crash as FAILED."""
        should_close = False
        if db is None:
            db = SessionLocal()
            should_close = True

        try:
            stuck_jobs = db.query(RefreshJob).filter(
                RefreshJob.status.in_(["RUNNING", "QUEUED"])
            ).all()

            for job in stuck_jobs:
                job.status = "FAILED"
                job.finish_time = datetime.utcnow()
                job.error_message = "Server restarted or worker stopped while job was in progress."
                job.message = "Failed: Server restart detected."
            if stuck_jobs:
                db.commit()
                print(f"[SnapshotService] Cleaned up {len(stuck_jobs)} orphaned refresh jobs.")
        except Exception as ex:
            db.rollback()
            print(f"[SnapshotService] Error recovering orphaned jobs: {ex}")
        finally:
            if should_close:
                db.close()

    def claim_next_queued_job(self, db: Optional[Session] = None) -> Optional[RefreshJob]:
        """Atomically claims the oldest QUEUED refresh job using row-level locking (SKIP LOCKED)."""
        should_close = False
        if db is None:
            db = SessionLocal()
            should_close = True

        try:
            from app.database import is_sqlite
            query = db.query(RefreshJob).filter(RefreshJob.status == "QUEUED").order_by(RefreshJob.created_at.asc())
            if not is_sqlite:
                query = query.with_for_update(skip_locked=True)
            job = query.first()
            if job:
                job.status = "RUNNING"
                job.start_time = datetime.utcnow()
                job.message = "Claimed by background worker..."
                db.commit()
                db.refresh(job)
            return job
        except Exception:
            db.rollback()
            return None
        finally:
            if should_close:
                db.close()

    def get_active_snapshot(self, db: Optional[Session] = None) -> Optional[Dict[str, Any]]:
        """Retrieve the currently active screener snapshot with complete metadata."""
        should_close = False
        if db is None:
            db = SessionLocal()
            should_close = True

        try:
            snap = db.query(ScreenerSnapshot).filter(
                ScreenerSnapshot.is_active == True,
                ScreenerSnapshot.status == "COMPLETED"
            ).order_by(desc(ScreenerSnapshot.saved_at)).first()

            if not snap:
                return None

            summary = json.loads(snap.summary_json) if snap.summary_json else {}
            signals = json.loads(snap.signals_json) if snap.signals_json else []

            return {
                "snapshot_id": snap.id,
                "status": snap.status,
                "is_active": snap.is_active,
                "market_as_of_date": snap.market_as_of_date,
                "calculated_at": snap.calculated_at.strftime("%Y-%m-%d %H:%M:%S UTC") if snap.calculated_at else None,
                "saved_at": snap.saved_at.strftime("%Y-%m-%d %H:%M:%S UTC") if snap.saved_at else None,
                "data_provider": snap.data_provider,
                "strategy_version": snap.strategy_version,
                "refresh_job_id": snap.refresh_job_id,
                "total_stocks": snap.total_stocks,
                "refreshed_count": snap.refreshed_count,
                "stale_count": snap.stale_count,
                "insufficient_count": snap.insufficient_count,
                "buy_candidates_count": snap.buy_candidates_count,
                "summary": summary,
                "signals": signals,
            }
        finally:
            if should_close:
                db.close()

    def publish_new_snapshot(
        self,
        staged_signals: List[Dict[str, Any]],
        market_as_of_date: str,
        refresh_job_id: Optional[str] = None,
        data_provider: str = "Yahoo Finance (Auto-Adjusted OHLCV)",
        strategy_version: str = "Adaptive Trading V4.0 Baseline",
        db: Optional[Session] = None,
    ) -> Dict[str, Any]:
        """Atomically publishes a new completed screener snapshot.
        Replaces previous active snapshot transactionally."""
        should_close = False
        if db is None:
            db = SessionLocal()
            should_close = True

        with _snapshot_lock:
            try:
                # 1. Calculate summary metrics
                refreshed = 0
                stale = 0
                insufficient = 0
                signal_counts = {
                    "BUY CANDIDATE": 0,
                    "WATCH": 0,
                    "HOLD": 0,
                    "EXIT": 0,
                    "AVOID": 0,
                    "SHORT": 0,
                    "INSUFFICIENT_DATA": 0,
                }

                for sig in staged_signals:
                    sig_type = sig.get("signal", "").upper()
                    if sig_type in ("BUY", "BUY CANDIDATE"):
                        signal_counts["BUY CANDIDATE"] += 1
                    elif sig_type == "WATCH":
                        signal_counts["WATCH"] += 1
                    elif sig_type == "HOLD":
                        signal_counts["HOLD"] += 1
                    elif sig_type == "EXIT":
                        signal_counts["EXIT"] += 1
                    elif sig_type == "AVOID":
                        signal_counts["AVOID"] += 1

                    freshness = sig.get("data_freshness", "READY").upper()
                    if freshness == "STALE":
                        stale += 1
                    elif freshness == "INSUFFICIENT_DATA":
                        insufficient += 1
                    else:
                        refreshed += 1

                signal_counts["INSUFFICIENT_DATA"] = insufficient
                calc_time = datetime.utcnow()

                summary = {
                    "total_universe": len(staged_signals),
                    "active_monitored": len(staged_signals),
                    "refreshed_count": refreshed,
                    "analysed_count": len(staged_signals),
                    "stale_count": stale,
                    "insufficient_data_count": insufficient,
                    "signals": signal_counts,
                    "short_candidates_validated": 0,
                    "short_status_notice": "RESEARCH ONLY — Audited V4.0 strategy is long-only. No short strategy validated.",
                    "latest_market_date": market_as_of_date,
                    "last_refresh_time": calc_time.strftime("%Y-%m-%d %H:%M:%S UTC"),
                    "data_provenance": {
                        **DATA_PROVENANCE,
                        "badge_text": f"Expanded Screener Universe ({len(staged_signals)} Monitored)",
                        "is_refreshed": True,
                        "as_of_date": market_as_of_date,
                    },
                }

                snap_id = f"snap_{calc_time.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"

                # 2. Deactivate previous active snapshots
                db.query(ScreenerSnapshot).filter(
                    ScreenerSnapshot.is_active == True
                ).update({"is_active": False})

                # 3. Insert new active snapshot
                new_snap = ScreenerSnapshot(
                    id=snap_id,
                    status="COMPLETED",
                    is_active=True,
                    market_as_of_date=market_as_of_date,
                    calculated_at=calc_time,
                    saved_at=calc_time,
                    data_provider=data_provider,
                    strategy_version=strategy_version,
                    refresh_job_id=refresh_job_id,
                    total_stocks=len(staged_signals),
                    refreshed_count=refreshed,
                    stale_count=stale,
                    insufficient_count=insufficient,
                    buy_candidates_count=signal_counts["BUY CANDIDATE"],
                    summary_json=json.dumps(summary),
                    signals_json=json.dumps(staged_signals),
                )
                db.add(new_snap)

                # 4. Synchronize MonitoredStock records
                for sig in staged_signals:
                    ticker = sig.get("ticker", "").strip().upper()
                    stock_rec = db.query(MonitoredStock).filter(MonitoredStock.ticker == ticker).first()
                    if stock_rec:
                        stock_rec.latest_signal_json = json.dumps(sig)
                        stock_rec.latest_price_date = sig.get("as_of")
                        stock_rec.data_status = "STALE" if sig.get("data_freshness") == "STALE" else "INSUFFICIENT_DATA" if sig.get("data_freshness") == "INSUFFICIENT_DATA" else "READY"
                        stock_rec.last_scanned_at = calc_time.isoformat()

                db.commit()

                # 5. Mirror save JSON file atomically (write to .tmp and rename)
                self._mirror_save_json(db)

                # 6. Apply retention policy to guarantee minimal storage footprint on Supabase free tier
                try:
                    self.prune_historical_snapshots(keep_count=SNAPSHOT_RETENTION_COUNT, db=db)
                    self.prune_historical_jobs(keep_count=JOB_RETENTION_COUNT, db=db)
                except Exception as prune_err:
                    print(f"[SnapshotService] Retention cleanup notice: {prune_err}")


                return {
                    "snapshot_id": snap_id,
                    "market_as_of_date": market_as_of_date,
                    "calculated_at": calc_time.strftime("%Y-%m-%d %H:%M:%S UTC"),
                    "total_stocks": len(staged_signals),
                    "summary": summary,
                }
            except Exception as ex:
                db.rollback()
                raise ex
            finally:
                if should_close:
                    db.close()

    def _mirror_save_json(self, db: Session):
        """Atomically mirrors database monitored stocks to data_cache/universe_registry.json."""
        try:
            stocks = db.query(MonitoredStock).all()
            data = {}
            for s in stocks:
                opt_rule = json.loads(s.optimal_rule_json) if s.optimal_rule_json else None
                latest_sig = json.loads(s.latest_signal_json) if s.latest_signal_json else None
                data[s.ticker] = {
                    "ticker": s.ticker,
                    "name": s.name,
                    "exchange": s.exchange,
                    "sector": s.sector,
                    "industry": s.industry,
                    "is_active": s.is_active,
                    "is_benchmark": s.is_benchmark,
                    "inclusion_date": s.inclusion_date,
                    "source": s.source,
                    "latest_price_date": s.latest_price_date,
                    "data_status": s.data_status,
                    "v40_eligible": s.v40_eligible,
                    "optimal_rule": opt_rule,
                    "latest_signal": latest_sig,
                    "last_scanned_at": s.last_scanned_at,
                }

            UNIVERSE_REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = UNIVERSE_REGISTRY_PATH.with_suffix(".tmp")
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            os.replace(tmp_path, UNIVERSE_REGISTRY_PATH)
        except Exception as e:
            print(f"[SnapshotService] Warning: Mirror JSON save failed: {e}")

    def list_historical_snapshots(self, limit: int = 15, db: Optional[Session] = None) -> List[Dict[str, Any]]:
        """List historical screener snapshots for auditability."""
        should_close = False
        if db is None:
            db = SessionLocal()
            should_close = True

        try:
            snaps = db.query(ScreenerSnapshot).order_by(
                desc(ScreenerSnapshot.saved_at)
            ).limit(limit).all()

            results = []
            for s in snaps:
                results.append({
                    "id": s.id,
                    "status": s.status,
                    "is_active": s.is_active,
                    "market_as_of_date": s.market_as_of_date,
                    "calculated_at": s.calculated_at.strftime("%Y-%m-%d %H:%M:%S UTC") if s.calculated_at else None,
                    "total_stocks": s.total_stocks,
                    "refreshed_count": s.refreshed_count,
                    "stale_count": s.stale_count,
                    "insufficient_count": s.insufficient_count,
                    "buy_candidates_count": s.buy_candidates_count,
                    "refresh_job_id": s.refresh_job_id,
                })
            return results
        finally:
            if should_close:
                db.close()

    def prune_historical_snapshots(self, keep_count: int = 30, db: Optional[Session] = None) -> int:
        """Delete inactive snapshots older than the most recent `keep_count` snapshots to prevent storage bloat."""
        should_close = False
        if db is None:
            db = SessionLocal()
            should_close = True

        try:
            snaps_to_keep = db.query(ScreenerSnapshot.id).order_by(
                desc(ScreenerSnapshot.saved_at)
            ).limit(keep_count).all()
            keep_ids = {s[0] for s in snaps_to_keep}

            to_delete = db.query(ScreenerSnapshot).filter(
                ScreenerSnapshot.is_active == False,
                ~ScreenerSnapshot.id.in_(keep_ids)
            ).all()

            deleted_count = len(to_delete)
            for s in to_delete:
                db.delete(s)
            if deleted_count > 0:
                db.commit()
                print(f"[SnapshotService] Pruned {deleted_count} old screener snapshots (Retention: {keep_count}).")
            return deleted_count
        except Exception as e:
            db.rollback()
            print(f"[SnapshotService] Snapshot retention error: {e}")
            return 0
        finally:
            if should_close:
                db.close()

    def prune_historical_jobs(self, keep_count: int = 50, max_age_days: int = 14, db: Optional[Session] = None) -> int:
        """Prunes finished background refresh jobs older than max_age_days or beyond keep_count."""
        should_close = False
        if db is None:
            db = SessionLocal()
            should_close = True

        try:
            cutoff = datetime.utcnow() - timedelta(days=max_age_days)
            jobs_to_keep = db.query(RefreshJob.id).order_by(
                desc(RefreshJob.created_at)
            ).limit(keep_count).all()
            keep_ids = {j[0] for j in jobs_to_keep}

            to_delete = db.query(RefreshJob).filter(
                RefreshJob.status.in_(["COMPLETED", "FAILED", "CANCELLED"]),
                ~RefreshJob.id.in_(keep_ids),
                RefreshJob.created_at < cutoff,
            ).all()

            deleted_count = len(to_delete)
            for j in to_delete:
                db.delete(j)
            if deleted_count > 0:
                db.commit()
                print(f"[SnapshotService] Pruned {deleted_count} finished refresh jobs (Retention: {keep_count}).")
            return deleted_count
        except Exception as e:
            db.rollback()
            print(f"[SnapshotService] Job retention error: {e}")
            return 0
        finally:
            if should_close:
                db.close()

    def get_storage_stats(self, db: Optional[Session] = None) -> Dict[str, Any]:
        """Calculate real-time database usage metrics to monitor Supabase free-tier storage safety."""
        should_close = False
        if db is None:
            db = SessionLocal()
            should_close = True

        try:
            stocks_count = db.query(MonitoredStock).count()
            snapshots_count = db.query(ScreenerSnapshot).count()
            jobs_count = db.query(RefreshJob).count()
            active_snap = db.query(ScreenerSnapshot).filter(ScreenerSnapshot.is_active == True).first()

            from app.models import DailyBar
            try:
                bars_count = db.query(DailyBar).count()
            except Exception:
                bars_count = 0

            # Average row footprints based on columns and JSON payload sizes:
            # Monitored stock: ~1.2 KB
            # Screener snapshot: ~125 KB
            # Refresh job: ~1 KB
            # Daily bar: ~105 bytes (table + index overhead)
            # Fixed index/metadata overhead: ~500 KB
            est_stock_bytes = stocks_count * 1200
            est_snap_bytes = snapshots_count * 125000
            est_job_bytes = jobs_count * 1000
            est_bar_bytes = bars_count * 105
            total_est_bytes = est_stock_bytes + est_snap_bytes + est_job_bytes + est_bar_bytes + 500000
            total_est_mb = round(total_est_bytes / (1024 * 1024), 2)

            supabase_limit_mb = 500.0
            pct_used = round((total_est_mb / supabase_limit_mb) * 100, 2)

            return {
                "database_url_type": "sqlite" if DATABASE_URL.startswith("sqlite") else "postgresql",
                "db_schema": DB_SCHEMA,
                "monitored_stocks_count": stocks_count,
                "daily_bars_count": bars_count,
                "total_snapshots_count": snapshots_count,
                "snapshot_retention_limit": SNAPSHOT_RETENTION_COUNT,
                "total_jobs_count": jobs_count,
                "job_retention_limit": JOB_RETENTION_COUNT,
                "active_snapshot_id": active_snap.id if active_snap else None,
                "active_market_date": active_snap.market_as_of_date if active_snap else None,
                "estimated_footprint_mb": total_est_mb,
                "supabase_free_limit_mb": supabase_limit_mb,
                "capacity_used_pct": pct_used,
                "headroom_mb": round(supabase_limit_mb - total_est_mb, 2),
                "status": "HEALTHY",
            }

        finally:
            if should_close:
                db.close()


# Singleton
snapshot_service = SnapshotService()

