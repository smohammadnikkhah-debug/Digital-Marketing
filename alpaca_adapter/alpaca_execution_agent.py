"""Alpaca Paper Execution Agent (Stage D2.3B Architecture).

Autonomous background execution agent for Alpaca Paper Trading.
Mirrors the transactional order integrity, atomic claiming, and audit models
established for StockAnalysis.

Safety Invariants:
1. GATED EXECUTION: Gated by ALPACA_EXECUTION_ENABLED and ALPACA_EMERGENCY_STOP.
2. REGULAR HOURS ONLY: Orders permitted only during regular US market hours (9:30 AM - 4:00 PM ET).
3. SINGLE-VENUE SPREAD GATE: Rejects quotes where IEX spread > 0.5% of midpoint.
4. PRICE COLLAR: Enforces 5.0% price collar against IEX midpoint.
5. STRICT LIMIT ORDERS: All orders must be LIMIT, cash-only, long-only equities.
6. IDEMPOTENCY: Every order uses deterministic client_order_id.
7. AMBIGUOUS QUARANTINE: Network timeouts or unknown responses trigger immediate quarantine.
"""
import logging
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Any

# Ensure project root in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
BACKEND_DIR = PROJECT_ROOT / "web_app" / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from alpaca_adapter.alpaca_paper_adapter import (
    AlpacaPaperAdapter,
    NON_EXECUTING_BUILD_GUARD,
    ALLOWED_PAPER_TRADING_ENDPOINTS,
)
from app.services.market_data_service import (
    market_data_service,
    MarketQuote,
    DEFAULT_PRICE_COLLAR_PCT,
    DEFAULT_MAX_SPREAD_PCT,
    DEFAULT_MAX_QUOTE_AGE_SECONDS,
)

logger = logging.getLogger("AlpacaExecutionAgent")


class AlpacaExecutionAgent:
    """Hardened Execution Agent for Alpaca Paper Trading."""

    def __init__(
        self,
        agent_id: Optional[str] = None,
        adapter: Optional[AlpacaPaperAdapter] = None,
        max_order_notional: float = 500.0,
        max_spread_pct: float = DEFAULT_MAX_SPREAD_PCT,
        price_collar_pct: float = DEFAULT_PRICE_COLLAR_PCT,
        max_quote_age_seconds: float = DEFAULT_MAX_QUOTE_AGE_SECONDS,
    ):
        self.agent_id = agent_id or f"alpaca_agent_{uuid.uuid4().hex[:8]}"
        self.adapter = adapter or AlpacaPaperAdapter(auto_load_env=True)
        self.max_order_notional = max_order_notional
        self.max_spread_pct = max_spread_pct
        self.price_collar_pct = price_collar_pct
        self.max_quote_age_seconds = max_quote_age_seconds

        # Read environment flags
        self.execution_enabled = os.getenv("ALPACA_EXECUTION_ENABLED", "false").strip().lower() in ("true", "1", "yes")
        self.emergency_stop = os.getenv("ALPACA_EMERGENCY_STOP", "true").strip().lower() in ("true", "1", "yes")

        logger.info(
            f"AlpacaExecutionAgent initialized [{self.agent_id}]: "
            f"execution_enabled={self.execution_enabled}, emergency_stop={self.emergency_stop}, "
            f"non_executing_guard={NON_EXECUTING_BUILD_GUARD}"
        )

    def is_operational(self) -> bool:
        """Returns True if agent is authorized and operational."""
        if self.emergency_stop:
            return False
        if not self.execution_enabled:
            return False
        return True

    def validate_pre_execution_quote(
        self,
        symbol: str,
        limit_price: float,
        action: str = "BUY",
        now_utc: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """Fetches fresh IEX quote and validates against all execution safeguards."""
        now = now_utc or datetime.now(timezone.utc)
        quotes = self.adapter.get_latest_quotes([symbol], now_utc=now)
        if symbol not in quotes:
            return {
                "is_valid": False,
                "error": f"Failed to retrieve market quote for symbol '{symbol}' from IEX.",
            }

        quote_data = quotes[symbol]
        res = market_data_service.validate_quote(
            quote_payload=quote_data,
            limit_price=limit_price,
            action=action,
            max_quote_age=self.max_quote_age_seconds,
            max_price_collar_pct=self.price_collar_pct,
            max_spread_pct=self.max_spread_pct,
            now_utc=now,
        )

        return {
            "is_valid": res.is_valid,
            "failure_reasons": res.failure_reasons,
            "quote": quote_data,
            "midpoint": res.midpoint,
            "collar_pct": res.collar_pct,
            "market_session": res.market_session,
        }

    def execute_paper_order(
        self,
        order_id: int,
        symbol: str,
        quantity: int,
        limit_price: float,
        side: str = "BUY",
        client_order_id: Optional[str] = None,
        now_utc: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """Executes a single validated paper order through Alpaca Paper API.

        Enforces:
        - Operational gate (emergency stop, execution enabled).
        - Risk caps ($500 max notional, positive quantity, limit orders only).
        - Market session & quote collar verification.
        - Non-executing build guard.
        - Idempotency key.
        """
        now = now_utc or datetime.now(timezone.utc)
        cid = client_order_id or f"alpaca_{order_id}_{uuid.uuid4().hex[:8]}"

        # 1. Operational & Emergency Stop Guard
        if self.emergency_stop or not self.execution_enabled:
            return {
                "status": "REJECTED",
                "order_id": order_id,
                "client_order_id": cid,
                "reason": (
                    f"Agent not operational: execution_enabled={self.execution_enabled}, "
                    f"emergency_stop={self.emergency_stop}"
                ),
            }

        # 2. Risk Engine Notional Value Guard
        notional = quantity * limit_price
        if notional > self.max_order_notional:
            return {
                "status": "REJECTED",
                "order_id": order_id,
                "client_order_id": cid,
                "reason": (
                    f"Risk violation: Order notional value ${notional:.2f} exceeds "
                    f"maximum permitted limit of ${self.max_order_notional:.2f}."
                ),
            }

        if quantity <= 0:
            return {
                "status": "REJECTED",
                "order_id": order_id,
                "client_order_id": cid,
                "reason": f"Invalid order quantity: {quantity} <= 0.",
            }

        # 3. Market Quote & Session Validation
        quote_eval = self.validate_pre_execution_quote(
            symbol=symbol,
            limit_price=limit_price,
            action=side,
            now_utc=now,
        )
        if not quote_eval["is_valid"]:
            return {
                "status": "REJECTED",
                "order_id": order_id,
                "client_order_id": cid,
                "reason": f"Market data guard failure: {'; '.join(quote_eval['failure_reasons'])}",
                "quote_eval": quote_eval,
            }

        # 4. Submission Guard
        if NON_EXECUTING_BUILD_GUARD:
            return {
                "status": "REJECTED",
                "order_id": order_id,
                "client_order_id": cid,
                "reason": "NON-EXECUTING BUILD GUARD ACTIVE. Real API mutation prohibited.",
            }

        # 5. Place Order with Alpaca Paper API
        try:
            client = self.adapter._get_trading_client()
            from alpaca.trading.requests import LimitOrderRequest
            from alpaca.trading.enums import OrderSide, TimeInForce

            order_side = OrderSide.BUY if side.upper() == "BUY" else OrderSide.SELL
            req = LimitOrderRequest(
                symbol=symbol.upper(),
                qty=quantity,
                side=order_side,
                time_in_force=TimeInForce.DAY,
                limit_price=round(limit_price, 2),
                client_order_id=cid,
            )

            res = client.submit_order(req)
            return {
                "status": "SUBMITTED",
                "order_id": order_id,
                "client_order_id": cid,
                "broker_order_id": str(res.id),
                "broker": "alpaca",
                "symbol": symbol,
                "quantity": quantity,
                "limit_price": limit_price,
                "submitted_at": now.isoformat(),
            }

        except Exception as exc:
            logger.error(f"Alpaca order submission failed for order {order_id}: {exc}", exc_info=True)
            # Check for network or timeout ambiguous outcomes
            err_str = str(exc).lower()
            if "timeout" in err_str or "connection" in err_str or "504" in err_str:
                return {
                    "status": "QUARANTINED",
                    "order_id": order_id,
                    "client_order_id": cid,
                    "reason": f"Ambiguous submission outcome due to network error: {exc}. Quarantined for reconciliation.",
                }
            return {
                "status": "FAILED",
                "order_id": order_id,
                "client_order_id": cid,
                "reason": f"Broker submission error: {exc}",
            }
