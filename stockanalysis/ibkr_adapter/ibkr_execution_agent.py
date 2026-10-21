"""Interactive Brokers (IBKR) Paper Execution Agent (Stage D2.2).

Architectural Requirements & Invariants:
1. STRICTLY NON-EXECUTING IN STAGE D2.2:
   - Order placement to IBKR Gateway socket is strictly disabled.
   - Mocked broker interface simulates acknowledgments, partial fills, full fills, rejections, and unknown states.
   - Explicit build guard (NON_EXECUTING_BUILD_GUARD) prevents any order transmission calls.
2. DEDICATED SEPARATION:
   - Distinct from read-only snapshot adapter (ibkr_adapter.py, client ID 21).
   - Dedicated client ID (default: 22) and local paper socket port (4002/7497).
3. OUTBOUND HTTPS ONLY:
   - Cloud communication is outbound HTTPS from Windows using IBKR_EXECUTION_KEY.
   - Dedicated M2M credentials; admin/ingest tokens are rejected.
4. PAPER-ONLY SAFETY & VALIDATION:
   - Connects ONLY to 127.0.0.1:4002 (or 7497).
   - Strictly rejects live accounts ('U...'), live ports (4001, 7496), and non-local hosts.
5. DIAGNOSTICS & HEARTBEAT:
   - Sends periodic agent heartbeat with gateway connectivity, active accounts, and health status.
6. IDEMPOTENT REPORTING & UNKNOWN QUARANTINE:
   - State reports are idempotent.
   - Uncertain outcomes (simulated socket disconnect or error during submit) are reported as UNKNOWN,
     which immediately halts automated retry and requires administrative reconciliation.
"""
import argparse
import json
import logging
import os
import re
import socket
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
from urllib.parse import urlparse

try:
    import requests
except ImportError:
    print("FATAL: 'requests' package is required. Install via: pip install requests")
    sys.exit(1)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] (ibkr_execution_agent) %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("ibkr_execution_agent")

DEFAULT_GATEWAY_HOST = "127.0.0.1"
DEFAULT_GATEWAY_PORT = 4002  # IB Gateway paper trading port (4002) / TWS paper (7497)
DEFAULT_CLIENT_ID = 22       # Dedicated client ID, distinct from snapshot adapter (21)
DEFAULT_BACKEND_URL = os.getenv("STOCKANALYSIS_BACKEND_URL", "http://127.0.0.1:3000/stockanalysis")
DEFAULT_AGENT_ID = "windows_execution_agent_1"

# STAGE D2.2 SAFETY GUARD: Strictly non-executing
STAGE_D22_NON_EXECUTING = True
NON_EXECUTING_BUILD_GUARD = True


class NonExecutingBuildGuardViolation(RuntimeError):
    """Raised whenever any broker order-transmission method is attempted."""
    pass


def assert_non_executing_guard():
    """Explicit build guard verifying stage D2.2 non-executing invariant."""
    if not STAGE_D22_NON_EXECUTING or not NON_EXECUTING_BUILD_GUARD:
        raise NonExecutingBuildGuardViolation(
            "CRITICAL SAFETY VIOLATION: Execution agent build guard failure. "
            "Stage D2.2 must remain strictly non-executing."
        )


def load_local_env_file():
    """Loads environment variables from local .env if present."""
    adapter_dir = Path(__file__).resolve().parent
    env_file = adapter_dir / ".env"
    if env_file.exists():
        try:
            with open(env_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k, v = line.split("=", 1)
                    k, v = k.strip(), v.strip().strip("'\"")
                    if k and k not in os.environ:
                        os.environ[k] = v
        except Exception as exc:
            logger.warning(f"Could not load local .env file: {exc}")


load_local_env_file()


def verify_socket_safety(host: str, port: int) -> bool:
    """Verifies socket connects strictly to local paper trading ports."""
    parsed_host = host.strip().lower()
    if parsed_host not in ("127.0.0.1", "localhost", "::1"):
        logger.error("SAFETY REJECTION: Execution agent can ONLY connect to 127.0.0.1 (local socket).")
        return False

    if port in (4001, 7496):
        logger.error(f"CRITICAL SAFETY REJECTION: Port {port} is an Interactive Brokers LIVE trading port.")
        return False

    if port not in (4002, 7497):
        logger.warning(f"Port {port} is non-standard for IBKR paper trading (expected 4002 or 7497).")

    return True


PAPER_ACCOUNT_REGEX = re.compile(r"^(DU|DF)[A-Z0-9]{3,28}$")


def verify_account_identifier(account_id: str) -> bool:
    """Verifies account is strictly a valid IBKR paper trading account (starts with DU or DF, 3-28 chars)."""
    if not account_id or not isinstance(account_id, str):
        logger.error("SAFETY REJECTION: Account identifier is empty or invalid type.")
        return False
    clean_acc = account_id.strip().upper()
    if clean_acc.startswith("U") and not (clean_acc.startswith("DU") or clean_acc.startswith("DF")):
        logger.error(f"CRITICAL SAFETY REJECTION: '{clean_acc}' is a LIVE brokerage account!")
        return False
    if not PAPER_ACCOUNT_REGEX.match(clean_acc):
        logger.error(
            f"CRITICAL SAFETY REJECTION: '{clean_acc}' is not a valid IBKR paper account identifier "
            "matching ^(DU|DF)[A-Z0-9]{3,28}$."
        )
        return False
    return True


def probe_gateway_socket(host: str, port: int, timeout: float = 1.0) -> bool:
    """Lightweight TCP probe to check if local IB Gateway is responding."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (socket.timeout, ConnectionRefusedError, OSError):
        return False


class IBKRExecutionAgentClient:
    """Outbound HTTPS client communicating with StockAnalysis backend using M2M execution credentials."""

    def __init__(self, backend_url: str, execution_key: str, agent_id: str):
        self.backend_url = backend_url.rstrip("/")
        self.execution_key = execution_key.strip()
        self.agent_id = agent_id

        parsed = urlparse(self.backend_url)
        self.is_local = parsed.hostname in ("127.0.0.1", "localhost", "::1")
        if not self.is_local and parsed.scheme != "https":
            raise ValueError("Insecure transport: Remote backend URL must use HTTPS.")

    def _get_headers(self) -> Dict[str, str]:
        return {
            "Content-Type": "application/json",
            "X-IBKR-Execution-Key": self.execution_key,
        }

    def send_heartbeat(
        self,
        client_id: int,
        gateway_host: str,
        gateway_port: int,
        gateway_connected: bool,
        managed_accounts: List[str],
        active_account: str,
        status: str = "HEALTHY",
        details: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Sends agent heartbeat and diagnostics to StockAnalysis backend."""
        endpoint = f"{self.backend_url}/api/portfolio/ibkr/execution/agent/heartbeat"
        payload = {
            "agent_id": self.agent_id,
            "client_id": client_id,
            "gateway_host": gateway_host,
            "gateway_port": gateway_port,
            "gateway_connected": gateway_connected,
            "managed_accounts": managed_accounts,
            "active_account": active_account,
            "is_paper": True,
            "non_executing_guard": NON_EXECUTING_BUILD_GUARD,
            "status": status,
            "details": details or {},
        }
        try:
            resp = requests.post(endpoint, headers=self._get_headers(), json=payload, timeout=8)
            if resp.status_code == 200:
                return True
            logger.error("Heartbeat rejected: HTTP %s (%s)", resp.status_code, resp.text)
        except requests.RequestException as exc:
            logger.warning("Network error sending heartbeat (%s): %s", endpoint, exc)
        return False

    def poll_approved_orders(self) -> Dict[str, Any]:
        """Polls approved orders awaiting execution."""
        endpoint = f"{self.backend_url}/api/portfolio/ibkr/execution/orders/poll?agent_id={self.agent_id}"
        try:
            resp = requests.get(endpoint, headers=self._get_headers(), timeout=12)
            if resp.status_code == 200:
                return resp.json()
            logger.error("Failed to poll approved orders: HTTP %s (%s)", resp.status_code, resp.text)
        except requests.RequestException as exc:
            logger.error("Network error polling backend (%s): %s", endpoint, exc)
        return {"orders": [], "emergency_stop": True, "status": "NETWORK_ERROR"}

    def claim_order(self, order_id: str, account_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Atomically claims an order."""
        endpoint = f"{self.backend_url}/api/portfolio/ibkr/execution/orders/{order_id}/claim"
        payload = {"agent_id": self.agent_id}
        if account_id:
            payload["account_id"] = account_id
        try:
            resp = requests.post(
                endpoint,
                headers=self._get_headers(),
                json=payload,
                timeout=12
            )
            if resp.status_code == 200:
                return resp.json().get("order")
            logger.error("Failed to claim order %s: HTTP %s (%s)", order_id, resp.status_code, resp.text)
        except requests.RequestException as exc:
            logger.error("Network error claiming order %s (%s): %s", order_id, endpoint, exc)
        return None

    def report_status(self, order_id: str, target_status: str, details: Dict[str, Any]) -> bool:
        """Reports order execution status update idempotently."""
        endpoint = f"{self.backend_url}/api/portfolio/ibkr/execution/orders/{order_id}/report"
        payload = {
            "agent_id": self.agent_id,
            "target_status": target_status,
            "details": details
        }
        try:
            resp = requests.post(endpoint, headers=self._get_headers(), json=payload, timeout=12)
            if resp.status_code == 200:
                return True
            logger.error("Failed to report status %s for order %s: HTTP %s (%s)", target_status, order_id, resp.status_code, resp.text)
        except requests.RequestException as exc:
            logger.error("Network error reporting status %s for order %s: %s", target_status, order_id, exc)
        return False


class MockBrokerSimulator:
    """Mocked broker-order submission and execution simulator for Stage D2.2.

    Guarantees that no socket calls (placeOrder, cancelOrder, etc.) can be transmitted to IBKR.
    Simulates acknowledgment, partial fill, full fill, rejections, and network disconnect / unknown.
    """

    def __init__(self, mode: str = "ack"):
        self.mode = mode.lower()

    def execute_simulated_order(
        self,
        client: IBKRExecutionAgentClient,
        order: Dict[str, Any],
        agent_id: str,
    ) -> bool:
        """Executes simulation sequence according to the configured mode."""
        assert_non_executing_guard()

        order_id = order.get("order_id")
        symbol = order.get("symbol")
        action = order.get("action")
        qty = float(order.get("quantity", 0))
        limit_price = float(order.get("limit_price", 0))
        sim_ibkr_id = f"SIM-IBKR-{order_id}"

        logger.info(
            "[SIMULATED BROKER] Commencing simulation (%s) for order %s (%s %s %s @ $%s)...",
            self.mode, order_id, action, qty, symbol, limit_price
        )

        # 1. Always transition CLAIMED -> SUBMITTING
        submitting_report = {
            "stage": "D2.2",
            "is_non_executing": True,
            "order_placement": "SIMULATED",
            "submitting_agent": agent_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "note": "SIMULATED — NOT SENT TO IBKR: Dispatching to mocked broker interface",
        }
        client.report_status(order_id, "SUBMITTING", submitting_report)
        time.sleep(0.5)

        # 2. Handle simulation modes
        if self.mode == "disconnect" or self.mode == "unknown":
            logger.warning("[SIMULATED BROKER] Simulating socket timeout / network drop during transmission!")
            unknown_report = {
                "stage": "D2.2",
                "is_non_executing": True,
                "order_placement": "SIMULATED",
                "error_code": 1100,
                "quarantine_reason": "Simulated connectivity drop during order transmission. Broker outcome uncertain.",
                "requires_manual_reconciliation": True,
                "can_auto_resubmit": False,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "note": "SIMULATED — NOT SENT TO IBKR: Order quarantined in UNKNOWN status",
            }
            client.report_status(order_id, "UNKNOWN", unknown_report)
            logger.info("[SIMULATED BROKER] Order %s placed in UNKNOWN quarantine state.", order_id)
            return True

        if self.mode == "reject":
            logger.warning("[SIMULATED BROKER] Simulating broker rejection (code 201: Exceeds paper margin / Price collar violation)!")
            reject_report = {
                "stage": "D2.2",
                "is_non_executing": True,
                "order_placement": "SIMULATED",
                "error_code": 201,
                "rejection_reason": "Simulated broker rejection: Exceeds paper margin or price collar bounds",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "note": "SIMULATED — NOT SENT TO IBKR: Order rejected by mock broker",
            }
            client.report_status(order_id, "REJECTED", reject_report)
            logger.info("[SIMULATED BROKER] Order %s reported REJECTED.", order_id)
            return True

        # Mode ack, fill, or partial: First report SUBMITTED (broker acknowledgment)
        ack_report = {
            "stage": "D2.2",
            "is_non_executing": True,
            "order_placement": "SIMULATED",
            "broker_order_id": sim_ibkr_id,
            "acknowledged_at": datetime.now(timezone.utc).isoformat(),
            "venue": "IBKR_SIMULATED_GATEWAY",
            "note": "SIMULATED — NOT SENT TO IBKR: Mock broker acknowledged order submission",
        }
        client.report_status(order_id, "SUBMITTED", ack_report)
        logger.info("[SIMULATED BROKER] Order %s reported SUBMITTED (Broker Order ID: %s)", order_id, sim_ibkr_id)

        if self.mode == "ack":
            logger.info("[SIMULATED BROKER] Mode is 'ack'. Submission complete, awaiting fill simulator.")
            return True

        time.sleep(0.5)

        if self.mode == "partial":
            partial_qty = round(qty / 2.0, 4) if qty > 1 else qty
            partial_report = {
                "stage": "D2.2",
                "is_non_executing": True,
                "order_placement": "SIMULATED",
                "broker_order_id": sim_ibkr_id,
                "filled_quantity": partial_qty,
                "total_quantity": qty,
                "avg_fill_price": limit_price,
                "fill_timestamp": datetime.now(timezone.utc).isoformat(),
                "note": f"SIMULATED — NOT SENT TO IBKR: Partial execution of {partial_qty}/{qty} shares",
            }
            client.report_status(order_id, "PARTIALLY_FILLED", partial_report)
            logger.info("[SIMULATED BROKER] Order %s reported PARTIALLY_FILLED (%s shares)", order_id, partial_qty)
            time.sleep(0.5)

        # Full Fill
        fill_report = {
            "stage": "D2.2",
            "is_non_executing": True,
            "order_placement": "SIMULATED",
            "broker_order_id": sim_ibkr_id,
            "filled_quantity": qty,
            "total_quantity": qty,
            "avg_fill_price": limit_price,
            "fill_timestamp": datetime.now(timezone.utc).isoformat(),
            "note": f"SIMULATED — NOT SENT TO IBKR: Complete execution of {qty} shares @ ${limit_price}",
        }
        client.report_status(order_id, "FILLED", fill_report)
        logger.info("[SIMULATED BROKER] Order %s reported FILLED (100%% complete).", order_id)
        return True


def run_agent_cycle(args) -> bool:
    """Executes a single polling, heartbeat, and simulated execution cycle."""
    assert_non_executing_guard()

    if not verify_socket_safety(args.host, args.port):
        return False

    effective_key = (args.exec_key or os.getenv("IBKR_EXECUTION_KEY") or os.getenv("STOCKANALYSIS_IBKR_EXECUTION_KEY") or "").strip()
    if not effective_key:
        logger.error("Missing IBKR_EXECUTION_KEY. Set environment variable or local .env file.")
        return False

    client = IBKRExecutionAgentClient(args.backend_url, effective_key, args.agent_id)

    # 1. Gateway Socket Probe & Heartbeat
    gateway_online = probe_gateway_socket(args.host, args.port)
    active_account = (getattr(args, "account", None) or os.getenv("IBKR_PAPER_ACCOUNT") or os.getenv("IBKR_ACCOUNT") or "").strip().upper()
    if not active_account:
        logger.error("SAFETY REJECTION: No active paper account specified (--account or IBKR_PAPER_ACCOUNT). Automatic fallback is strictly forbidden.")
        return False

    if not verify_account_identifier(active_account):
        logger.error(f"SAFETY REJECTION: Active account '{active_account}' is not a valid IBKR paper account. Aborting cycle.")
        return False

    managed_accounts = [active_account]

    client.send_heartbeat(
        client_id=args.client_id,
        gateway_host=args.host,
        gateway_port=args.port,
        gateway_connected=gateway_online,
        managed_accounts=managed_accounts,
        active_account=active_account,
        status="HEALTHY" if gateway_online else "DEGRADED",
        details={
            "stage": "D2.2",
            "is_non_executing": True,
            "simulation_mode": args.simulate,
            "socket_probe_ok": gateway_online,
        }
    )

    # 2. Polling for Approved Work
    logger.info("Polling StockAnalysis backend for approved paper orders...")
    poll_result = client.poll_approved_orders()

    if poll_result.get("emergency_stop"):
        logger.warning("Emergency Stop is ACTIVE on server. Execution halted.")
        return True

    orders = poll_result.get("orders") or []
    if not orders:
        logger.info("No approved orders awaiting execution. Queue is clear.")
        return True

    logger.info("Discovered %d approved order(s) awaiting execution.", len(orders))

    simulator = MockBrokerSimulator(mode=args.simulate)

    for order in orders:
        order_id = order.get("order_id")
        symbol = order.get("symbol")
        action = order.get("action")
        qty = order.get("quantity")
        limit_price = order.get("limit_price")
        notional = order.get("estimated_notional")
        order_account = str(order.get("account_id") or "").strip().upper()

        logger.info(
            "Evaluating approved order %s: %s %s shares of %s @ $%s (Notional: $%s, Account: %s)",
            order_id, action, qty, symbol, limit_price, notional, order_account
        )

        if not order_account:
            logger.error("Order %s missing account_id. Refusing to claim.", order_id)
            continue
        if not verify_account_identifier(order_account):
            logger.error("Order %s specifies invalid paper account '%s'. Refusing to claim.", order_id, order_account)
            continue
        if order_account != active_account:
            logger.error("Order %s account '%s' does not match active agent account '%s'. Refusing to claim.", order_id, order_account, active_account)
            continue

        if args.dry_run:
            logger.info("[DRY-RUN] Simulating order poll without server claim.")
            continue

        # In Stage D2.2: Atomically claim order from backend
        logger.info("Atomically claiming order %s for account %s...", order_id, active_account)
        claimed_order = client.claim_order(order_id, account_id=active_account)
        if not claimed_order:
            logger.warning("Could not claim order %s (may have expired or collided).", order_id)
            continue

        logger.info("Order %s claimed successfully. Executing Stage D2.2 simulation flow...", order_id)

        # Execute simulation via MockBrokerSimulator (Strictly non-executing)
        simulator.execute_simulated_order(client, claimed_order, args.agent_id)

    return True


def main():
    parser = argparse.ArgumentParser(description="StockAnalysis IBKR Paper Execution Agent (Stage D2.2)")
    parser.add_argument("--host", default=DEFAULT_GATEWAY_HOST, help="IB Gateway Host (strictly 127.0.0.1)")
    parser.add_argument("--port", type=int, default=DEFAULT_GATEWAY_PORT, help="IB Gateway Port (default: 4002)")
    parser.add_argument("--client-id", type=int, default=DEFAULT_CLIENT_ID, help="IB Client ID (default: 22)")
    parser.add_argument("--account", default=None, help="Explicit IBKR paper account identifier (e.g. DUR257161)")
    parser.add_argument("--backend-url", default=DEFAULT_BACKEND_URL, help="StockAnalysis Backend URL")
    parser.add_argument("--exec-key", default=None, help=argparse.SUPPRESS)
    parser.add_argument("--agent-id", default=DEFAULT_AGENT_ID, help="Agent identifier")
    parser.add_argument("--once", action="store_true", help="Poll and execute single cycle, then exit")
    parser.add_argument("--dry-run", action="store_true", help="Poll approved orders without claiming from server")
    parser.add_argument(
        "--simulate",
        choices=["ack", "fill", "partial", "reject", "disconnect", "unknown"],
        default="ack",
        help="Simulated execution mode (default: ack). All results clearly labeled as SIMULATED."
    )

    args = parser.parse_args()

    logger.info("=== StockAnalysis IBKR Paper Execution Agent Starting (Stage D2.2) ===")
    logger.info("Build Guard: NON_EXECUTING_BUILD_GUARD = True (Strictly Non-Executing)")
    logger.info("Gateway Socket Target: %s:%s (clientId=%s)", args.host, args.port, args.client_id)
    logger.info("Destination Backend: %s", args.backend_url)
    logger.info("Simulation Mode: %s", args.simulate)

    if args.once or args.dry_run:
        success = run_agent_cycle(args)
        sys.exit(0 if success else 1)

    logger.info("Entering poll cycle (30s interval). Press Ctrl+C to stop.")
    while True:
        try:
            run_agent_cycle(args)
        except KeyboardInterrupt:
            logger.info("Stopping Execution Agent upon operator interrupt.")
            break
        except Exception as exc:
            logger.error("Unexpected error in execution cycle: %s", exc)
        time.sleep(30)


if __name__ == "__main__":
    main()
