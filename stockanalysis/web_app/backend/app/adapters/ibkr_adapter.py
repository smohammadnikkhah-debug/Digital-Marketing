"""Interactive Brokers (IBKR) Gateway Windows Paper Trading Adapter.

Adaptive Trading V4.0 — Stage D1B: Read-Only Paper Account Integration.

Features:
1. Connects locally to IB Gateway Paper Trading on 127.0.0.1:4002 (clientId=21).
2. Performs read-only data collection: NetLiquidation, TotalCashValue, BuyingPower, and Positions.
3. STRICT READ-ONLY SAFETY: All order placement and cancellation methods are blocked.
4. Performs authenticated OUTBOUND-ONLY pushes to StockAnalysis backend API.
   Gateway port 4002 is never exposed publicly.
5. Reconnection resilience, error categorization, and graceful cleanup.
6. Supports CLI execution: --once, --interval, --dry-run, and --mock modes.
"""
import argparse
import json
import logging
import os
import sys
import threading
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
import requests

try:
    from ibapi.client import EClient
    from ibapi.wrapper import EWrapper
    from ibapi.contract import Contract
    HAS_IBAPI = True
except ImportError:
    HAS_IBAPI = False
    EClient = object
    EWrapper = object
    Contract = object

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("IBKRAdapter")

DEFAULT_GATEWAY_HOST = os.getenv("IBKR_GATEWAY_HOST", "127.0.0.1")
DEFAULT_GATEWAY_PORT = int(os.getenv("IBKR_GATEWAY_PORT", "4002"))
DEFAULT_CLIENT_ID = int(os.getenv("IBKR_CLIENT_ID", "21"))
DEFAULT_BACKEND_URL = os.getenv("STOCKANALYSIS_BACKEND_URL", "http://127.0.0.1:8000")
DEFAULT_INGESTION_KEY = os.getenv("IBKR_INGESTION_KEY", os.getenv("STOCKANALYSIS_IBKR_INGEST_KEY", "ibkr-ingest-key-dev-local-2026"))
DEFAULT_INTERVAL = int(os.getenv("SYNC_INTERVAL_SECONDS", "60"))


class ReadOnlyIBKREClient(EClient):
    """EClient wrapper enforcing read-only operation."""

    def placeOrder(self, *args, **kwargs):
        raise PermissionError("READ-ONLY SAFETY: Order placement is strictly forbidden in this adapter.")

    def cancelOrder(self, *args, **kwargs):
        raise PermissionError("READ-ONLY SAFETY: Order cancellation is strictly forbidden in this adapter.")

    def reqGlobalCancel(self, *args, **kwargs):
        raise PermissionError("READ-ONLY SAFETY: Order modification is strictly forbidden in this adapter.")


class IBKRPaperReader(EWrapper, ReadOnlyIBKREClient):
    """IBKR Gateway event handler and collector for paper account status."""

    def __init__(self):
        EWrapper.__init__(self)
        ReadOnlyIBKREClient.__init__(self, self)

        # Thread synchronization events
        self.connected_event = threading.Event()
        self.summary_event = threading.Event()
        self.positions_event = threading.Event()

        # State storage
        self.account_id: Optional[str] = None
        self.currency: str = "AUD"
        self.account_values: Dict[str, str] = {}
        self.positions_list: List[Dict[str, Any]] = []
        self.last_error: Optional[str] = None
        self.connection_ok: bool = False

    # --- Connection Callbacks ---

    def nextValidId(self, orderId: int):
        logger.info("Successfully established connection to IBKR Gateway.")
        self.connection_ok = True
        self.connected_event.set()

    def connectionClosed(self):
        logger.warning("IBKR Gateway connection closed by remote host.")
        self.connection_ok = False
        self.connected_event.clear()

    def error(self, reqId: int, *args, **kwargs):
        """Unified error callback supporting varying ibapi parameter signatures."""
        error_code = None
        error_str = ""

        if len(args) == 2:
            error_code, error_str = args
        elif len(args) >= 3:
            # signature: (errorTime, errorCode, errorString, ...)
            error_code = args[1]
            error_str = args[2]

        # Ignore benign informational status codes
        # 2104: Market data farm connection is OK
        # 2106: HMDS data farm connection is OK
        # 2158: Sec-def data farm connection is OK
        if error_code in (2104, 2106, 2108, 2158):
            logger.debug(f"IBKR Status {error_code}: {error_str}")
            return

        logger.warning(f"IBKR Message [Req {reqId}] Code {error_code}: {error_str}")

        # Severe connection failure codes
        if error_code in (502, 504, 1100, 1101, 1102):
            self.last_error = f"Gateway Error {error_code}: {error_str}"
            self.connection_ok = False

    def managedAccounts(self, accountsList: str):
        accounts = [a.strip() for a in accountsList.split(",") if a.strip()]
        self.managed_accounts = accounts
        if accounts:
            self.account_id = accounts[0]
            logger.info(f"Detected paper account: {self.account_id} (Managed accounts: {accounts})")

    # --- Account Summary Callbacks ---

    def accountSummary(self, reqId: int, account: str, tag: str, value: str, currency: str):
        if not self.account_id:
            self.account_id = account
        if currency:
            self.currency = currency
        if tag in ("NetLiquidation", "TotalCashValue", "BuyingPower"):
            self.account_values[tag] = value
            logger.debug(f"AccountSummary: {tag}={value} {currency}")

    def accountSummaryEnd(self, reqId: int):
        logger.info("Account summary retrieval complete.")
        self.summary_event.set()

    # --- Position Callbacks ---

    def position(self, account: str, contract: Any, position: Any, avgCost: float):
        try:
            pos_qty = float(position)
            if pos_qty != 0:
                symbol = getattr(contract, "symbol", "UNKNOWN")
                sec_type = getattr(contract, "secType", "STK")
                exchange = getattr(contract, "exchange", "SMART")
                curr = getattr(contract, "currency", "USD")

                self.positions_list.append({
                    "symbol": symbol,
                    "sec_type": sec_type,
                    "exchange": exchange,
                    "currency": curr,
                    "position": pos_qty,
                    "avg_cost": round(float(avgCost), 4),
                    "market_price": round(float(avgCost), 4),  # Seeded from cost basis
                    "market_value": round(pos_qty * float(avgCost), 2),
                    "unrealized_pnl": 0.0,
                    "realized_pnl": 0.0,
                })
        except Exception as e:
            logger.error(f"Error parsing position: {e}")

    def positionEnd(self):
        logger.info(f"Position retrieval complete. ({len(self.positions_list)} active positions)")
        self.positions_event.set()


def collect_live_snapshot(host: str, port: int, client_id: int, timeout: int = 15) -> Dict[str, Any]:
    """Connects to local IB Gateway, fetches summary and positions, and disconnects safely."""
    if not HAS_IBAPI:
        raise RuntimeError("The official 'ibapi' package is not installed in this Python environment.")

    app = IBKRPaperReader()
    worker = None

    try:
        logger.info(f"Connecting to IB Gateway at {host}:{port} (clientId={client_id})...")
        app.connect(host, port, clientId=client_id)

        worker = threading.Thread(target=app.run, daemon=True)
        worker.start()

        if not app.connected_event.wait(timeout=timeout):
            raise TimeoutError(f"Timed out waiting for IB Gateway on {host}:{port} ({timeout}s)")

        # Request data
        req_id = 9001
        app.reqAccountSummary(req_id, "All", "NetLiquidation,TotalCashValue,BuyingPower")
        app.reqPositions()

        # Wait for data retrieval events
        app.summary_event.wait(timeout=timeout)
        app.positions_event.wait(timeout=timeout)

        # Allow slight buffer for final packet flush
        time.sleep(0.5)

        net_liq = float(app.account_values.get("NetLiquidation", 0.0))
        cash = float(app.account_values.get("TotalCashValue", 0.0))
        buying_power = float(app.account_values.get("BuyingPower", 0.0))

        managed_accs = getattr(app, "managed_accounts", [app.account_id] if app.account_id else [])
        for acc in managed_accs:
            acc_str = str(acc).strip().upper()
            if acc_str.startswith("U") and not (
                acc_str.startswith("DU") or acc_str.startswith("DF") or
                "TEST" in acc_str or "MOCK" in acc_str or "PAPER" in acc_str
            ):
                raise RuntimeError(
                    f"CRITICAL SECURITY ABORT: Gateway session reports LIVE account '{acc}'. "
                    "Only paper trading accounts are permitted. Aborting snapshot push."
                )

        if app.account_id and app.account_id not in managed_accs:
            raise RuntimeError(
                f"Gateway identity mismatch: Target account '{app.account_id}' is not in authenticated managed accounts {managed_accs}."
            )

        return {
            "account_id": app.account_id or "DU_PAPER_ACCOUNT",
            "account_type": "PAPER",
            "currency": app.currency or "AUD",
            "net_liquidation": net_liq,
            "total_cash_value": cash,
            "buying_power": buying_power,
            "positions": app.positions_list,
            "connection_state": "CONNECTED",
            "error_message": None,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "adapter_version": "1.0.0",
            "gateway_managed_accounts": managed_accs,
            "gateway_account_type": "PAPER",
            "gateway_port": port,
        }

    finally:
        try:
            if app.isConnected():
                app.cancelAccountSummary(9001)
                app.cancelPositions()
                app.disconnect()
                logger.info("Safely disconnected from IB Gateway.")
        except Exception as e:
            logger.debug(f"Disconnect cleanup notice: {e}")


def generate_mock_snapshot() -> Dict[str, Any]:
    """Generates a realistic paper trading snapshot in AUD for offline testing and demos."""
    return {
        "account_id": "DU8921742",
        "account_type": "PAPER",
        "currency": "AUD",
        "net_liquidation": 1054280.50,
        "total_cash_value": 752190.20,
        "buying_power": 3008760.80,
        "positions": [
            {
                "symbol": "AAPL",
                "sec_type": "STK",
                "exchange": "NASDAQ",
                "currency": "USD",
                "position": 150.0,
                "avg_cost": 218.40,
                "market_price": 224.50,
                "market_value": 33675.00,
                "unrealized_pnl": 915.00,
                "realized_pnl": 0.0,
            },
            {
                "symbol": "MSFT",
                "sec_type": "STK",
                "exchange": "NASDAQ",
                "currency": "USD",
                "position": 100.0,
                "avg_cost": 412.30,
                "market_price": 418.90,
                "market_value": 41890.00,
                "unrealized_pnl": 660.00,
                "realized_pnl": 0.0,
            },
            {
                "symbol": "GOOGL",
                "sec_type": "STK",
                "exchange": "NASDAQ",
                "currency": "USD",
                "position": 200.0,
                "avg_cost": 174.10,
                "market_price": 178.60,
                "market_value": 35720.00,
                "unrealized_pnl": 900.00,
                "realized_pnl": 0.0,
            },
            {
                "symbol": "BHP",
                "sec_type": "STK",
                "exchange": "ASX",
                "currency": "AUD",
                "position": 800.0,
                "avg_cost": 42.50,
                "market_price": 44.10,
                "market_value": 35280.00,
                "unrealized_pnl": 1280.00,
                "realized_pnl": 0.0,
            },
        ],
        "connection_state": "CONNECTED",
        "error_message": None,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "adapter_version": "1.0.0",
        "gateway_managed_accounts": ["DU8921742"],
        "gateway_account_type": "PAPER",
        "gateway_port": 4002,
    }


def push_to_backend(backend_url: str, ingest_key: str, payload: Dict[str, Any]) -> bool:
    """Outbound-only authenticated push to StockAnalysis API."""
    target_endpoint = f"{backend_url.rstrip('/')}/api/portfolio/ibkr/sync"
    is_remote = not any(h in backend_url for h in ("127.0.0.1", "localhost"))

    # Fail closed on missing/dev credentials when targeting non-localhost
    KNOWN_DEV_INGEST_KEYS = {
        "ibkr-ingest-key-dev-local-2026",
        "test_gateway_ibkr_ingest_key_2026",
        "dev-key",
        "default",
    }
    if is_remote:
        if not ingest_key or ingest_key in KNOWN_DEV_INGEST_KEYS:
            logger.error(
                "CRITICAL SECURITY REJECTION: Missing, empty, or default development ingestion key "
                "used with remote backend URL. Production requires an explicitly provisioned secret. Aborting."
            )
            return False

    # HTTPS verification for remote transport
    if target_endpoint.startswith("http://") and is_remote:
        logger.warning(
            "INSECURE TRANSPORT WARNING: Outbound push to remote backend is not using HTTPS. "
            "HTTPS transport is strictly required in production."
        )

    headers = {
        "Content-Type": "application/json",
        "X-IBKR-Ingest-Key": ingest_key,
    }

    try:
        logger.info(f"Pushing outbound paper snapshot to {target_endpoint}...")
        resp = requests.post(target_endpoint, headers=headers, json=payload, timeout=12)

        if resp.status_code == 200:
            logger.info("Successfully pushed snapshot to StockAnalysis backend.")
            return True
        else:
            logger.error(f"Backend rejected snapshot (HTTP {resp.status_code}): {resp.text}")
            return False

    except requests.exceptions.RequestException as e:
        logger.error(f"Outbound HTTP push to backend failed: {e}")
        return False


def run_single_sync(args) -> bool:
    """Executes a single sync pass."""
    payload = None
    try:
        if args.mock:
            logger.info("Running with mock IBKR responses (--mock).")
            payload = generate_mock_snapshot()
        else:
            payload = collect_live_snapshot(
                host=args.host,
                port=args.port,
                client_id=args.client_id,
                timeout=args.timeout,
            )

    except Exception as e:
        logger.error(f"IB Gateway data collection failed: {e}")
        payload = {
            "account_id": "UNKNOWN",
            "account_type": "PAPER",
            "currency": "AUD",
            "net_liquidation": 0.0,
            "total_cash_value": 0.0,
            "buying_power": 0.0,
            "positions": [],
            "connection_state": "DISCONNECTED",
            "error_message": str(e),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "adapter_version": "1.0.0",
        }

    if args.dry_run:
        print("\n--- DRY RUN SNAPSHOT PAYLOAD ---")
        print(json.dumps(payload, indent=2))
        print("--- END SNAPLOAD ---\n")
        return True

    effective_key = args.ingest_key or args.admin_key or DEFAULT_INGESTION_KEY
    return push_to_backend(args.backend_url, effective_key, payload)


def main():
    parser = argparse.ArgumentParser(description="StockAnalysis IBKR Paper Trading Windows Adapter")
    parser.add_argument("--host", default=DEFAULT_GATEWAY_HOST, help="IB Gateway Host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=DEFAULT_GATEWAY_PORT, help="IB Gateway Socket Port (default: 4002)")
    parser.add_argument("--client-id", type=int, default=DEFAULT_CLIENT_ID, help="IB Client ID (default: 21)")
    parser.add_argument("--backend-url", default=DEFAULT_BACKEND_URL, help="StockAnalysis Backend URL")
    parser.add_argument("--ingest-key", default=DEFAULT_INGESTION_KEY, help="Dedicated IBKR Ingestion Key (do not share or commit)")
    parser.add_argument("--admin-key", default=None, help=argparse.SUPPRESS)
    parser.add_argument("--interval", type=int, default=DEFAULT_INTERVAL, help="Sync interval in seconds (default: 60)")
    parser.add_argument("--timeout", type=int, default=15, help="Socket timeout in seconds (default: 15)")
    parser.add_argument("--once", action="store_true", help="Run once and exit")
    parser.add_argument("--dry-run", action="store_true", help="Print collected snapshot without pushing to backend")
    parser.add_argument("--mock", action="store_true", help="Use mock IBKR paper account data")

    args = parser.parse_args()

    effective_key = args.ingest_key or args.admin_key or DEFAULT_INGESTION_KEY
    masked_key = (effective_key[:4] + "***" + effective_key[-4:]) if len(effective_key) > 8 else "***"

    logger.info("=== StockAnalysis IBKR Paper Trading Adapter Starting ===")
    logger.info(f"Target Gateway: {args.host}:{args.port} (clientId={args.client_id})")
    logger.info(f"Destination Backend: {args.backend_url} (Ingest Auth: {masked_key})")
    logger.info("READ-ONLY SAFETY: Order placement and modification are disabled.")

    if args.once or args.dry_run:
        success = run_single_sync(args)
        sys.exit(0 if success else 1)

    logger.info(f"Entering continuous sync loop (interval: {args.interval}s). Press Ctrl+C to stop.")
    while True:
        try:
            run_single_sync(args)
        except KeyboardInterrupt:
            logger.info("Stopping IBKR Adapter upon user interrupt.")
            break
        except Exception as e:
            logger.error(f"Unexpected error in sync cycle: {e}")

        time.sleep(args.interval)


if __name__ == "__main__":
    main()
