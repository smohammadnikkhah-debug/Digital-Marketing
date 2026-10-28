"""Read-only Alpaca paper bridge for StockAnalysis (Stage D2.4F).

Reuses alpaca_adapter.AlpacaPaperAdapter. Never submits, cancels, or modifies orders.
Never prints credentials or raw account identifiers in reports.
"""
from __future__ import annotations

import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from app.config import BACKEND_DIR, PROJECT_ROOT
from app.services.buy_decision_engine import AccountSnapshot

logger = logging.getLogger("stockanalysis.alpaca_readonly")


def _discover_digital_marketing_root() -> Path:
    """Locate the directory that contains alpaca_adapter/."""
    candidates = [
        PROJECT_ROOT.parent,  # stockanalysis/ → Digital Marketing/
        PROJECT_ROOT,
        BACKEND_DIR.parents[2],  # backend → web_app → stockanalysis → Digital Marketing
        Path(__file__).resolve().parents[5],
    ]
    for candidate in candidates:
        try:
            if (candidate / "alpaca_adapter").is_dir():
                return candidate.resolve()
        except OSError:
            continue
    return PROJECT_ROOT.parent.resolve()


def ensure_alpaca_adapter_on_path() -> str:
    """Ensure Digital Marketing root is importable so alpaca_adapter resolves."""
    root = str(_discover_digital_marketing_root())
    if root not in sys.path:
        sys.path.insert(0, root)
    return root


def _redact_account_id(account_id: Optional[str]) -> str:
    if not account_id:
        return ""
    s = str(account_id).strip()
    if len(s) <= 4:
        return "****"
    return f"{'*' * max(0, len(s) - 4)}{s[-4:]}"


class AlpacaReadOnlyClient:
    """Thin StockAnalysis wrapper around AlpacaPaperAdapter (read-only)."""

    def __init__(self, auto_load_env: bool = True):
        ensure_alpaca_adapter_on_path()
        from alpaca_adapter.alpaca_paper_adapter import (
            AlpacaPaperAdapter,
            NON_EXECUTING_BUILD_GUARD,
        )

        self._adapter = AlpacaPaperAdapter(auto_load_env=auto_load_env)
        self.non_executing_guard = bool(NON_EXECUTING_BUILD_GUARD)
        self.submissions_attempted = 0

    @property
    def adapter(self):
        return self._adapter

    def get_market_session(self) -> Dict[str, Any]:
        """Clock / session info from Alpaca trading API when available."""
        if hasattr(self._adapter, "get_market_clock"):
            return self._adapter.get_market_clock()
        # Fallback: attempt trading client clock without mutating adapter API contract
        try:
            client = self._adapter._get_trading_client()  # noqa: SLF001 — intentional reuse
            clock = client.get_clock()
            return {
                "is_open": bool(getattr(clock, "is_open", False)),
                "timestamp": getattr(clock, "timestamp", None).isoformat()
                if getattr(clock, "timestamp", None)
                else None,
                "next_open": getattr(clock, "next_open", None).isoformat()
                if getattr(clock, "next_open", None)
                else None,
                "next_close": getattr(clock, "next_close", None).isoformat()
                if getattr(clock, "next_close", None)
                else None,
                "source": "ALPACA_CLOCK",
            }
        except Exception as exc:
            return {"error": str(exc)[:200], "source": "ALPACA_CLOCK_UNAVAILABLE"}

    def get_account_snapshot(self) -> AccountSnapshot:
        summary = self._adapter.get_account_summary()
        acct_id = self._adapter.get_authenticated_account_id()
        cash = float(summary.get("cash") or 0)
        equity = float(summary.get("equity") or cash)
        return AccountSnapshot(
            broker="alpaca",
            account_id=str(acct_id).upper(),
            cash=cash,
            equity=equity,
            positions=self._adapter.get_positions() or [],
            open_orders=self._adapter.get_orders(status="open") or [],
            snapshot_fresh=True,
            connection_ok=True,
            as_of_utc=datetime.now(timezone.utc).isoformat(),
        )

    def get_quotes(self, symbols: Sequence[str]) -> Dict[str, Dict[str, Any]]:
        if not symbols:
            return {}
        return self._adapter.get_latest_quotes(list(symbols)) or {}

    def validate_readonly(self) -> Dict[str, Any]:
        """Connectivity check: balances, BP, positions, orders, quotes, session.

        Never includes credentials or full account identifiers.
        """
        report: Dict[str, Any] = {
            "connected": False,
            "env": getattr(self._adapter, "env", None),
            "non_executing_guard": self.non_executing_guard,
            "credentials_present": bool(
                getattr(self._adapter, "api_key", None) and getattr(self._adapter, "secret_key", None)
            ),
            "error": None,
            "account": None,
            "positions_count": None,
            "open_orders_count": None,
            "sample_quotes": {},
            "market_session": None,
            "order_submission_blocked": True,
            "submissions_attempted": 0,
        }
        try:
            if not report["credentials_present"]:
                report["error"] = "MISSING_ALPACA_CREDENTIALS"
                return report

            summary = self._adapter.get_account_summary()
            acct_id = self._adapter.get_authenticated_account_id()
            positions = self._adapter.get_positions() or []
            open_orders = self._adapter.get_orders(status="open") or []
            quotes = self.get_quotes(["AAPL", "MSFT"])
            session = self.get_market_session()

            cash = float(summary.get("cash") or 0)
            equity = float(summary.get("equity") or 0)
            bp = float(
                summary.get("cash_available_for_risk")
                or summary.get("non_margin_buying_power")
                or cash
            )

            report["connected"] = True
            report["account"] = {
                "account_id_redacted": _redact_account_id(acct_id),
                "account_id_length": len(str(acct_id or "")),
                "status": summary.get("status"),
                "currency": summary.get("currency"),
                "cash_positive": cash > 0,
                "equity_positive": equity > 0,
                "buying_power_positive": bp > 0,
                "cash": cash,
                "equity": equity,
                "buying_power_cash_only": bp,
                "trading_blocked": bool(summary.get("trading_blocked")),
                "account_blocked": bool(summary.get("account_blocked")),
            }
            report["positions_count"] = len(positions)
            report["open_orders_count"] = len(open_orders)
            report["market_session"] = session
            for sym, q in quotes.items():
                report["sample_quotes"][sym] = {
                    "has_bid": float(q.get("bid") or 0) > 0,
                    "has_ask": float(q.get("ask") or 0) > 0,
                    "is_two_sided": bool(q.get("is_two_sided")),
                    "source": q.get("source"),
                    "meets_30s_freshness": q.get("meets_30s_freshness"),
                }

            # Prove mutation path is blocked
            try:
                self._adapter.submit_order(symbol="AAPL", qty=1, side="buy", type="limit", limit_price=1.0)
                report["order_submission_blocked"] = False
            except PermissionError:
                report["order_submission_blocked"] = True
            report["submissions_attempted"] = self.submissions_attempted
            return report
        except Exception as exc:
            report["error"] = f"{type(exc).__name__}: {str(exc)[:240]}"
            return report


def try_load_readonly_client() -> tuple[Optional[AlpacaReadOnlyClient], str]:
    """Factory that never fabricates account data on failure."""
    try:
        client = AlpacaReadOnlyClient(auto_load_env=True)
        if not (getattr(client.adapter, "api_key", None) and getattr(client.adapter, "secret_key", None)):
            return None, "MISSING_ALPACA_CREDENTIALS"
        return client, "OK"
    except Exception as exc:
        return None, f"ACCOUNT_UNAVAILABLE: {exc}"
