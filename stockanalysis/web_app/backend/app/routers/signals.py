from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.engine_bridge import bridge
from app.database import get_db
from app.models import WatchlistStock
from app.services.universe_manager import universe_manager
from app.services.scanner_service import scanner_service
from app.services.shariah_eligibility import attach_execution_eligibility
from app.services.investment_eligibility import attach_investment_eligibility
from app.config import (
    DATA_PROVENANCE,
    INVESTMENT_ELIGIBILITY_MODE,
    V40_SIGNAL_SOURCE,
    V40_STRATEGY_VERSION,
)

router = APIRouter(prefix="/api/signals", tags=["Signals"])


def _enrich_signal_for_api(sig: Dict[str, Any], shariah_map: Dict[str, Dict[str, str]]) -> Dict[str, Any]:
    """Attach Shariah overlay + USER_POLICY eligibility for dashboard visibility."""
    out = dict(sig)
    ticker = out.get("ticker", "")
    if ticker in shariah_map:
        out["shariah_status"] = shariah_map[ticker]["status"]
    stock_info = universe_manager.get_stock(ticker) or {}
    stock_name = stock_info.get("name", out.get("name", ticker))
    out["name"] = out.get("name") or stock_name
    out["company_name"] = stock_name
    out["sector"] = stock_info.get("sector", out.get("sector", "Technology"))
    out["industry"] = stock_info.get("industry", out.get("industry", ""))
    out["exchange"] = stock_info.get("exchange", out.get("exchange", "NASDAQ"))
    out["data_status"] = stock_info.get("data_status", out.get("data_status", "READY"))
    # Ensure V4.0 scanner identity is explicit when missing (legacy seeded rows)
    out.setdefault("signal_source", V40_SIGNAL_SOURCE)
    out.setdefault("strategy_version", V40_STRATEGY_VERSION)
    # Preserve legacy Shariah classification fields, then overlay USER_POLICY for dashboard
    out = attach_execution_eligibility(out)
    mode = (INVESTMENT_ELIGIBILITY_MODE or "USER_POLICY").strip().upper()
    out = attach_investment_eligibility(out, eligibility_mode=mode)
    # Keep excluded / review-required stocks visible in research monitoring
    out["research_visible"] = True
    out["user_policy_status"] = (out.get("investment_eligibility") or {}).get("user_policy_status")
    out["policy_blocking_reason"] = (out.get("investment_eligibility") or {}).get("blocking_reason") or ""
    return out


def _snapshot_is_live_refresh(active_snap: Dict[str, Any], signals_list: List[Dict[str, Any]]) -> bool:
    """True only when snapshot signals were produced by a live scan, not frozen seed."""
    if any(s.get("is_fresh_analysis") is True for s in signals_list):
        return True
    if any(s.get("provenance_mode") == "LIVE_SCAN" for s in signals_list):
        return True
    # Legacy snapshots without provenance: treat as refreshed only if refresh_job_id present
    return bool(active_snap.get("refresh_job_id"))


@router.get("")
def get_today_signals(
    mode: Optional[str] = Query(None, description="'baseline' for frozen 28 stocks, otherwise expanded universe"),
    db: Session = Depends(get_db)
):
    """Retrieve today's signals across broad market universe or frozen baseline."""
    # Read watchlist from DB to get updated Shariah statuses
    stocks = db.query(WatchlistStock).all()
    shariah_map = {
        s.ticker: {
            "status": s.shariah_status,
            "source": s.shariah_source,
            "date": s.shariah_date
        } for s in stocks
    }

    if mode == "baseline":
        # Explicit frozen baseline — never advertised as a fresh opportunity scan
        payload = bridge.get_today_signals(custom_shariah=shariah_map)
        enriched = [_enrich_signal_for_api(s, shariah_map) for s in payload.get("signals", [])]
        for s in enriched:
            s["provenance_mode"] = "FROZEN_BASELINE"
            s["is_fresh_analysis"] = False
            s["validation_status"] = s.get("validation_status") or "FROZEN_BASELINE"
            s["data_freshness"] = "FROZEN_BASELINE"
        payload["signals"] = enriched
        payload["data_provenance"] = {
            **DATA_PROVENANCE,
            "mode": "FROZEN_BASELINE",
            "is_refreshed": False,
            "badge_text": "Frozen Baseline Dataset — not a live scan",
            "signal_source": V40_SIGNAL_SOURCE,
            "strategy_version": V40_STRATEGY_VERSION,
        }
        return payload

    # Expanded Market Universe Signals: Read from persistent active ScreenerSnapshot
    from app.services.snapshot_service import snapshot_service
    active_snap = snapshot_service.get_active_snapshot(db)

    if active_snap:
        signals_source = active_snap.get("signals")
        if not signals_source:
            active_stocks = universe_manager.get_all(include_inactive=False)
            signals_source = [s.get("latest_signal") or scanner_service.evaluate_stock_signal(s["ticker"]) for s in active_stocks]

        signals_list = []
        for s in signals_source:
            if not s:
                continue
            signals_list.append(_enrich_signal_for_api(s, shariah_map))

        summary = active_snap.get("summary") or universe_manager.get_summary_counts()
        is_live = _snapshot_is_live_refresh(active_snap, signals_list)
        return {
            "snapshot_id": active_snap.get("snapshot_id"),
            "as_of_date": active_snap.get("market_as_of_date", "2026-10-14"),
            "last_refresh_time": active_snap.get("calculated_at"),
            "total_stocks": len(signals_list),
            "counts": summary.get("signals", {}),
            "summary": summary,
            "signals": signals_list,
            "data_provenance": {
                **DATA_PROVENANCE,
                "mode": "LIVE_SCAN" if is_live else "SNAPSHOT_OR_SEEDED",
                "badge_text": (
                    f"Live V4.0 Screener ({len(signals_list)} Monitored)"
                    if is_live
                    else f"Screener Snapshot — verify freshness ({len(signals_list)} Monitored)"
                ),
                "is_refreshed": is_live,
                "as_of_date": active_snap.get("market_as_of_date"),
                "description": (
                    "Adaptive Trading V4.0 quantitative signal engine across expanded liquid US market."
                    if is_live
                    else "Snapshot may include seeded frozen-baseline rows until a FULL/MARKET_CLOSE refresh completes."
                ),
                "signal_source": V40_SIGNAL_SOURCE,
                "strategy_version": V40_STRATEGY_VERSION,
            },
        }

    # Fallback if no snapshot created yet
    active_stocks = universe_manager.get_all(include_inactive=False)
    signals_list = []

    for s in active_stocks:
        sig = s.get("latest_signal")
        ticker = s["ticker"]
        if not sig:
            sig = scanner_service.evaluate_stock_signal(ticker)
            universe_manager.update_stock(ticker, {"latest_signal": sig})

        enriched = _enrich_signal_for_api(dict(sig), shariah_map)
        enriched["company_name"] = s.get("name", ticker)
        enriched["sector"] = s.get("sector", "Technology")
        enriched["exchange"] = s.get("exchange", "NASDAQ")
        enriched["data_status"] = s.get("data_status", "READY")
        signals_list.append(enriched)

    summary = universe_manager.get_summary_counts()
    any_fresh = any(s.get("is_fresh_analysis") for s in signals_list)

    return {
        "snapshot_id": None,
        "as_of_date": summary.get("latest_market_date", "2026-10-09"),
        "last_refresh_time": summary.get("last_refresh_time"),
        "total_stocks": len(signals_list),
        "counts": summary.get("signals", {}),
        "summary": summary,
        "signals": signals_list,
        "data_provenance": {
            **DATA_PROVENANCE,
            "mode": "LIVE_SCAN" if any_fresh else "REGISTRY_FALLBACK",
            "badge_text": f"Expanded Screener Universe ({len(signals_list)} Monitored)",
            "is_refreshed": bool(any_fresh),
            "description": "Adaptive Trading V4.0 quantitative signal engine across expanded liquid US market.",
            "signal_source": V40_SIGNAL_SOURCE,
            "strategy_version": V40_STRATEGY_VERSION,
        },
    }


