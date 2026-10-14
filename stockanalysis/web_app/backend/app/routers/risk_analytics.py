"""Risk Analytics Router."""
from fastapi import APIRouter
from app.engine_bridge import bridge

router = APIRouter(prefix="/api/risk", tags=["Risk Analytics"])


@router.get("")
def get_risk_metrics():
    """Retrieve portfolio risk profile, underwater drawdown, worst trades, volatility, and capture ratios."""
    return bridge.get_risk_analytics()
