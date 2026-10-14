"""Backtesting Router supporting asynchronous job submission, progress tracking, and Excel export."""
from pathlib import Path
import json
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import BacktestRun, WatchlistStock
from app.schemas import BacktestRequest, BacktestJobResponse
from app.jobs import enqueue_backtest
from app.config import PRICE_CACHE_DIR

router = APIRouter(prefix="/api/backtesting", tags=["Backtesting"])


@router.post("/run")
def start_backtest(req: BacktestRequest, db: Session = Depends(get_db)):
    """Trigger a backtest with custom parameters on the unchanged V4.0 baseline strategy."""
    tickers = req.tickers
    if not tickers:
        # Default to enabled stocks in watchlist
        enabled_stocks = db.query(WatchlistStock).filter(WatchlistStock.enabled == True).all()
        tickers = [s.ticker for s in enabled_stocks] if enabled_stocks else []

    if not tickers:
        # Fallback to discovering cached CSVs
        tickers = [f.stem.replace("IDX_", "^") for f in PRICE_CACHE_DIR.glob("*.csv") if f.stem != "SPY"]

    job_id = enqueue_backtest(
        start_date=req.start_date,
        end_date=req.end_date,
        capital=req.capital,
        max_positions=req.max_positions,
        train_years=req.train_years,
        fee_bps=req.fee_bps,
        min_training_buys=req.min_training_buys,
        tickers=tickers
    )

    return {
        "job_id": job_id,
        "status": "QUEUED",
        "message": f"Backtest queued for {len(tickers)} stocks ({req.start_date} to {req.end_date or 'latest'})"
    }


@router.get("/jobs/{job_id}")
def get_backtest_job_status(job_id: str, db: Session = Depends(get_db)):
    """Check progress, status, and metrics of a backtest job."""
    run = db.query(BacktestRun).filter(BacktestRun.id == job_id).first()
    if not run:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    metrics = json.loads(run.metrics_json) if run.metrics_json else {}

    return {
        "job_id": run.id,
        "status": run.status,
        "progress_pct": run.progress_pct,
        "message": run.progress_message,
        "error": run.error_message,
        "metrics": metrics,
        "has_excel_report": bool(run.excel_path and Path(run.excel_path).exists()),
        "created_at": str(run.created_at),
        "completed_at": str(run.completed_at) if run.completed_at else None
    }


@router.get("/jobs/{job_id}/download")
def download_backtest_excel(job_id: str, db: Session = Depends(get_db)):
    """Download the generated Excel report for a completed backtest job."""
    run = db.query(BacktestRun).filter(BacktestRun.id == job_id).first()
    if not run or not run.excel_path or not Path(run.excel_path).exists():
        raise HTTPException(status_code=404, detail="Excel report not ready or job not found")

    return FileResponse(
        path=run.excel_path,
        filename=f"Adaptive_Trading_Backtest_{job_id[:8]}.xlsx",
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


@router.get("/runs")
def list_backtest_runs(db: Session = Depends(get_db)):
    """List recent backtest runs."""
    runs = db.query(BacktestRun).order_by(BacktestRun.created_at.desc()).limit(20).all()
    results = []
    for r in runs:
        metrics = json.loads(r.metrics_json) if r.metrics_json else {}
        results.append({
            "id": r.id,
            "status": r.status,
            "start_date": r.start_date,
            "end_date": r.end_date,
            "capital": r.capital,
            "max_positions": r.max_positions,
            "cagr_pct": metrics.get("portfolio_cagr_pct"),
            "total_return_pct": metrics.get("portfolio_total_return_pct"),
            "max_dd_pct": metrics.get("portfolio_max_drawdown_pct"),
            "completed_trades": metrics.get("completed_trades"),
            "created_at": str(r.created_at)
        })
    return results
