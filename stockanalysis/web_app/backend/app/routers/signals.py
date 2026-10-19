from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.engine_bridge import bridge
from app.database import get_db
from app.models import WatchlistStock
from app.services.universe_manager import universe_manager
from app.services.scanner_service import scanner_service
from app.config import DATA_PROVENANCE

router = APIRouter(prefix="/api/signals", tags=["Signals"])


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
        return bridge.get_today_signals(custom_shariah=shariah_map)

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
            sig = dict(s)
            ticker = sig.get("ticker", "")
            if ticker in shariah_map:
                sig["shariah_status"] = shariah_map[ticker]["status"]
            stock_info = universe_manager.get_stock(ticker) or {}
            stock_name = stock_info.get("name", sig.get("name", ticker))
            sig["name"] = sig.get("name") or stock_name
            sig["company_name"] = stock_name
            sig["sector"] = stock_info.get("sector", sig.get("sector", "Technology"))
            sig["exchange"] = stock_info.get("exchange", sig.get("exchange", "NASDAQ"))
            sig["data_status"] = stock_info.get("data_status", sig.get("data_status", "READY"))
            signals_list.append(sig)

        summary = active_snap.get("summary") or universe_manager.get_summary_counts()
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
                "badge_text": f"Expanded Screener Universe ({len(signals_list)} Monitored)",
                "is_refreshed": True,
                "as_of_date": active_snap.get("market_as_of_date"),
                "description": "Adaptive Trading V4.0 quantitative signal engine across expanded liquid US market.",
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

        # Attach custom Shariah if present
        if ticker in shariah_map:
            sig["shariah_status"] = shariah_map[ticker]["status"]
        
        # Attach sector & company name from universe registry
        sig["company_name"] = s.get("name", ticker)
        sig["sector"] = s.get("sector", "Technology")
        sig["exchange"] = s.get("exchange", "NASDAQ")
        sig["data_status"] = s.get("data_status", "READY")
        signals_list.append(sig)

    summary = universe_manager.get_summary_counts()

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
            "badge_text": f"Expanded Screener Universe ({len(signals_list)} Monitored)",
            "is_refreshed": True,
            "description": "Adaptive Trading V4.0 quantitative signal engine across expanded liquid US market.",
        },
    }


