import re
from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, Float, DateTime, Text, CheckConstraint
from sqlalchemy.orm import validates
from app.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    email = Column(String(100), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True)
    role = Column(String(20), default="researcher")
    created_at = Column(DateTime, default=datetime.utcnow)


class WatchlistStock(Base):
    __tablename__ = "watchlist_stocks"

    ticker = Column(String(20), primary_key=True, index=True)
    name = Column(String(100), default="")
    enabled = Column(Boolean, default=True)
    shariah_status = Column(String(30), default="NOT VERIFIED")  # VERIFIED, NOT VERIFIED, NON-COMPLIANT
    shariah_source = Column(String(255), default="")
    shariah_date = Column(String(50), default="")
    sector = Column(String(100), default="")
    notes = Column(Text, default="")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class BacktestRun(Base):
    __tablename__ = "backtest_runs"

    id = Column(String(50), primary_key=True, index=True)
    status = Column(String(20), default="QUEUED")  # QUEUED, RUNNING, COMPLETED, FAILED
    start_date = Column(String(20), nullable=False)
    end_date = Column(String(20), nullable=False)
    capital = Column(Float, default=100000.0)
    max_positions = Column(Integer, default=5)
    train_years = Column(Integer, default=5)
    fee_bps = Column(Float, default=10.0)
    min_training_buys = Column(Integer, default=2)
    tickers_json = Column(Text, default="[]")
    metrics_json = Column(Text, default="{}")
    results_json = Column(Text, default="{}")
    excel_path = Column(String(255), default="")
    error_message = Column(Text, default="")
    progress_pct = Column(Integer, default=0)
    progress_message = Column(String(255), default="")
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)


class SystemSetting(Base):
    __tablename__ = "system_settings"

    key = Column(String(50), primary_key=True)
    value = Column(Text, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Portfolio(Base):
    __tablename__ = "portfolios"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=True, index=True)  # Scoped to authenticated User.id (or None for default demo)
    name = Column(String(100), default="Primary Portfolio")
    base_currency = Column(String(10), default="USD")
    cash_balance = Column(Float, default=0.0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class PortfolioTransaction(Base):
    __tablename__ = "portfolio_transactions"

    id = Column(Integer, primary_key=True, index=True)
    portfolio_id = Column(Integer, nullable=False, index=True)
    ticker = Column(String(20), nullable=False, index=True)
    exchange = Column(String(30), default="NASDAQ")
    transaction_type = Column(String(20), nullable=False)  # BUY, SELL, DEPOSIT, WITHDRAWAL, DIVIDEND
    quantity = Column(Float, default=0.0)
    price_per_share = Column(Float, default=0.0)
    fee = Column(Float, default=0.0)
    amount = Column(Float, default=0.0)  # Total cash impact
    currency = Column(String(10), default="USD")
    trade_date = Column(String(20), nullable=False, index=True)  # YYYY-MM-DD
    notes = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)


class PortfolioLot(Base):
    __tablename__ = "portfolio_lots"

    id = Column(Integer, primary_key=True, index=True)
    portfolio_id = Column(Integer, nullable=False, index=True)
    buy_transaction_id = Column(Integer, nullable=False, index=True)
    ticker = Column(String(20), nullable=False, index=True)
    exchange = Column(String(30), default="NASDAQ")
    initial_quantity = Column(Float, nullable=False)
    remaining_quantity = Column(Float, nullable=False)
    cost_per_share = Column(Float, nullable=False)
    fee_allocated = Column(Float, default=0.0)
    purchase_date = Column(String(20), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class MonitoredStock(Base):
    __tablename__ = "monitored_stocks"

    ticker = Column(String(20), primary_key=True, index=True)
    name = Column(String(150), default="")
    exchange = Column(String(30), default="NASDAQ")
    sector = Column(String(100), default="Technology")
    industry = Column(String(100), default="Equity")
    is_active = Column(Boolean, default=True)
    is_benchmark = Column(Boolean, default=False)
    inclusion_date = Column(String(20), default="2026-10-09")
    source = Column(String(50), default="v40_baseline")
    data_status = Column(String(30), default="READY")  # READY, STALE, INSUFFICIENT_DATA, PENDING
    latest_price_date = Column(String(20), nullable=True)
    v40_eligible = Column(Boolean, default=True)
    optimal_rule_json = Column(Text, nullable=True)  # JSON {entry, exit}
    latest_signal_json = Column(Text, nullable=True)  # Full evaluated signal JSON
    last_scanned_at = Column(String(50), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ScreenerSnapshot(Base):
    __tablename__ = "screener_snapshots"

    id = Column(String(50), primary_key=True, index=True)
    status = Column(String(20), default="COMPLETED")  # COMPLETED, FAILED, STAGING
    is_active = Column(Boolean, default=False, index=True)
    market_as_of_date = Column(String(20), nullable=False)
    calculated_at = Column(DateTime, default=datetime.utcnow)
    saved_at = Column(DateTime, default=datetime.utcnow)
    data_provider = Column(String(100), default="Yahoo Finance (Auto-Adjusted OHLCV)")
    strategy_version = Column(String(100), default="Adaptive Trading V4.0 Baseline")
    refresh_job_id = Column(String(50), nullable=True, index=True)
    total_stocks = Column(Integer, default=0)
    refreshed_count = Column(Integer, default=0)
    stale_count = Column(Integer, default=0)
    insufficient_count = Column(Integer, default=0)
    buy_candidates_count = Column(Integer, default=0)
    summary_json = Column(Text, default="{}")
    signals_json = Column(Text, default="[]")
    created_at = Column(DateTime, default=datetime.utcnow)


class RefreshJob(Base):
    __tablename__ = "refresh_jobs"

    id = Column(String(50), primary_key=True, index=True)
    job_type = Column(String(30), default="MANUAL_REFRESH")  # MANUAL_REFRESH, MARKET_OPEN, MARKET_CLOSE
    status = Column(String(20), default="QUEUED", index=True)  # QUEUED, RUNNING, COMPLETED, FAILED, CANCELLED
    force_all = Column(Boolean, default=False)
    total_stocks = Column(Integer, default=0)
    completed_stocks = Column(Integer, default=0)
    remaining_stocks = Column(Integer, default=0)
    failed_stocks = Column(Integer, default=0)
    stale_stocks = Column(Integer, default=0)
    current_ticker = Column(String(20), nullable=True)
    start_time = Column(DateTime, nullable=True)
    finish_time = Column(DateTime, nullable=True)
    message = Column(String(255), default="Job queued")
    error_message = Column(Text, nullable=True)
    errors_json = Column(Text, default="[]")
    snapshot_id = Column(String(50), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class DailyBar(Base):
    __tablename__ = "daily_bars"

    ticker = Column(String(20), primary_key=True, index=True)
    bar_date = Column(String(20), primary_key=True, index=True)  # YYYY-MM-DD
    open = Column(Float, nullable=False)
    high = Column(Float, nullable=False)
    low = Column(Float, nullable=False)
    close = Column(Float, nullable=False)
    volume = Column(Float, default=0.0)
    created_at = Column(DateTime, default=datetime.utcnow)


# ==============================================================================
# STAGE D2.2: TRANSACTIONAL PAPER ORDER MANAGEMENT MODELS
# ==============================================================================

class PaperOrder(Base):
    __tablename__ = "paper_orders"

    order_id = Column(String(50), primary_key=True, index=True)
    client_order_id = Column(String(100), unique=True, index=True, nullable=False)
    broker = Column(String(20), default="ibkr", nullable=False, index=True)
    account_id = Column(String(30), nullable=False, index=True)
    symbol = Column(String(20), nullable=False, index=True)
    action = Column(String(10), nullable=False)  # BUY, SELL
    order_type = Column(String(20), default="LIMIT", nullable=False)
    quantity = Column(Float, nullable=False)
    limit_price = Column(Float, nullable=False)
    currency = Column(String(10), default="USD", nullable=False)
    estimated_notional = Column(Float, nullable=False)
    filled_quantity = Column(Float, default=0.0, nullable=False)
    avg_fill_price = Column(Float, nullable=True)
    status = Column(String(30), default="DRAFT", index=True, nullable=False)
    version = Column(Integer, default=1, nullable=False)
    proposed_by = Column(String(50), default="ADMIN", nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    approved_by = Column(String(50), nullable=True)
    approved_at = Column(DateTime, nullable=True)
    approval_expires_at = Column(DateTime, nullable=True, index=True)
    claimed_by_agent = Column(String(50), nullable=True, index=True)
    claimed_at = Column(DateTime, nullable=True)
    submitted_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    requires_manual_reconciliation = Column(Boolean, default=False, index=True, nullable=False)
    can_auto_resubmit = Column(Boolean, default=False, nullable=False)
    notes = Column(Text, nullable=True)
    risk_check_json = Column(Text, nullable=True)
    execution_report_json = Column(Text, nullable=True)
    market_quote_json = Column(Text, nullable=True)

    __table_args__ = (
        CheckConstraint("quantity > 0", name="chk_paper_orders_qty"),
        CheckConstraint("limit_price > 0", name="chk_paper_orders_price"),
        CheckConstraint("action IN ('BUY', 'SELL')", name="chk_paper_orders_action"),
        CheckConstraint("broker IN ('ibkr', 'alpaca')", name="chk_paper_orders_broker"),
        # Portable approximation of migration regex constraints (PostgreSQL enforces
        # the full regex in d2_2_paper_orders_transactional.sql). Application-level
        # @validates below mirrors the exact broker-aware patterns.
        CheckConstraint(
            "("
            "(broker = 'ibkr' AND (account_id LIKE 'DU%' OR account_id LIKE 'DF%') "
            "AND length(account_id) >= 5 AND length(account_id) <= 30) "
            "OR "
            "(broker = 'alpaca' AND ("
            "(account_id LIKE 'PA%' AND length(account_id) >= 7 AND length(account_id) <= 30) "
            "OR length(account_id) = 36"
            "))"
            ")",
            name="chk_paper_orders_account",
        ),
    )

    @validates("broker")
    def validate_broker(self, key, value):
        clean = str(value or "ibkr").strip().lower()
        if clean not in ("ibkr", "alpaca"):
            raise ValueError(f"Invalid broker '{value}'. Only 'ibkr' and 'alpaca' are supported.")
        return clean

    @validates("account_id")
    def validate_account_id(self, key, value):
        clean = str(value or "").strip().upper()
        current_broker = getattr(self, "broker", None) or "ibkr"
        if current_broker == "ibkr":
            if not clean or not re.match(r"^(DU|DF)[A-Z0-9]{3,28}$", clean):
                raise ValueError(
                    f"Paper account validation rejection: '{value}' is invalid for IBKR. "
                    "Account identifiers must strictly begin with 'DU' or 'DF' followed by 3-28 alphanumeric characters."
                )
        elif current_broker == "alpaca":
            if not clean or not (
                re.match(r"^PA[A-Z0-9]{5,28}$", clean) or
                re.match(r"^[0-9A-F]{8}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{12}$", clean)
            ):
                raise ValueError(
                    f"Paper account validation rejection: '{value}' is invalid for Alpaca. "
                    "Account identifiers must be a valid Alpaca paper account number (PA...) or UUID."
                )
        return clean


class PaperOrderEvent(Base):
    __tablename__ = "paper_order_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    order_id = Column(String(50), nullable=False, index=True)
    event_sequence = Column(Integer, nullable=False)
    from_status = Column(String(30), nullable=True)
    to_status = Column(String(30), nullable=False)
    action = Column(String(50), nullable=False)
    actor = Column(String(50), nullable=False)
    reason = Column(Text, nullable=True)
    event_data_json = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class PaperExecutionClaim(Base):
    __tablename__ = "paper_execution_claims"

    claim_id = Column(String(50), primary_key=True)
    order_id = Column(String(50), nullable=False, index=True)
    agent_id = Column(String(50), nullable=False, index=True)
    broker = Column(String(20), default="ibkr", nullable=False, index=True)
    claimed_at = Column(DateTime, default=datetime.utcnow)
    lease_expires_at = Column(DateTime, nullable=False, index=True)
    is_active = Column(Boolean, default=True, index=True)
    released_at = Column(DateTime, nullable=True)
    release_reason = Column(String(100), nullable=True)


