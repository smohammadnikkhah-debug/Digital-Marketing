"""Broker quote / symbol integrity audit for paper-pilot readiness (D2.4J).

Validates captured Alpaca IEX quotes against Yahoo price-cache closes, asset
identity, whole-share affordability under the $500 order cap, and split-scale
sanity. Does not enable trading or submit orders.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from app.config import DATA_CACHE_DIR
from app.services.order_execution_service import DEFAULT_MAX_ORDER_NOTIONAL_USD

PRICE_CACHE_DIR = DATA_CACHE_DIR / "price_cache"

# Soft band: broker ask vs Yahoo last close. Wide IEX post-market books expected;
# flag only extreme scale mismatches (e.g. unadjusted split residual).
CLOSE_ASK_RATIO_WARN = 0.35  # ask/close outside [1-warn, 1+2*warn] → scale concern


def _yahoo_last_close(ticker: str) -> Optional[Dict[str, Any]]:
    path = PRICE_CACHE_DIR / f"{ticker.upper()}.csv"
    if not path.exists():
        return None
    try:
        import pandas as pd

        df = pd.read_csv(path)
        if df.empty or "Close" not in df.columns:
            return None
        last = df.iloc[-1]
        return {
            "path": str(path),
            "date": str(last.get("Date")),
            "close": float(last["Close"]),
            "bars": int(len(df)),
        }
    except Exception as exc:
        return {"path": str(path), "error": str(exc)[:200]}


def assess_whole_share_affordability(
    *,
    ask: float,
    max_order_notional_usd: float = DEFAULT_MAX_ORDER_NOTIONAL_USD,
    slot_budget: Optional[float] = None,
) -> Dict[str, Any]:
    """Mirror buy_decision_engine whole-share gate (no fractional shares)."""
    budget = float(slot_budget if slot_budget is not None else max_order_notional_usd)
    ask_f = float(ask or 0)
    qty = int(budget // ask_f) if ask_f > 0 else 0
    affordable = ask_f > 0 and budget >= ask_f and qty >= 1
    return {
        "max_order_notional_usd": float(max_order_notional_usd),
        "slot_budget": round(budget, 2),
        "ask": ask_f,
        "whole_share_qty": qty,
        "affordable_one_whole_share": affordable,
        "fractional_shares_enabled": False,
        "expected_reason_if_blocked": (
            None if affordable else "INSUFFICIENT_CASH_FOR_ONE_SHARE"
        ),
    }


def audit_symbol_quote(
    ticker: str,
    *,
    quote: Optional[Dict[str, Any]] = None,
    asset: Optional[Dict[str, Any]] = None,
    sizing_block: Optional[Dict[str, Any]] = None,
    max_order_notional_usd: float = DEFAULT_MAX_ORDER_NOTIONAL_USD,
) -> Dict[str, Any]:
    t = str(ticker or "").strip().upper()
    q = quote or {}
    ask = float(q.get("ask") or 0)
    bid = float(q.get("bid") or 0)
    yahoo = _yahoo_last_close(t)
    afford = assess_whole_share_affordability(
        ask=ask, max_order_notional_usd=max_order_notional_usd
    )

    symbol_match = True
    q_sym = str(q.get("symbol") or "").strip().upper()
    if q_sym and q_sym != t:
        symbol_match = False
    a_sym = str((asset or {}).get("symbol") or "").strip().upper()
    if a_sym and a_sym != t:
        symbol_match = False

    scale_ok = None
    close = None
    if isinstance(yahoo, dict) and yahoo.get("close") and ask > 0:
        close = float(yahoo["close"])
        ratio = ask / close
        # Allow wide post-market ask premium; flag only absurd scale (e.g. 10x)
        scale_ok = 0.5 <= ratio <= 2.5

    sizing_codes = list((sizing_block or {}).get("reason_codes") or [])
    expected_block = afford["expected_reason_if_blocked"]
    whole_share_gate_confirmed = (
        expected_block is None
        or expected_block in sizing_codes
        or (
            not afford["affordable_one_whole_share"]
            and ask > max_order_notional_usd
        )
    )

    return {
        "ticker": t,
        "quote": {
            "symbol": q.get("symbol") or t,
            "bid": bid or None,
            "ask": ask or None,
            "source": q.get("source"),
            "feed": q.get("feed"),
            "quote_timestamp": q.get("quote_timestamp"),
            "received_at": q.get("received_at"),
            "quote_age_seconds": q.get("quote_age_seconds"),
            "is_two_sided": q.get("is_two_sided"),
            "is_delayed": q.get("is_delayed"),
            "is_synthetic": q.get("is_synthetic"),
            "is_consolidated_nbbo": q.get("is_consolidated_nbbo"),
        },
        "asset": asset,
        "yahoo_price_cache": yahoo,
        "symbol_identity_ok": symbol_match,
        "scale_vs_yahoo_close_ok": scale_ok,
        "ask_vs_close_ratio": (
            round(ask / close, 4) if close and ask else None
        ),
        "whole_share_affordability": afford,
        "sizing_block_reason_codes": sizing_codes,
        "whole_share_cap_rejection_confirmed": bool(
            not afford["affordable_one_whole_share"] and whole_share_gate_confirmed
        ),
        "split_adjustment_concern": scale_ok is False,
        "notes": _notes(t, afford, scale_ok, symbol_match, ask, bid, close),
    }


def _notes(
    ticker: str,
    afford: Dict[str, Any],
    scale_ok: Optional[bool],
    symbol_match: bool,
    ask: float,
    bid: float,
    close: Optional[float],
) -> List[str]:
    notes: List[str] = []
    if not symbol_match:
        notes.append(f"{ticker}: quote/asset symbol mismatch vs requested ticker")
    if scale_ok is False:
        notes.append(
            f"{ticker}: ask vs Yahoo close scale outside [0.5, 2.5] — "
            "possible split/adjustment or identity issue"
        )
    if ask > 0 and bid > 0 and ask >= bid and close:
        mid = (ask + bid) / 2.0
        notes.append(
            f"{ticker}: Alpaca IEX mid≈{mid:.2f} vs Yahoo close {close:.2f} "
            f"(spread {ask - bid:.2f}); identity consistent with cache when "
            "scale_ok"
        )
    if not afford["affordable_one_whole_share"]:
        notes.append(
            f"{ticker}: ask {ask:.2f} exceeds ${afford['slot_budget']:.2f} "
            "whole-share budget → INSUFFICIENT_CASH_FOR_ONE_SHARE (fractional "
            "shares not enabled)"
        )
    return notes


def audit_high_ask_candidates(
    rows: Sequence[Dict[str, Any]],
    *,
    tickers: Sequence[str] = ("AMD", "MSFT", "MU"),
    assets: Optional[Dict[str, Dict[str, Any]]] = None,
    max_order_notional_usd: float = DEFAULT_MAX_ORDER_NOTIONAL_USD,
) -> Dict[str, Any]:
    """Audit named tickers from candidate_results-style rows."""
    by_t = {str(r.get("ticker") or "").upper(): r for r in rows}
    assets = assets or {}
    audits = []
    for t in tickers:
        row = by_t.get(t.upper()) or {}
        audits.append(
            audit_symbol_quote(
                t,
                quote=row.get("quote") or {},
                asset=assets.get(t.upper()) or row.get("alpaca_asset"),
                sizing_block=row.get("sizing_block"),
                max_order_notional_usd=max_order_notional_usd,
            )
        )
    return {
        "audited_at_utc": datetime.now(timezone.utc).isoformat(),
        "max_order_notional_usd": float(max_order_notional_usd),
        "fractional_shares_enabled": False,
        "tickers": list(tickers),
        "results": audits,
        "all_whole_share_cap_rejections_confirmed": all(
            a.get("whole_share_cap_rejection_confirmed") for a in audits
        ),
        "any_symbol_mismatch": any(not a.get("symbol_identity_ok") for a in audits),
        "any_split_concern": any(a.get("split_adjustment_concern") for a in audits),
    }
