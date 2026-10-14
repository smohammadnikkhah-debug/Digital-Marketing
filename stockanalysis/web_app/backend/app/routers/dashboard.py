"""Dashboard Router."""
from fastapi import APIRouter
from app.engine_bridge import bridge

router = APIRouter(prefix="/api/dashboard", tags=["Dashboard"])


@router.get("")
def get_dashboard_data():
    """Retrieve full dashboard overview data."""
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
