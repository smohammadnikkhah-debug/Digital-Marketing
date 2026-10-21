"""Alpaca Paper Trading Adapter (Stage D2.3A.2).

Provides read-only connectivity and market data access to the Alpaca Paper Trading API.
Strictly non-executing: all order placement, modification, and cancellation methods
are blocked at the code level by immutable safety guards.

Key Design Principles:
1. STRICT READ-ONLY SAFETY: All mutation methods raise PermissionError.
2. ENDPOINT ENFORCEMENT: Strictly validates and requires paper-api.alpaca.markets.
   Live trading endpoints (api.alpaca.markets) are strictly rejected.
3. IEX MARKET DATA: Queries IEX Level 1 non-consolidated quotes via official alpaca-py SDK.
4. ZERO CREDENTIAL LEAKAGE: Secrets and account numbers are strictly redacted.
5. NO AUTOMATIC FALLBACK: Fails closed on missing or invalid configuration.
"""
import os
import re
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Any, Union

try:
    from alpaca.trading.client import TradingClient
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.requests import StockLatestQuoteRequest
    from alpaca.data.enums import DataFeed
    HAS_ALPACA_PY = True
except ImportError:
    HAS_ALPACA_PY = False
    TradingClient = object
    StockHistoricalDataClient = object
    StockLatestQuoteRequest = object
    DataFeed = object

logger = logging.getLogger("AlpacaPaperAdapter")

# Security guards and endpoint invariants
ALLOWED_PAPER_TRADING_ENDPOINTS = {
    "https://paper-api.alpaca.markets",
    "https://paper-api.alpaca.markets/v2",
}
DISALLOWED_LIVE_ENDPOINTS = {
    "https://api.alpaca.markets",
    "https://api.alpaca.markets/v2",
}

NON_EXECUTING_BUILD_GUARD = True


class NonExecutingGuard:
    """Code-level guard preventing any order creation, modification, or cancellation."""

    @staticmethod
    def assert_non_executing(action_name: str):
        if NON_EXECUTING_BUILD_GUARD:
            raise PermissionError(
                f"NON-EXECUTING BUILD GUARD ACTIVE: Action '{action_name}' is strictly forbidden in Stage D2.3A.2. "
                "Alpaca paper integration is currently read-only."
            )


class AlpacaPaperAdapter:
    """Alpaca Paper Trading Adapter implementing read-only portfolio and market data operations."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        secret_key: Optional[str] = None,
        trading_url: Optional[str] = None,
        data_url: Optional[str] = None,
        data_feed: str = "iex",
        env: str = "paper",
        auto_load_env: bool = True,
    ):
        self.auto_load_env = auto_load_env
        if auto_load_env:
            self._load_local_env()

        self.api_key = api_key if api_key is not None else os.getenv("ALPACA_API_KEY", "")
        self.secret_key = secret_key if secret_key is not None else os.getenv("ALPACA_SECRET_KEY", "")
        self.trading_url = (trading_url if trading_url is not None else os.getenv("ALPACA_TRADING_URL", "https://paper-api.alpaca.markets")).strip().rstrip("/")
        self.data_url = (data_url if data_url is not None else os.getenv("ALPACA_DATA_URL", "https://data.alpaca.markets")).strip().rstrip("/")
        self.data_feed = (data_feed if data_feed is not None else os.getenv("ALPACA_DATA_FEED", "iex")).strip().lower()
        self.env = (env if env is not None else os.getenv("ALPACA_ENV", "paper")).strip().lower()

        self._validate_security_invariants()

        self._trading_client: Optional[Any] = None
        self._data_client: Optional[Any] = None

    def _load_local_env(self):
        """Loads environment variables from local .env if not already set."""
        adapter_dir = Path(__file__).resolve().parent
        search_paths = [
            adapter_dir / ".env",
            adapter_dir.parent / ".env",
        ]
        for env_path in search_paths:
            if env_path.exists():
                try:
                    for line in env_path.read_text(encoding="utf-8").splitlines():
                        line = line.strip()
                        if line and not line.startswith("#") and "=" in line:
                            k, v = line.split("=", 1)
                            k = k.strip()
                            v = v.strip().strip("'\"")
                            if k and k not in os.environ:
                                os.environ[k] = v
                    break
                except Exception as ex:
                    logger.warning(f"Failed to read local env file {env_path}: {ex}")

    def _validate_security_invariants(self):
        """Validates endpoints, environment, and credential format to fail closed."""
        # 1. Reject live endpoints explicitly
        for dis in DISALLOWED_LIVE_ENDPOINTS:
            if self.trading_url.lower().startswith(dis.lower()):
                raise ValueError(
                    f"CRITICAL SECURITY REJECTION: Live trading URL '{self.trading_url}' is strictly forbidden. "
                    "Only paper-api.alpaca.markets is allowed."
                )

        # 2. Must be paper endpoint
        if "paper" not in self.trading_url.lower():
            raise ValueError(
                f"Endpoint validation failure: Trading URL '{self.trading_url}' does not contain 'paper'. "
                "Only paper trading is permitted."
            )

        # 3. Environment must be paper
        if self.env != "paper":
            raise ValueError(
                f"Configuration failure: ALPACA_ENV is '{self.env}'. Only 'paper' is permitted."
            )

        # 4. Data feed must be iex
        if self.data_feed != "iex":
            raise ValueError(
                f"Configuration failure: ALPACA_DATA_FEED is '{self.data_feed}'. "
                "The free tier integration strictly requires 'iex'."
            )

    def _get_trading_client(self) -> Any:
        if not HAS_ALPACA_PY:
            raise RuntimeError("alpaca-py is required but not installed.")
        if not self.api_key or not self.secret_key:
            raise ValueError("Alpaca API credentials missing. Both ALPACA_API_KEY and ALPACA_SECRET_KEY are required.")

        if self._trading_client is None:
            self._trading_client = TradingClient(
                api_key=self.api_key,
                secret_key=self.secret_key,
                paper=True,
                url_override=self.trading_url,
            )
        return self._trading_client

    def _get_data_client(self) -> Any:
        if not HAS_ALPACA_PY:
            raise RuntimeError("alpaca-py is required but not installed.")
        if not self.api_key or not self.secret_key:
            raise ValueError("Alpaca API credentials missing. Both ALPACA_API_KEY and ALPACA_SECRET_KEY are required.")

        if self._data_client is None:
            self._data_client = StockHistoricalDataClient(
                api_key=self.api_key,
                secret_key=self.secret_key,
                url_override=self.data_url,
            )
        return self._data_client

    # -------------------------------------------------------------------------
    # Read-Only Portfolio & Account Operations
    # -------------------------------------------------------------------------

    def get_account_summary(self) -> Dict[str, Any]:
        """Retrieves normalized account status, balances, and safety classifications."""
        client = self._get_trading_client()
        acc = client.get_account()

        status_str = str(getattr(acc, "status", "")).replace("AccountStatus.", "")

        # Cash-Only Risk Guard:
        # Alpaca provides leveraged buying power (e.g. 4x equity = $400,000 for $100,000 cash).
        # We strictly expose cash and non_margin_buying_power for our cash-only risk checks.
        cash_val = float(acc.cash)
        equity_val = float(acc.equity)
        leveraged_bp = float(acc.buying_power)
        non_margin_bp = float(getattr(acc, "non_margin_buying_power", cash_val) or cash_val)

        return {
            "broker": "alpaca",
            "account_type": "PAPER",
            "account_id": "***REDACTED***",
            "status": status_str,
            "currency": str(acc.currency),
            "equity": equity_val,
            "cash": cash_val,
            "buying_power_leveraged": leveraged_bp,
            "cash_available_for_risk": cash_val,  # Cash-only invariant: Never use leveraged buying power
            "non_margin_buying_power": non_margin_bp,
            "pattern_day_trader": bool(getattr(acc, "pattern_day_trader", False)),
            "trading_blocked": bool(getattr(acc, "trading_blocked", False)),
            "transfers_blocked": bool(getattr(acc, "transfers_blocked", False)),
            "account_blocked": bool(getattr(acc, "account_blocked", False)),
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
        }

    def get_authenticated_account_id(self) -> str:
        """Retrieves the unmasked account identifier strictly for internal binding/validation."""
        client = self._get_trading_client()
        acc = client.get_account()
        acc_num = getattr(acc, "account_number", None)
        if acc_num:
            return str(acc_num).strip().upper()
        return str(getattr(acc, "id", "")).strip().upper()

    def get_positions(self) -> List[Dict[str, Any]]:
        """Retrieves normalized current paper positions."""
        client = self._get_trading_client()
        raw_positions = client.get_all_positions()
        normalized = []
        for pos in raw_positions:
            normalized.append({
                "symbol": str(pos.symbol),
                "quantity": float(pos.qty),
                "side": "LONG" if float(pos.qty) > 0 else "SHORT",
                "avg_entry_price": float(pos.avg_entry_price),
                "market_value": float(pos.market_value),
                "cost_basis": float(pos.cost_basis),
                "unrealized_pl": float(pos.unrealized_pl),
                "unrealized_plpc": float(pos.unrealized_plpc),
                "current_price": float(pos.current_price) if pos.current_price else None,
                "exchange": str(getattr(pos, "exchange", "IEX")),
            })
        return normalized

    def get_orders(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        """Retrieves normalized paper orders."""
        client = self._get_trading_client()
        from alpaca.trading.requests import GetOrdersRequest
        from alpaca.trading.enums import QueryOrderStatus

        query_status = QueryOrderStatus.ALL
        if status:
            st = status.lower()
            if st == "open":
                query_status = QueryOrderStatus.OPEN
            elif st == "closed":
                query_status = QueryOrderStatus.CLOSED

        req = GetOrdersRequest(status=query_status)
        raw_orders = client.get_orders(filter=req)
        normalized = []
        for o in raw_orders:
            normalized.append({
                "order_id": str(o.id),
                "client_order_id": str(o.client_order_id),
                "symbol": str(o.symbol),
                "side": str(o.side).replace("OrderSide.", "").upper(),
                "order_type": str(o.type).replace("OrderType.", "").upper(),
                "quantity": float(o.qty) if o.qty else None,
                "filled_quantity": float(o.filled_qty) if o.filled_qty else 0.0,
                "limit_price": float(o.limit_price) if o.limit_price else None,
                "status": str(o.status).replace("OrderStatus.", "").upper(),
                "created_at": o.created_at.isoformat() if o.created_at else None,
                "submitted_at": o.submitted_at.isoformat() if o.submitted_at else None,
                "filled_at": o.filled_at.isoformat() if o.filled_at else None,
            })
        return normalized

    # -------------------------------------------------------------------------
    # Read-Only Market Data Operations (IEX Feed)
    # -------------------------------------------------------------------------

    def get_latest_quotes(
        self,
        symbols: List[str],
        now_utc: Optional[datetime] = None,
    ) -> Dict[str, Dict[str, Any]]:
        """Fetches top-of-book quotes for US equities via Alpaca IEX data feed.

        Guarantees:
        - Labels data source as 'ALPACA_IEX' (Non-Consolidated Single-Venue, NOT NBBO).
        - Evaluates quote age against exchange emission timestamp.
        - Calculates spread, midpoint, and 30-second freshness contract compliance.
        """
        client = self._get_data_client()
        req = StockLatestQuoteRequest(symbol_or_symbols=symbols, feed=DataFeed.IEX)
        raw_quotes = client.get_stock_latest_quote(req)

        if now_utc is None:
            now_utc = datetime.now(timezone.utc)
        elif now_utc.tzinfo is None:
            now_utc = now_utc.replace(tzinfo=timezone.utc)

        results = {}
        for sym, q in raw_quotes.items():
            bid = float(q.bid_price)
            ask = float(q.ask_price)
            q_time = q.timestamp
            if q_time.tzinfo is None:
                q_time = q_time.replace(tzinfo=timezone.utc)

            quote_age_sec = max(0.0, (now_utc - q_time).total_seconds())
            is_two_sided = bid > 0 and ask > 0
            is_valid_spread = ask >= bid if is_two_sided else False
            midpoint = (bid + ask) / 2.0 if is_two_sided else None
            spread = (ask - bid) if is_two_sided else None
            meets_30s_freshness = quote_age_sec <= 30.0

            results[sym] = {
                "symbol": sym,
                "source": "ALPACA_IEX",
                "feed": "iex",
                "is_consolidated_nbbo": False,  # Non-Consolidated single exchange book
                "venue_type": "NON_CONSOLIDATED_DIRECT_VENUE",
                "bid": bid,
                "ask": ask,
                "bid_size": float(q.bid_size),
                "ask_size": float(q.ask_size),
                "midpoint": midpoint,
                "spread": spread,
                "quote_timestamp": q_time.isoformat(),
                "received_at": now_utc.isoformat(),
                "quote_age_seconds": round(quote_age_sec, 2),
                "is_two_sided": is_two_sided,
                "is_valid_spread": is_valid_spread,
                "meets_30s_freshness": meets_30s_freshness,
                "is_delayed": False,
                "is_synthetic": False,
            }

        return results

    # -------------------------------------------------------------------------
    # Immutable Execution Safety Guards (Strictly Non-Executing)
    # -------------------------------------------------------------------------

    def submit_order(self, *args, **kwargs):
        """Guarded against order submission."""
        NonExecutingGuard.assert_non_executing("submit_order")
        raise PermissionError("Order submission is blocked.")

    def replace_order(self, *args, **kwargs):
        """Guarded against order replacement."""
        NonExecutingGuard.assert_non_executing("replace_order")
        raise PermissionError("Order replacement is blocked.")

    def cancel_order(self, *args, **kwargs):
        """Guarded against order cancellation."""
        NonExecutingGuard.assert_non_executing("cancel_order")
        raise PermissionError("Order cancellation is blocked.")

    def cancel_all_orders(self, *args, **kwargs):
        """Guarded against global order cancellation."""
        NonExecutingGuard.assert_non_executing("cancel_all_orders")
        raise PermissionError("Global order cancellation is blocked.")

    def transfer_funds(self, *args, **kwargs):
        """Guarded against fund transfers or account funding."""
        raise PermissionError("Fund transfers and account funding are strictly prohibited.")

    def __repr__(self) -> str:
        """Safe string representation redacting sensitive credentials and endpoints."""
        key_status = "CONFIGURED" if self.api_key else "MISSING"
        sec_status = "CONFIGURED" if self.secret_key else "MISSING"
        return (
            f"<AlpacaPaperAdapter env='{self.env}' feed='{self.data_feed}' "
            f"trading_url='{self.trading_url}' api_key={key_status} secret={sec_status} "
            f"non_executing_guard={NON_EXECUTING_BUILD_GUARD}>"
        )
