"""Market Scanner & Stock Universe API Router for Adaptive Trading V4.0.

Provides endpoints for:
1. Dynamic broad-market screener listing, filtering, and summary metrics.
2. Global stock search and 'Add to Screener' actions.
3. User-initiated manual Refresh Screener execution and status polling.
"""
from typing import Dict, List, Any, Optional
from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.universe_manager import universe_manager
from app.services.scanner_service import scanner_service
from app.services.security_master import search_symbols

router = APIRouter(prefix="/api/scanner", tags=["Market Scanner"])


class AddStockRequest(BaseModel):
    ticker: str
    name: Optional[str] = None
    exchange: Optional[str] = "NASDAQ"
    sector: Optional[str] = "Technology"


class RefreshRequest(BaseModel):
    force_all: bool = False


@router.get("/universe")
def get_universe_stocks(
    search: Optional[str] = None,
    sector: Optional[str] = None,
    signal: Optional[str] = None,
    data_status: Optional[str] = None,
    sort_by: Optional[str] = "signal",
    ascending: bool = True,
    limit: Optional[int] = Query(None, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    """Retrieve the broad market screener universe with filtering, sorting, and pagination."""
    all_stocks = universe_manager.get_all(
        include_inactive=False,
        sector=sector,
        signal=signal,
        data_status=data_status,
        search=search,
        sort_by=sort_by,
        ascending=ascending,
    )

    total_filtered = len(all_stocks)
    paginated = all_stocks[offset : offset + limit] if limit else all_stocks[offset:]

    summary = universe_manager.get_summary_counts()

    return {
        "total_filtered": total_filtered,
        "offset": offset,
        "limit": limit or total_filtered,
        "summary": summary,
        "stocks": paginated,
    }


@router.get("/summary")
def get_scanner_summary():
    """Retrieve broad-market dashboard metrics and signal breakdown."""
    return universe_manager.get_summary_counts()


@router.get("/search")
def search_stocks_for_screener(
    q: str = Query(..., min_length=1, description="Ticker, company name, or alias"),
    db: Session = Depends(get_db),
):
    """Global stock search returning both monitored and unmonitored US equities."""
    results = search_symbols(q, db=db)
    return results


@router.post("/add-stock")
def add_stock_to_screener(payload: AddStockRequest):
    """Dynamically validates, downloads historical data, calculates V4.0 indicators,
    derives optimal rules, evaluates trading signal, and persists stock to universe."""
    ticker = payload.ticker.strip().upper()
    if not ticker or len(ticker) > 10:
        raise HTTPException(status_code=400, detail="Invalid ticker symbol.")

    result = scanner_service.add_stock_to_screener(
        ticker=ticker,
        name=payload.name,
        exchange=payload.exchange,
        sector=payload.sector,
    )
    return result


@router.post("/refresh")
def trigger_screener_refresh(payload: Optional[RefreshRequest] = None):
    """Initiates a manual daily data refresh across all monitored stocks."""
    force = payload.force_all if payload else False
    result = scanner_service.start_refresh_async(force_all=force)
    return result


@router.get("/refresh-status")
def get_refresh_status():
    """Polls the live progress and status of the screener refresh operation."""
    return scanner_service.get_refresh_status()


@router.post("/cancel-refresh")
def cancel_screener_refresh():
    """Cancels an active screener refresh operation."""
    return scanner_service.cancel_refresh()
