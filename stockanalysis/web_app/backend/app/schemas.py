"""Pydantic schemas for data validation and API documentation."""
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


# Auth
class UserRegister(BaseModel):
    username: str
    email: str
    password: str


class UserLogin(BaseModel):
    username: str
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str
    username: str
    role: str


# Watchlist
class WatchlistStockCreate(BaseModel):
    ticker: str
    name: Optional[str] = ""
    enabled: Optional[bool] = True
    shariah_status: Optional[str] = "NOT VERIFIED"
    shariah_source: Optional[str] = ""
    shariah_date: Optional[str] = ""
    notes: Optional[str] = ""


class WatchlistStockUpdate(BaseModel):
    name: Optional[str] = None
    enabled: Optional[bool] = None
    shariah_status: Optional[str] = None
    shariah_source: Optional[str] = None
    shariah_date: Optional[str] = None
    notes: Optional[str] = None


class WatchlistStockResponse(BaseModel):
    ticker: str
    name: str
    enabled: bool
    shariah_status: str
    shariah_source: str
    shariah_date: str
    notes: str


# Signals
class TodaySignalRow(BaseModel):
    ticker: str
    name: str
    as_of: str
    close: float
    ma30: Optional[float]
    ma50: Optional[float]
    ma250: Optional[float]
    roc20_pct: Optional[float]
    atr14: Optional[float]
    entry_rule: str
    exit_rule: str
    signal: str  # BUY CANDIDATE, WATCH, HOLD, EXIT, AVOID
    shariah_status: str
    explanation: str
    is_simulated_position: bool
    color_bg: str
    color_text: str


class TodaySignalsSummary(BaseModel):
    as_of_date: str
    total_stocks: int
    counts: Dict[str, int]
    signals: List[TodaySignalRow]


# Dashboard
class BenchmarkDashboardMetrics(BaseModel):
    initial_capital: float
    portfolio_ending_value: float
    spy_ending_value: float
    portfolio_total_return_pct: float
    spy_total_return_pct: float
    portfolio_cagr_pct: float
    spy_cagr_pct: float
    portfolio_max_drawdown_pct: float
    spy_max_drawdown_pct: float
    years_beating_spy: int
    years_compared: int
    completed_trades: int
    available_cash: float
    simulated_exposure: float
    latest_refresh_date: str


class AnnualPerformanceRow(BaseModel):
    year: int
    from_date: str
    through_date: str
    portfolio_return_pct: float
    spy_return_pct: float
    excess_pp: float
    portfolio_end_val: float
    spy_end_val: float
    portfolio_max_dd_pct: float
    spy_max_dd_pct: float


class EquityPoint(BaseModel):
    date: str
    portfolio: float
    cash: float
    positions: int
    spy: float
    portfolio_dd_pct: float
    spy_dd_pct: float


class DashboardOverviewResponse(BaseModel):
    metrics: BenchmarkDashboardMetrics
    annual_performance: List[AnnualPerformanceRow]
    recent_equity: List[EquityPoint]
    signal_counts: Dict[str, int]


# Stock Analysis
class OHLCVBar(BaseModel):
    date: str
    open: float
    high: float
    low: float
    close: float
    ma30: Optional[float] = None
    ma50: Optional[float] = None
    ma250: Optional[float] = None
    roc20: Optional[float] = None
    atr14: Optional[float] = None


class TradeMarker(BaseModel):
    date: str
    action: str  # BUY or EXIT
    price: float
    rule: str
    notes: Optional[str] = ""


class StockAnalysisResponse(BaseModel):
    ticker: str
    name: str
    latest_price: float
    as_of: str
    signal: str
    selected_entry: str
    selected_exit: str
    explanation: str
    shariah_status: str
    shariah_source: str
    shariah_date: str
    bars: List[OHLCVBar]
    trade_markers: List[TradeMarker]
    strategy_history: List[Dict[str, Any]]
    stock_vs_bh_vs_spy: Dict[str, Any]


# Backtest
class BacktestRequest(BaseModel):
    start_date: str = "2016-01-01"
    end_date: Optional[str] = None
    capital: float = 100000.0
    max_positions: int = 5
    train_years: int = 5
    fee_bps: float = 10.0
    min_training_buys: int = 2
    tickers: Optional[List[str]] = None


class BacktestJobResponse(BaseModel):
    job_id: str
    status: str
    progress_pct: int
    message: str
