"""SQLAlchemy models for Watchlist, Backtests, Users, and Settings."""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, Float, DateTime, Text
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
