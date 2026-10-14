"""Simulated Portfolio Router."""
from fastapi import APIRouter
from app.engine_bridge import bridge

router = APIRouter(prefix="/api/portfolio", tags=["Simulated Portfolio"])


@router.get("")
def get_portfolio_overview():
    """Retrieve simulated cash-only portfolio holdings, cash, and completed trades."""
    holdings_and_trades = bridge.get_portfolio_holdings_and_trades()
    dashboard = bridge.get_baseline_dashboard()
    equity_curve = bridge.get_portfolio_equity_curve()

    return {
        "disclaimer": "SIMULATED RESEARCH PORTFOLIO ONLY. Does not place orders or represent live brokerage holdings.",
        "starting_capital": dashboard.get("initial_capital", 100000.0),
        "current_equity": dashboard.get("portfolio_ending_value", 0.0),
        "available_cash": dashboard.get("available_cash", 0.0),
        "simulated_exposure": dashboard.get("simulated_exposure", 0.0),
        "max_positions": 5,
        "cash_only": True,
        "margin_allowed": False,
        "current_holdings": holdings_and_trades["current_holdings"],
        "completed_trades": holdings_and_trades["completed_trades"],
        "trade_stats": holdings_and_trades.get("trade_stats", {}),
        "recent_equity": equity_curve[-60:] if len(equity_curve) > 60 else equity_curve,
    }

