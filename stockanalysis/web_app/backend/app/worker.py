"""Standalone Background Worker Process for Adaptive Trading V4.0.

Compatible with DigitalOcean App Platform Worker Component:
- Continuously polls the durable database for QUEUED refresh jobs.
- Executes jobs independently of the Web Service container.
- Survives Web Service deployments and restarts.
"""
import sys
import time
import signal
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
        db = SessionLocal()
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
                stocks = universe_manager.get_all(include_inactive=False)
                # Execute job synchronously in this worker process
                scanner_service._run_refresh_worker(job_id, stocks, force_all=queued_job.force_all)
                print(f"[Worker] Job {job_id} processing ended.")

        except Exception as e:
            print(f"[Worker] Error in worker loop: {e}")
            traceback.print_exc()
        finally:
            db.close()

        # Heartbeat poll interval (2 seconds)
        for _ in range(20):
            if _shutdown_requested:
                break
            time.sleep(0.1)

    print("[Worker] Graceful shutdown completed. Exiting.")


if __name__ == "__main__":
    run_worker_loop()

