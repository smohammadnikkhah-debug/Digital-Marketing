"""Standalone Background Worker Process for Adaptive Trading V4.0.

Compatible with DigitalOcean App Platform Worker Component:
- Continuously polls the durable database for QUEUED refresh jobs.
- Executes jobs independently of the Web Service container.
- Survives Web Service deployments and restarts.
"""
import sys
import time
import signal
import json
import traceback
from datetime import datetime
from app.database import SessionLocal, is_sqlite
from app.models import RefreshJob
from app.services.scanner_service import scanner_service
from app.services.universe_manager import universe_manager
from app.services.snapshot_service import snapshot_service

_shutdown_requested = False


def _signal_handler(signum, frame):
    global _shutdown_requested
    sig_name = signal.Signals(signum).name if hasattr(signal, "Signals") else str(signum)
    print(f"[Worker] Received {sig_name}. Finishing cycle and shutting down cleanly...")
    _shutdown_requested = True


def run_worker_iteration(db=None) -> bool:
    """Executes a single check and execution of the next queued job. Returns True if a job was processed."""
    should_close = False
    if db is None:
        db = SessionLocal()
        should_close = True

    try:
        # Atomic job claiming: uses SKIP LOCKED on PostgreSQL so multiple concurrent workers never double-claim
        job_query = db.query(RefreshJob).filter(
            RefreshJob.status == "QUEUED"
        ).order_by(RefreshJob.created_at.asc())
        if not is_sqlite:
            job_query = job_query.with_for_update(skip_locked=True)

        queued_job = job_query.first()

        if queued_job:
            job_id = queued_job.id
            queued_job.status = "RUNNING"
            queued_job.message = "Claimed by supervised worker process..."
            queued_job.start_time = datetime.utcnow()
            db.commit()

            print(f"[Worker] Claimed job {job_id} (Type: {queued_job.job_type})...")
            is_partial = bool(queued_job.job_type and str(queued_job.job_type).strip().upper().startswith("PARTIAL"))
            if is_partial:
                rejection_reason = None
                requested = []

                if not queued_job.errors_json:
                    rejection_reason = "Missing job metadata in partial refresh job"
                else:
                    try:
                        meta = json.loads(queued_job.errors_json)
                        if not isinstance(meta, dict):
                            rejection_reason = "Malformed metadata: root is not a dictionary"
                        elif "requested_tickers" not in meta:
                            rejection_reason = "Malformed metadata: 'requested_tickers' key missing"
                        else:
                            requested = meta.get("requested_tickers")
                            if not isinstance(requested, list) or len(requested) == 0:
                                rejection_reason = "Empty or invalid 'requested_tickers' list in metadata"
                    except Exception as ex:
                        rejection_reason = f"Corrupted JSON in job metadata: {ex}"

                if not rejection_reason:
                    # Validate tickers for malformed, duplicated, unknown, or inactive values
                    seen_upper = set()
                    resolved_stocks = []

                    for t in requested:
                        if not isinstance(t, str):
                            rejection_reason = f"Malformed ticker: non-string value {t}"
                            break
                        t_clean = t.strip()
                        if not t_clean or len(t_clean) > 10 or not t_clean.replace('.', '').replace('-', '').isalnum():
                            rejection_reason = f"Malformed ticker symbol: '{t}'"
                            break
                        t_upper = t_clean.upper()
                        if t_upper in seen_upper:
                            rejection_reason = f"Duplicate ticker '{t_upper}' detected in partial refresh job"
                            break
                        seen_upper.add(t_upper)

                        stock = universe_manager.get_stock(t_upper)
                        if not stock:
                            rejection_reason = f"Unknown ticker '{t_upper}' in partial refresh job (not in universe)"
                            break
                        is_active = stock.get("is_active", True) if isinstance(stock, dict) else getattr(stock, "is_active", True)
                        if not is_active:
                            rejection_reason = f"Inactive ticker '{t_upper}' in partial refresh job"
                            break

                        resolved_stocks.append(stock)

                if rejection_reason:
                    queued_job.status = "FAILED"
                    queued_job.finish_time = datetime.utcnow()
                    queued_job.error_message = f"Partial refresh rejected: {rejection_reason}. Refusing fallback to full refresh."
                    queued_job.message = f"Failed: {rejection_reason}"
                    db.commit()
                    print(f"[Worker] Job {job_id} aborted: {rejection_reason}")
                    return True

                stocks = resolved_stocks
            else:
                stocks = universe_manager.get_all(include_inactive=False)

            # Execute job synchronously in this worker process
            scanner_service._run_refresh_worker(job_id, stocks, force_all=queued_job.force_all, is_partial=is_partial)
            print(f"[Worker] Job {job_id} processing ended.")
            return True
        return False
    finally:
        if should_close:
            db.close()


def run_worker_loop():
    global _shutdown_requested
    try:
        signal.signal(signal.SIGTERM, _signal_handler)
        signal.signal(signal.SIGINT, _signal_handler)
    except (ValueError, AttributeError):
        pass  # On certain thread contexts or platforms

    print("[Worker] Starting Adaptive Trading V4.0 Background Worker Process...")
    snapshot_service.recover_orphaned_jobs()

    while not _shutdown_requested:
        try:
            run_worker_iteration()
        except Exception as e:
            print(f"[Worker] Error in worker loop: {e}")
            traceback.print_exc()

        # Heartbeat poll interval (2 seconds)
        for _ in range(20):
            if _shutdown_requested:
                break
            time.sleep(0.1)

    print("[Worker] Graceful shutdown completed. Exiting.")


if __name__ == "__main__":
    run_worker_loop()

