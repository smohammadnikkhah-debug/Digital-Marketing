"""In-Container Process Supervisor for Adaptive Trading V4.0.

Runs and supervises both the Web API (Uvicorn) and the Background Worker within
a single DigitalOcean App Platform container ($5/mo basic-xxs), avoiding any
extra monthly worker container charges while providing full process-level
isolation, crash recovery, and graceful shutdown handling.

Features:
- Dual-Process Architecture: Uvicorn and Worker run as separate OS child processes.
  Heavy numerical calculations in Worker never block Uvicorn's event loop or /health checks.
- Process Supervision: If the Worker crashes (uncaught exception / OOM), the Supervisor
  detects the crash, logs the incident, and automatically restarts the Worker with backoff.
- Graceful Signal Handling: Catches SIGTERM / SIGINT from DigitalOcean App Platform.
  Sends SIGTERM to Web (stops accepting new connections) and Worker (grace period to finish
  or abort cleanly before container termination).
- Zero Duplicate Claims: Relies on PostgreSQL row-level locks (FOR UPDATE SKIP LOCKED).
"""
import os
import sys
import time
import signal
import subprocess
from typing import Optional


class ContainerSupervisor:
    def __init__(self):
        self.port = os.environ.get("PORT", "8080")
        self.host = "0.0.0.0"
        self.p_web: Optional[subprocess.Popen] = None
        self.p_worker: Optional[subprocess.Popen] = None
        self.shutting_down = False
        self.worker_restart_count = 0
        self.max_worker_restarts = 10

    def start_web(self) -> subprocess.Popen:
        print(f"[Supervisor] Launching Web Service (Uvicorn on port {self.port})...")
        cmd = [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            self.host,
            "--port",
            str(self.port),
        ]
        return subprocess.Popen(cmd, env=os.environ.copy())

    def start_worker(self) -> subprocess.Popen:
        print("[Supervisor] Launching Background Worker process...")
        cmd = [sys.executable, "-m", "app.worker"]
        return subprocess.Popen(cmd, env=os.environ.copy())

    def handle_signal(self, signum, frame):
        sig_name = signal.Signals(signum).name
        print(f"[Supervisor] Received {sig_name}. Initiating graceful shutdown of child processes...")
        self.shutting_down = True
        self.terminate_children()

    def terminate_children(self):
        # 1. Terminate Web Service first so no new HTTP requests are accepted
        if self.p_web and self.p_web.poll() is None:
            print("[Supervisor] Sending SIGTERM to Web process...")
            self.p_web.terminate()

        # 2. Terminate Worker process (gives time to cancel or finalize current job)
        if self.p_worker and self.p_worker.poll() is None:
            print("[Supervisor] Sending SIGTERM to Worker process...")
            self.p_worker.terminate()

        # 3. Wait up to 10 seconds for clean exit before forcing SIGKILL
        deadline = time.time() + 10.0
        for p, name in [(self.p_web, "Web"), (self.p_worker, "Worker")]:
            if p:
                while time.time() < deadline and p.poll() is None:
                    time.sleep(0.2)
                if p.poll() is None:
                    print(f"[Supervisor] {name} process did not exit in 10s. Forcing kill...")
                    p.kill()

        print("[Supervisor] All child processes terminated. Exiting.")
        sys.exit(0)

    def run(self):
        print("==================================================================")
        print(" [Supervisor] Adaptive Trading V4.0 In-Container Supervisor Active")
        print(f" [Supervisor] Python: {sys.version.split()[0]} | Host: {self.host}:{self.port}")
        print("==================================================================")

        # Register termination signal handlers
        signal.signal(signal.SIGTERM, self.handle_signal)
        signal.signal(signal.SIGINT, self.handle_signal)

        self.p_web = self.start_web()
        self.p_worker = self.start_worker()

        while not self.shutting_down:
            time.sleep(1)

            # 1. Check Web process health
            web_status = self.p_web.poll()
            if web_status is not None:
                print(f"[Supervisor] CRITICAL: Web service exited unexpectedly with code {web_status}!")
                # If web server dies, shut down container so DO orchestrator triggers a fresh deploy
                self.terminate_children()
                sys.exit(web_status if web_status != 0 else 1)

            # 2. Check Worker process health
            worker_status = self.p_worker.poll()
            if worker_status is not None:
                if self.shutting_down:
                    break

                self.worker_restart_count += 1
                print(
                    f"[Supervisor] WARNING: Background worker died (exit code {worker_status}). "
                    f"Restarting worker (attempt {self.worker_restart_count}/{self.max_worker_restarts})..."
                )

                if self.worker_restart_count > self.max_worker_restarts:
                    print("[Supervisor] ERROR: Exceeded maximum worker restarts. Failing container.")
                    self.terminate_children()
                    sys.exit(1)

                time.sleep(2)  # Backoff before restarting
                self.p_worker = self.start_worker()


if __name__ == "__main__":
    supervisor = ContainerSupervisor()
    supervisor.run()
