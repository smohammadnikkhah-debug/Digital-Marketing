"""Portfolio Router supporting Real User Portfolio and Simulated Research Portfolio."""
from typing import Optional, List
from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User, PortfolioTransaction
from app.auth import get_current_user_or_default
from app.engine_bridge import bridge
from app.services.user_portfolio import (
    get_or_create_portfolio,
    calculate_dashboard_data,
    recalculate_portfolio,
    add_transaction,
    update_transaction,
    delete_transaction,
    seed_sample_portfolio,
    reset_portfolio,
)

router = APIRouter(prefix="/api/portfolio", tags=["Portfolio"])


class TransactionCreate(BaseModel):
    ticker: str
    exchange: Optional[str] = "NASDAQ"
    transaction_type: str = Field(..., description="BUY, SELL, DEPOSIT, WITHDRAWAL, DIVIDEND, SPLIT")
    quantity: float = 0.0
    price_per_share: float = 0.0
    fee: float = 0.0
    trade_date: str
    notes: Optional[str] = ""
    currency: Optional[str] = "USD"


class TransactionUpdate(BaseModel):
    ticker: Optional[str] = None
    exchange: Optional[str] = None
    transaction_type: Optional[str] = None
    quantity: Optional[float] = None
    price_per_share: Optional[float] = None
    fee: Optional[float] = None
    trade_date: Optional[str] = None
    notes: Optional[str] = None
    currency: Optional[str] = None


@router.get("/dashboard")
def get_user_portfolio_dashboard(
    period: str = Query("ytd", description="Day, MTD, YTD, 1Y, All Time"),
    current_user: Optional[User] = Depends(get_current_user_or_default),
    db: Session = Depends(get_db),
):
    """Retrieve full personal investment portfolio dashboard metrics, rebased chart, and scorecard."""
    user_id = current_user.id if current_user else None
    portfolio = get_or_create_portfolio(db, user_id=user_id)
    return calculate_dashboard_data(db, portfolio.id, period=period)


@router.get("/holdings")
def get_user_portfolio_holdings(
    current_user: Optional[User] = Depends(get_current_user_or_default),
    db: Session = Depends(get_db),
):
    """Retrieve active user holdings and multi-lot breakdown."""
    user_id = current_user.id if current_user else None
    portfolio = get_or_create_portfolio(db, user_id=user_id)
    return recalculate_portfolio(db, portfolio.id)


@router.get("/transactions")
def list_user_transactions(
    current_user: Optional[User] = Depends(get_current_user_or_default),
    db: Session = Depends(get_db),
):
    """Retrieve user portfolio transaction history."""
    user_id = current_user.id if current_user else None
    portfolio = get_or_create_portfolio(db, user_id=user_id)
    txs = (
        db.query(PortfolioTransaction)
        .filter(PortfolioTransaction.portfolio_id == portfolio.id)
        .order_by(PortfolioTransaction.trade_date.desc(), PortfolioTransaction.id.desc())
        .all()
    )
    return [
        {
            "id": tx.id,
            "portfolio_id": tx.portfolio_id,
            "ticker": tx.ticker,
            "exchange": tx.exchange,
            "transaction_type": tx.transaction_type,
            "quantity": tx.quantity,
            "price_per_share": tx.price_per_share,
            "fee": tx.fee,
            "amount": tx.amount,
            "currency": tx.currency,
            "trade_date": tx.trade_date,
            "notes": tx.notes,
            "created_at": tx.created_at.isoformat() if tx.created_at else None,
        }
        for tx in txs
    ]


@router.post("/transactions")
def create_transaction(
    payload: TransactionCreate,
    current_user: Optional[User] = Depends(get_current_user_or_default),
    db: Session = Depends(get_db),
):
    """Record a new transaction with validation against over-selling and invalid inputs."""
    user_id = current_user.id if current_user else None
    portfolio = get_or_create_portfolio(db, user_id=user_id)
    try:
        tx = add_transaction(
            db=db,
            portfolio_id=portfolio.id,
            ticker=payload.ticker,
            exchange=payload.exchange or "NASDAQ",
            transaction_type=payload.transaction_type,
            quantity=payload.quantity,
            price_per_share=payload.price_per_share,
            fee=payload.fee,
            trade_date=payload.trade_date,
            notes=payload.notes or "",
            currency=payload.currency or "USD",
        )
        return {
            "success": True,
            "transaction_id": tx.id,
            "message": f"Successfully recorded {tx.transaction_type} of {tx.ticker}",
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/transactions/{transaction_id}")
def edit_transaction(
    transaction_id: int,
    payload: TransactionUpdate,
    current_user: Optional[User] = Depends(get_current_user_or_default),
    db: Session = Depends(get_db),
):
    """Update an existing transaction and recalculate lots and cash."""
    user_id = current_user.id if current_user else None
    portfolio = get_or_create_portfolio(db, user_id=user_id)
    tx = db.query(PortfolioTransaction).filter(PortfolioTransaction.id == transaction_id).first()
    if not tx or tx.portfolio_id != portfolio.id:
        raise HTTPException(status_code=404, detail="Transaction not found or access denied")
    try:
        updates = {k: v for k, v in payload.dict().items() if v is not None}
        updated_tx = update_transaction(db, transaction_id, **updates)
        return {"success": True, "transaction_id": updated_tx.id, "message": "Transaction updated successfully"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/transactions/{transaction_id}")
def remove_transaction(
    transaction_id: int,
    current_user: Optional[User] = Depends(get_current_user_or_default),
    db: Session = Depends(get_db),
):
    """Delete a transaction and recalculate portfolio state."""
    user_id = current_user.id if current_user else None
    portfolio = get_or_create_portfolio(db, user_id=user_id)
    tx = db.query(PortfolioTransaction).filter(PortfolioTransaction.id == transaction_id).first()
    if not tx or tx.portfolio_id != portfolio.id:
        raise HTTPException(status_code=404, detail="Transaction not found or access denied")
    delete_transaction(db, transaction_id)
    return {"success": True, "message": "Transaction deleted successfully"}


@router.post("/seed-sample")
def seed_sample(
    current_user: Optional[User] = Depends(get_current_user_or_default),
    db: Session = Depends(get_db),
):
    """Seed sample realistic multi-lot investment portfolio."""
    user_id = current_user.id if current_user else None
    portfolio = get_or_create_portfolio(db, user_id=user_id)
    res = seed_sample_portfolio(db, portfolio.id)
    return {"success": True, "message": "Sample portfolio seeded successfully", "summary": res}


@router.post("/reset")
def reset_user_portfolio(
    current_user: Optional[User] = Depends(get_current_user_or_default),
    db: Session = Depends(get_db),
):
    """Reset portfolio to an empty state."""
    user_id = current_user.id if current_user else None
    portfolio = get_or_create_portfolio(db, user_id=user_id)
    res = reset_portfolio(db, portfolio.id)
    return {"success": True, "message": "Portfolio reset to empty state", "summary": res}


@router.get("/simulated")
def get_simulated_portfolio():
    """Retrieve simulated cash-only portfolio holdings, cash, and completed trades (Audited V4.0 Engine)."""
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


@router.get("")
def get_portfolio_overview():
    """Default portfolio route preserving backward compatibility for simulated portfolio."""
    return get_simulated_portfolio()
