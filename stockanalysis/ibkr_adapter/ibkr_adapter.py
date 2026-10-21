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
import math
import os
import sys
import threading
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
from pathlib import Path
import requests

try:
    from ibapi.client import EClient
    from ibapi.wrapper import EWrapper
    from ibapi.contract import Contract
    HAS_IBAPI = True
except ImportError:
    HAS_IBAPI = False
    class EClient:
        pass
    class EWrapper:
        pass
    class Contract:
        pass

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("IBKRAdapter")

def load_local_env():
    """Securely loads .env file from the adapter's directory if present.

    Prevents placing secrets in command-line arguments or bash/powershell history.
    """
    adapter_dir = Path(__file__).resolve().parent
    search_paths = [
        adapter_dir / ".env",
        adapter_dir.parent / ".env",
    ]
    for env_path in search_paths:
        if env_path.exists():
            try:
                with open(env_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith("#") or "=" not in line:
                            continue
                        k, v = line.split("=", 1)
                        k = k.strip()
                        v = v.strip().strip("'\"")
                        if k and k not in os.environ:
                            os.environ[k] = v
                logger.info(f"Loaded local configuration from {env_path.name}")
            except Exception as ex:
                logger.warning(f"Failed to read .env file at {env_path}: {ex}")
            break

load_local_env()

DEFAULT_GATEWAY_HOST = os.getenv("IBKR_GATEWAY_HOST", "127.0.0.1")
DEFAULT_GATEWAY_PORT = int(os.getenv("IBKR_GATEWAY_PORT", "4002"))
DEFAULT_CLIENT_ID = int(os.getenv("IBKR_CLIENT_ID", "21"))
DEFAULT_BACKEND_URL = os.getenv("STOCKANALYSIS_BACKEND_URL", "http://127.0.0.1:8000")


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

        logger.warning("IBKR message [Req %s] code %s", reqId, error_code)

        # Severe connection failure codes
        if error_code in (502, 504, 1100, 1101, 1102):
            self.last_error = f"Gateway Error {error_code}"
            self.connection_ok = False

    def managedAccounts(self, accountsList: str):
        accounts = [a.strip() for a in accountsList.split(",") if a.strip()]
        self.managed_accounts = accounts
        if accounts:
            self.account_id = accounts[0]
            logger.info("IBKR managed account received (identifier redacted)")

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
            if self.account_id and account != self.account_id:
                raise RuntimeError("Position account differs from managed paper account")
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
                    "market_price": None,  # No live market quote requested
                    "market_value": None,  # Unknown until market data is fetched
                    "unrealized_pnl": None,
                    "realized_pnl": None,
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

        # A snapshot is valid only after both IBKR streams finish.
        if not app.summary_event.wait(timeout=30):
            raise TimeoutError("IBKR account summary did not complete")
        if not app.positions_event.wait(timeout=30):
            raise TimeoutError("IBKR positions retrieval did not complete")
        if not app.connection_ok or not app.isConnected():
            raise ConnectionError("IBKR Gateway disconnected during account retrieval")
        if app.last_error:
            raise ConnectionError(app.last_error)

        required = ("NetLiquidation", "TotalCashValue", "BuyingPower")
        missing = [tag for tag in required if tag not in app.account_values]
        if missing:
            raise RuntimeError(f"IBKR account summary incomplete: missing {missing}")

        net_liq = float(app.account_values["NetLiquidation"])
        cash = float(app.account_values["TotalCashValue"])
        buying_power = float(app.account_values["BuyingPower"])
        if not all(math.isfinite(v) for v in (net_liq, cash, buying_power)):
            raise ValueError("IBKR returned a non-finite account balance")

        managed_accs = getattr(app, "managed_accounts", [])
        if not managed_accs or not app.account_id:
            raise RuntimeError("IBKR did not supply a verifiable managed paper account")
        if len(managed_accs) != 1 or app.account_id not in managed_accs:
            raise RuntimeError("Expected exactly one matching IBKR paper account")
        if not app.account_id.upper().startswith(("DU", "DF")):
            raise RuntimeError("Non-paper or unrecognized account identifier: sync blocked")
        if port not in (4002, 7497):
            raise RuntimeError("Non-paper IBKR Gateway port: sync blocked")

        return {
            "account_id": app.account_id,
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
                "realized_pnl": None,
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
                "realized_pnl": None,
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
                "realized_pnl": None,
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
                "realized_pnl": None,
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
    """Push one verified read-only paper snapshot over HTTPS."""
    from urllib.parse import urlparse

    base = backend_url.rstrip("/")
    parsed = urlparse(base)
    local = parsed.hostname in ("127.0.0.1", "localhost", "::1")
    if not local and (parsed.scheme != "https" or parsed.hostname != "mozarex.com"):
        logger.error("Remote destination must be https://mozarex.com")
        return False
    if not local and base != "https://mozarex.com/stockanalysis":
        logger.error("Set STOCKANALYSIS_BACKEND_URL=https://mozarex.com/stockanalysis")
        return False

    known_dev = {"ibkr-ingest-key-dev-local-2026", "test_gateway_ibkr_ingest_key_2026", "dev-key", "default"}
    if not local and (len(ingest_key) < 32 or ingest_key in known_dev):
        logger.error("Missing, weak or development ingestion key; sync blocked")
        return False
    if payload.get("connection_state") != "CONNECTED" or payload.get("account_type") != "PAPER":
        logger.error("Invalid or disconnected snapshot; sync blocked")
        return False
    if not str(payload.get("account_id", "")).upper().startswith(("DU", "DF")):
        logger.error("Invalid paper account identifier; sync blocked")
        return False

    endpoint = f"{base}/api/portfolio/ibkr/sync"
    headers = {"Content-Type": "application/json", "X-IBKR-Ingest-Key": ingest_key}
    try:
        logger.info("Pushing read-only paper snapshot to %s", endpoint)
        resp = requests.post(endpoint, headers=headers, json=payload, timeout=12,
                             allow_redirects=False)
        if resp.status_code == 200 and "json" in resp.headers.get("Content-Type", "").lower():
            logger.info("Paper snapshot accepted by StockAnalysis (HTTP 200)")
            return True
        logger.error("Snapshot rejected: HTTP %s, response type %s", resp.status_code,
                     resp.headers.get("Content-Type", "unknown"))
        # Never print server response bodies; they may contain sensitive information.
        return False
    except requests.exceptions.RequestException as exc:
        logger.error("Outbound request failed: %s", type(exc).__name__)
        return False


def run_single_sync(args) -> bool:
    """Collect and optionally push one complete, real paper account snapshot."""
    try:
        if args.mock:
            if not args.dry_run:
                logger.error("Mock snapshots are local dry-run only; cloud upload blocked")
                return False
            payload = generate_mock_snapshot()
        else:
            payload = collect_live_snapshot(
                host=args.host, port=args.port, client_id=args.client_id,
                timeout=args.timeout,
            )
    except Exception as exc:
        logger.error("IB Gateway collection failed: %s", exc)
        return False

    if args.dry_run:
        print("\n--- DRY RUN SNAPSHOT PAYLOAD (NO CLOUD PUSH) ---")
        print(json.dumps(payload, indent=2))
        print("--- END SNAPSHOT ---\n")
        return True

    effective_key = (os.getenv("IBKR_INGESTION_KEY") or "").strip()
    return push_to_backend(args.backend_url, effective_key, payload)


def main():
    parser = argparse.ArgumentParser(description="StockAnalysis IBKR Paper Trading Windows Adapter")
    parser.add_argument("--host", default=DEFAULT_GATEWAY_HOST, help="IB Gateway Host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=DEFAULT_GATEWAY_PORT, help="IB Gateway Socket Port (default: 4002)")
    parser.add_argument("--client-id", type=int, default=DEFAULT_CLIENT_ID, help="IB Client ID (default: 21)")
    parser.add_argument("--backend-url", default=DEFAULT_BACKEND_URL, help="StockAnalysis Backend URL")
    parser.add_argument("--interval", type=int, default=None, help="Continuous sync is disabled in Stage D1B")
    parser.add_argument("--timeout", type=int, default=15, help="Socket timeout in seconds (default: 15)")
    parser.add_argument("--once", action="store_true", help="Run once and exit")
    parser.add_argument("--dry-run", action="store_true", help="Print collected snapshot without pushing to backend")
    parser.add_argument("--mock", action="store_true", help="Use mock IBKR paper account data")

    args = parser.parse_args()
    if args.interval is not None:
        parser.error("Continuous sync is disabled in Stage D1B")


    logger.info("=== StockAnalysis IBKR Paper Trading Adapter Starting ===")
    logger.info(f"Target Gateway: {args.host}:{args.port} (clientId={args.client_id})")
    logger.info("Destination Backend: %s", args.backend_url)
    logger.info("READ-ONLY SAFETY: Order placement and modification are disabled.")

    if args.once or args.dry_run:
        success = run_single_sync(args)
        sys.exit(0 if success else 1)

    parser.error("Stage D1B permits only --once or --dry-run; continuous sync is disabled")


if __name__ == "__main__":
    main()
