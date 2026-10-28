"""Simulated opportunity performance tracking (Stage D2.4K).

Fill approximation (EXPLICIT — not a real broker fill):
  A simulated BUY LIMIT at `limit_price` is marked WOULD_HAVE_FILLED if any
  subsequent regular-session bar has Low <= limit_price within `lookforward_bars`
  trading days after the signal date. Otherwise WOULD_NOT_HAVE_FILLED.

This is a research approximation using Yahoo/cache OHLCV only. It does not
claim broker acknowledgement, partial fills, or actual paper executions.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional, Sequence

from app.services.scanner_service import scanner_service

FILL_APPROXIMATION_ID = "BUY_LIMIT_TOUCHED_BY_SUBSEQUENT_LOW"
FILL_APPROXIMATION_DOC = (
    "WOULD_HAVE_FILLED iff a subsequent regular-session bar Low <= proposed "
    "limit_price within lookforward_bars after signal date. NOT a broker fill."
)


def _bar_dates_and_ohlc(df) -> List[Dict[str, Any]]:
    rows = []
    if df is None or getattr(df, "empty", True):
        return rows
    for idx, row in df.iterrows():
        try:
            d = idx.date() if hasattr(idx, "date") else date.fromisoformat(str(idx)[:10])
        except Exception:
            continue
        rows.append(
            {
                "date": d,
                "open": float(row.get("Open", row.get("open", 0)) or 0),
                "high": float(row.get("High", row.get("high", 0)) or 0),
                "low": float(row.get("Low", row.get("low", 0)) or 0),
                "close": float(row.get("Close", row.get("close", 0)) or 0),
            }
        )
    return rows


def evaluate_simulated_opportunity(
    *,
    ticker: str,
    signal_date: str,
    signal_price: Optional[float],
    entry_rule: Optional[str],
    proposed_limit: Optional[float],
    proposed_qty: Optional[int],
    lookforward_bars: int = 5,
    benchmark_ticker: str = "SPY",
) -> Dict[str, Any]:
    """Compute fill approximation + path metrics from local price cache."""
    t = str(ticker or "").upper()
    out: Dict[str, Any] = {
        "ticker": t,
        "signal_date": str(signal_date)[:10] if signal_date else None,
        "strategy_rule": entry_rule,
        "signal_price": signal_price,
        "proposed_limit": proposed_limit,
        "proposed_quantity": proposed_qty,
        "fill_approximation_id": FILL_APPROXIMATION_ID,
        "fill_approximation_doc": FILL_APPROXIMATION_DOC,
        "is_real_broker_fill": False,
        "lookforward_bars": lookforward_bars,
        "sufficient_data": False,
    }
    try:
        sig_d = date.fromisoformat(str(signal_date)[:10])
    except Exception:
        out["error"] = "INVALID_SIGNAL_DATE"
        return out

    df = scanner_service.get_price_df(t)
    bars = _bar_dates_and_ohlc(df)
    if not bars:
        out["error"] = "NO_PRICE_BARS"
        return out

    # bars at/after signal
    after = [b for b in bars if b["date"] > sig_d][: max(int(lookforward_bars), 0)]
    on_signal = next((b for b in bars if b["date"] == sig_d), None)
    if signal_price is None and on_signal:
        signal_price = on_signal["close"]
        out["signal_price"] = signal_price

    out["subsequent_reference_prices"] = [
        {"date": b["date"].isoformat(), "close": b["close"], "low": b["low"], "high": b["high"]}
        for b in after
    ]

    if not after:
        out["error"] = "NO_SUBSEQUENT_BARS"
        out["would_have_filled_approx"] = None
        return out

    out["sufficient_data"] = True
    limit = float(proposed_limit) if proposed_limit is not None else None
    filled = False
    fill_bar = None
    if limit is not None and limit > 0:
        for b in after:
            if b["low"] <= limit:
                filled = True
                fill_bar = b
                break
    out["would_have_filled_approx"] = filled if limit else None
    out["approx_fill_date"] = fill_bar["date"].isoformat() if fill_bar else None
    out["approx_fill_label"] = (
        "WOULD_HAVE_FILLED" if filled else "WOULD_NOT_HAVE_FILLED" if limit else "NO_LIMIT"
    )

    # Path metrics from signal close
    base = float(signal_price) if signal_price else (on_signal["close"] if on_signal else None)
    if base and base > 0:
        highs = [b["high"] for b in after]
        lows = [b["low"] for b in after]
        last_close = after[-1]["close"]
        mfe = (max(highs) - base) / base * 100.0
        mae = (min(lows) - base) / base * 100.0
        ret = (last_close - base) / base * 100.0
        out["subsequent_return_pct"] = round(ret, 4)
        out["max_favorable_excursion_pct"] = round(mfe, 4)
        out["max_adverse_excursion_pct"] = round(mae, 4)
        out["horizon_bars"] = len(after)

        # Benchmark comparison (same dates)
        bdf = scanner_service.get_price_df(benchmark_ticker)
        bbars = _bar_dates_and_ohlc(bdf)
        b_on = next((b for b in bbars if b["date"] == sig_d), None)
        b_after = [b for b in bbars if b["date"] > sig_d][: len(after)]
        if b_on and b_after and b_on["close"] > 0:
            b_ret = (b_after[-1]["close"] - b_on["close"]) / b_on["close"] * 100.0
            out["benchmark_ticker"] = benchmark_ticker
            out["benchmark_return_pct"] = round(b_ret, 4)
            out["excess_return_pct"] = round(ret - b_ret, 4)

    return out


def attach_performance_to_proposals(
    results: Sequence[Dict[str, Any]],
    *,
    lookforward_bars: int = 5,
) -> List[Dict[str, Any]]:
    """Annotate pipeline results that have simulated proposals."""
    out = []
    for row in results:
        prop = row.get("simulated_proposal") or {}
        if prop.get("status") != "SIMULATED":
            continue
        inv = row.get("investment_decision") or {}
        perf = evaluate_simulated_opportunity(
            ticker=row.get("ticker") or prop.get("symbol"),
            signal_date=row.get("market_as_of_date") or "",
            signal_price=None,
            entry_rule=row.get("entry_rule"),
            proposed_limit=prop.get("proposed_limit_price"),
            proposed_qty=prop.get("proposed_quantity"),
            lookforward_bars=lookforward_bars,
        )
        out.append(
            {
                "ticker": row.get("ticker"),
                "investment_classification": inv.get("classification"),
                "performance": perf,
            }
        )
    return out
