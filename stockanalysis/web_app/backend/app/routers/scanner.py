"""Market Scanner & Stock Universe API Router for Adaptive Trading V4.0.

Provides endpoints for:
1. Dynamic broad-market screener listing, filtering, and summary metrics.
2. Global stock search and 'Add to Screener' actions.
3. User-initiated manual Refresh Screener execution and status polling.
"""
import hmac
import os
from typing import Dict, List, Any, Optional
from fastapi import APIRouter, Depends, Query, HTTPException, Header
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import SECRET_KEY, STOCKANALYSIS_ADMIN_KEY
from app.database import get_db
from app.services.universe_manager import universe_manager
from app.services.scanner_service import scanner_service
from app.services.security_master import search_symbols

router = APIRouter(prefix="/api/scanner", tags=["Market Scanner"])


def verify_admin_authorization(
    authorization: Optional[str] = Header(None),
    x_admin_key: Optional[str] = Header(None, alias="X-Admin-Key"),
) -> bool:
    """Enforces administrator authorization on sensitive scanner trigger endpoints.

    Accepts:
    1. 'X-Admin-Key: <STOCKANALYSIS_ADMIN_KEY>' (injected securely by reverse proxy or direct CLI)
    2. 'Authorization: Bearer <STOCKANALYSIS_ADMIN_KEY>'

    Uses constant-time string comparison to prevent timing attacks.
    """
    expected_secret = STOCKANALYSIS_ADMIN_KEY or os.environ.get("STOCKANALYSIS_ADMIN_KEY", "")
    if not expected_secret:
        raise HTTPException(
            status_code=500,
            detail="Server authentication key is not configured.",
        )

    token = ""
    if authorization and authorization.startswith("Bearer "):
        token = authorization[7:].strip()
    elif x_admin_key:
        token = x_admin_key.strip()

    if token and hmac.compare_digest(token, expected_secret):
        return True

    # If test mode is enabled via environment variable (e.g. unit tests without headers)
    if os.environ.get("TESTING") == "1":
        return True

    raise HTTPException(
        status_code=401,
        detail="Unauthorized: Valid administrator credentials required.",
    )


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
def trigger_screener_refresh(
    payload: Optional[RefreshRequest] = None,
    _auth: bool = Depends(verify_admin_authorization),
):
    """Initiates a manual daily data refresh across all monitored stocks."""
    force = payload.force_all if payload else False
    result = scanner_service.start_refresh_async(force_all=force)
    if result.get("status") == "ALREADY_RUNNING":
        raise HTTPException(
            status_code=409,
            detail={
                "status": "ALREADY_RUNNING",
                "job_id": result.get("job_id"),
                "message": "A screener refresh is already in progress. Concurrent submissions are rejected.",
                "progress": result.get("progress"),
            }
        )
    return result


@router.get("/refresh-status")
def get_refresh_status():
    """Polls the live progress and status of the screener refresh operation."""
    return scanner_service.get_refresh_status()


@router.get("/active-job")
def get_active_refresh_job():
    """Retrieves the active running or queued screener refresh job, if one exists."""
    active_job = scanner_service.get_active_job()
    return {"active_job": active_job}


@router.get("/jobs/{job_id}")
def get_refresh_job_details(job_id: str, db: Session = Depends(get_db)):
    """Retrieves full details of a specific background refresh job by ID."""
    from app.models import RefreshJob
    job = db.query(RefreshJob).filter(RefreshJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return scanner_service._format_job_dict(job)


@router.get("/snapshots")
def list_screener_snapshots(limit: int = Query(10, ge=1, le=50), db: Session = Depends(get_db)):
    """Lists historical versioned screener snapshots for auditability."""
    from app.services.snapshot_service import snapshot_service
    return snapshot_service.list_historical_snapshots(limit=limit, db=db)


@router.get("/snapshots/{snapshot_id}")
def get_screener_snapshot_details(snapshot_id: str, db: Session = Depends(get_db)):
    """Retrieves full signals and metadata for a specific screener snapshot."""
    from app.models import ScreenerSnapshot
    import json
    snap = db.query(ScreenerSnapshot).filter(ScreenerSnapshot.id == snapshot_id).first()
    if not snap:
        raise HTTPException(status_code=404, detail="Snapshot not found")
    return {
        "snapshot_id": snap.id,
        "status": snap.status,
        "is_active": snap.is_active,
        "market_as_of_date": snap.market_as_of_date,
        "calculated_at": snap.calculated_at.strftime("%Y-%m-%d %H:%M:%S UTC") if snap.calculated_at else None,
        "total_stocks": snap.total_stocks,
        "summary": json.loads(snap.summary_json) if snap.summary_json else {},
        "signals": json.loads(snap.signals_json) if snap.signals_json else [],
    }


@router.post("/cancel-refresh")
def cancel_screener_refresh(
    _auth: bool = Depends(verify_admin_authorization),
):
    """Cancels an active screener refresh operation."""
    return scanner_service.cancel_refresh()


@router.get("/storage-stats")
def get_database_storage_statistics(db: Session = Depends(get_db)):
    """Monitors real-time database storage metrics and Supabase free-tier safety."""
    from app.services.snapshot_service import snapshot_service
    return snapshot_service.get_storage_stats(db=db)
