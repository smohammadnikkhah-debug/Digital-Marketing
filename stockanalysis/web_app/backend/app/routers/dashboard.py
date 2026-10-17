"""Dashboard Router supporting both Real Portfolio Overview and Audited V4.0 Strategy Baseline."""
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.auth import get_current_user_or_default
from app.engine_bridge import bridge
from app.services.user_portfolio import get_or_create_portfolio, calculate_dashboard_data

router = APIRouter(prefix="/api/dashboard", tags=["Dashboard"])


@router.get("/strategy")
def get_strategy_dashboard_data():
    """Retrieve audited V4.0 strategy baseline dashboard overview data."""
    metrics = bridge.get_baseline_dashboard()
    annual = bridge.get_annual_performance()
    equity = bridge.get_portfolio_equity_curve(downsample=1)
    signals = bridge.get_today_signals()

    return {
        "metrics": metrics,
        "annual_performance": annual,
        "equity_curve": equity,
        "signal_counts": signals["counts"],
        "latest_date": signals["as_of_date"],
    }


@router.get("")
def get_dashboard_data(
    mode: Optional[str] = Query(None, description="Set to 'strategy' for V4.0 baseline, or omit for real portfolio"),
    period: str = Query("ytd", description="Day, MTD, YTD, 1Y, All Time"),
    current_user: Optional[User] = Depends(get_current_user_or_default),
    db: Session = Depends(get_db),
):
    """Retrieve dashboard data. Defaults to personal investment portfolio overview."""
    if mode == "strategy":
        return get_strategy_dashboard_data()

    user_id = current_user.id if current_user else None
    portfolio = get_or_create_portfolio(db, user_id=user_id)
    return calculate_dashboard_data(db, portfolio.id, period=period)
