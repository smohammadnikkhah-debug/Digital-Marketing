"""Tests for User Portfolio Management, FIFO Cost Basis, TWR, SPY Rebasing, and Isolation."""
import pytest
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import User, Portfolio, PortfolioTransaction, PortfolioLot
from app.services.user_portfolio import (
    get_or_create_portfolio,
    add_transaction,
    update_transaction,
    delete_transaction,
    recalculate_portfolio,
    calculate_dashboard_data,
    seed_sample_portfolio,
    reset_portfolio,
)


@pytest.fixture
def db_session():
    """Create in-memory SQLite database session for testing."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    # Seed test users
    user_a = User(username="user_a", email="a@test.local", hashed_password="pw1", role="user")
    user_b = User(username="user_b", email="b@test.local", hashed_password="pw2", role="user")
    session.add_all([user_a, user_b])
    session.commit()

    yield session
    session.close()


def test_get_or_create_portfolio_user_scoping(db_session):
    """Test user isolation: user A and user B get separate portfolios."""
    user_a = db_session.query(User).filter(User.username == "user_a").first()
    user_b = db_session.query(User).filter(User.username == "user_b").first()

    port_a = get_or_create_portfolio(db_session, user_id=user_a.id)
    port_b = get_or_create_portfolio(db_session, user_id=user_b.id)

    assert port_a.id != port_b.id
    assert port_a.user_id == user_a.id
    assert port_b.user_id == user_b.id


def test_fifo_multiple_lots_and_cost_basis(db_session):
    """Test multi-lot FIFO cost basis tracking and partial sale realized P/L."""
    user_a = db_session.query(User).filter(User.username == "user_a").first()
    port = get_or_create_portfolio(db_session, user_id=user_a.id)

    # 1. Deposit $50,000 cash
    add_transaction(
        db=db_session,
        portfolio_id=port.id,
        ticker="CASH",
        exchange="CASH",
        transaction_type="DEPOSIT",
        quantity=0.0,
        price_per_share=50000.0,
        fee=0.0,
        trade_date="2024-01-10",
    )

    # 2. Lot 1: Buy 100 shares of NVDA @ $50.00 (fee $5.00) -> Cost basis per share = 50.05
    tx_buy1 = add_transaction(
        db=db_session,
        portfolio_id=port.id,
        ticker="NVDA",
        exchange="NASDAQ",
        transaction_type="BUY",
        quantity=100.0,
        price_per_share=50.0,
        fee=5.0,
        trade_date="2024-02-01",
    )

    # 3. Lot 2: Buy 50 shares of NVDA @ $80.00 (fee $5.00) -> Cost basis per share = 80.10
    tx_buy2 = add_transaction(
        db=db_session,
        portfolio_id=port.id,
        ticker="NVDA",
        exchange="NASDAQ",
        transaction_type="BUY",
        quantity=50.0,
        price_per_share=80.0,
        fee=5.0,
        trade_date="2024-03-01",
    )

    summary = recalculate_portfolio(db_session, port.id)
    holding = next(h for h in summary["holdings"] if h["ticker"] == "NVDA")
    assert holding["shares"] == 150.0
    assert len(holding["lots"]) == 2
    assert holding["lots"][0]["remaining_shares"] == 100.0
    assert holding["lots"][1]["remaining_shares"] == 50.0

    # 4. Partial sale: Sell 60 shares of NVDA @ $120.00 (fee $5.00)
    # Under FIFO, all 60 shares must be deducted from Lot 1 (cost $50.05).
    # Expected gross proceeds = 60 * 120 = 7,200.
    # Expected cost = 60 * 50.05 = 3,003.
    # Realized P/L = 7,200 - 3,003 - 5.00 fee = 4,192.
    add_transaction(
        db=db_session,
        portfolio_id=port.id,
        ticker="NVDA",
        exchange="NASDAQ",
        transaction_type="SELL",
        quantity=60.0,
        price_per_share=120.0,
        fee=5.0,
        trade_date="2024-04-01",
    )

    summary_after_sale = recalculate_portfolio(db_session, port.id)
    holding_after = next(h for h in summary_after_sale["holdings"] if h["ticker"] == "NVDA")
    assert holding_after["shares"] == 90.0
    assert len(holding_after["lots"]) == 2
    assert holding_after["lots"][0]["remaining_shares"] == 40.0  # 100 - 60 = 40 left in Lot 1
    assert holding_after["lots"][1]["remaining_shares"] == 50.0  # Lot 2 untouched
    assert summary_after_sale["total_realized_pnl"] == pytest.approx(4192.0, abs=1.0)


def test_cannot_sell_more_shares_than_owned(db_session):
    """Test validation preventing short selling or selling unowned shares."""
    user_a = db_session.query(User).filter(User.username == "user_a").first()
    port = get_or_create_portfolio(db_session, user_id=user_a.id)

    add_transaction(
        db=db_session,
        portfolio_id=port.id,
        ticker="CASH",
        exchange="CASH",
        transaction_type="DEPOSIT",
        quantity=0.0,
        price_per_share=10000.0,
        fee=0.0,
        trade_date="2024-01-10",
    )
    add_transaction(
        db=db_session,
        portfolio_id=port.id,
        ticker="AAPL",
        exchange="NASDAQ",
        transaction_type="BUY",
        quantity=10.0,
        price_per_share=150.0,
        fee=0.0,
        trade_date="2024-02-01",
    )

    # Attempt to sell 20 shares when only 10 are owned
    with pytest.raises(ValueError, match="Insufficient shares to sell"):
        add_transaction(
            db=db_session,
            portfolio_id=port.id,
            ticker="AAPL",
            exchange="NASDAQ",
            transaction_type="SELL",
            quantity=20.0,
            price_per_share=160.0,
            fee=0.0,
            trade_date="2024-03-01",
        )


def test_stock_split_corporate_action(db_session):
    """Test SPLIT corporate action adjusts shares and cost basis proportionally."""
    user_a = db_session.query(User).filter(User.username == "user_a").first()
    port = get_or_create_portfolio(db_session, user_id=user_a.id)

    add_transaction(
        db=db_session,
        portfolio_id=port.id,
        ticker="CASH",
        exchange="CASH",
        transaction_type="DEPOSIT",
        quantity=0.0,
        price_per_share=20000.0,
        fee=0.0,
        trade_date="2024-01-01",
    )
    # Buy 10 shares @ $100
    add_transaction(
        db=db_session,
        portfolio_id=port.id,
        ticker="TSLA",
        exchange="NASDAQ",
        transaction_type="BUY",
        quantity=10.0,
        price_per_share=100.0,
        fee=0.0,
        trade_date="2024-02-01",
    )

    # Execute 3:1 forward split
    add_transaction(
        db=db_session,
        portfolio_id=port.id,
        ticker="TSLA",
        exchange="NASDAQ",
        transaction_type="SPLIT",
        quantity=3.0,
        price_per_share=0.0,
        fee=0.0,
        trade_date="2024-03-01",
    )

    summary = recalculate_portfolio(db_session, port.id)
    tsla_holding = next(h for h in summary["holdings"] if h["ticker"] == "TSLA")
    assert tsla_holding["shares"] == pytest.approx(30.0, abs=0.01)
    assert tsla_holding["average_cost_basis"] == pytest.approx(33.33, abs=0.1)


def test_twr_external_cash_flows_do_not_fabricate_returns(db_session):
    """Test that pure cash deposits/withdrawals do not distort Time-Weighted Return (TWR)."""
    user_a = db_session.query(User).filter(User.username == "user_a").first()
    port = get_or_create_portfolio(db_session, user_id=user_a.id)

    # Initial deposit of $100,000 on 2024-01-08
    add_transaction(
        db=db_session,
        portfolio_id=port.id,
        ticker="CASH",
        exchange="CASH",
        transaction_type="DEPOSIT",
        quantity=0.0,
        price_per_share=100000.0,
        fee=0.0,
        trade_date="2024-01-08",
    )

    # Second massive deposit of $500,000 on 2024-01-15
    add_transaction(
        db=db_session,
        portfolio_id=port.id,
        ticker="CASH",
        exchange="CASH",
        transaction_type="DEPOSIT",
        quantity=0.0,
        price_per_share=500000.0,
        fee=0.0,
        trade_date="2024-01-15",
    )

    dash = calculate_dashboard_data(db_session, port.id, period="all")
    # Because all capital was held in pure cash without stock price changes,
    # period return % must be exactly 0.0% despite total equity jumping 6x!
    assert dash["summary_cards"]["period_return_pct"] == 0.0
    assert dash["summary_cards"]["period_pnl"] == 0.0
    assert dash["summary_cards"]["total_equity"] == 600000.0


def test_seed_sample_portfolio_and_scorecard(db_session):
    """Test realistic sample portfolio seeding, annual scorecard, and period switching."""
    user_a = db_session.query(User).filter(User.username == "user_a").first()
    port = get_or_create_portfolio(db_session, user_id=user_a.id)

    seed_sample_portfolio(db_session, port.id)

    # Check YTD dashboard
    dash_ytd = calculate_dashboard_data(db_session, port.id, period="ytd")
    assert not dash_ytd["is_empty"]
    assert dash_ytd["summary_cards"]["total_equity"] > 100000.0
    assert len(dash_ytd["performance_chart"]) > 0
    # Rebasing invariant: first chart point must be rebased to 0%
    assert dash_ytd["performance_chart"][0]["portfolio_return_pct"] == 0.0
    assert dash_ytd["performance_chart"][0]["spy_return_pct"] == 0.0
    assert dash_ytd["performance_chart"][0]["excess_pp"] == 0.0

    # Check annual scorecard rows
    assert len(dash_ytd["annual_scorecard"]) >= 1
    for row in dash_ytd["annual_scorecard"]:
        assert "year" in row
        assert "portfolio_return_pct" in row
        assert "spy_return_pct" in row
        assert "excess_pp" in row
        assert "year_end_equity" in row

    # Check Day period
    dash_day = calculate_dashboard_data(db_session, port.id, period="day")
    assert len(dash_day["performance_chart"]) <= 2
    assert dash_day["performance_chart"][0]["portfolio_return_pct"] == 0.0

    # Check Reset to empty
    reset_portfolio(db_session, port.id)
    dash_empty = calculate_dashboard_data(db_session, port.id, period="ytd")
    assert dash_empty["is_empty"]
    assert dash_empty["summary_cards"]["total_equity"] == 0.0
    assert len(dash_empty["performance_chart"]) == 0
