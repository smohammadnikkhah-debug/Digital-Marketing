"""Stock Research Router for Advanced Individual Equity Analysis (Phase 3A).

Provides endpoints for:
- Autocomplete search across tickers, company names, aliases, and global equities
- 6-panel comprehensive financial information (Valuation, Cash Flow, Margins, Balance Sheet, Dividends, Profitability)
- Multi-frequency financial chart series (Quarterly, Quarterly TTM, Annually)
- Price & volume candlestick history (Daily, Weekly, Monthly)
- Transparent 4-section risk assessment (Trend, Valuation, Financial, Market)
- Watchlist integration
"""
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import WatchlistStock
from app.services.security_master import search_symbols
from app.services.financial_data import financial_data_service

router = APIRouter(prefix="/api/research", tags=["Stock Research"])


@router.get("/search")
def autocomplete_search(
    q: str = Query(..., min_length=1, description="Search term (ticker, company name, alias)"),
    db: Session = Depends(get_db)
):
    """Global intelligent autocomplete search across securities master, aliases, and live market."""
    results = search_symbols(q, db=db)
    return results


@router.get("/{ticker}/overview")
def get_company_overview(ticker: str):
    """Retrieve comprehensive 6-panel financial overview with documented reporting periods, source, and currency."""
    ticker = ticker.strip().upper()
    try:
        overview = financial_data_service.get_company_overview(ticker)
        return overview
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch financial overview for {ticker}: {str(e)}")


@router.get("/{ticker}/financial-history")
def get_financial_history(
    ticker: str,
    frequency: str = Query("quarterly", pattern="^(quarterly|quarterly_ttm|annually)$"),
    range: str = Query("5y", pattern="^(1y|3y|5y|10y|max)$")
):
    """Retrieve point-in-time financial metrics series across Quarterly, Quarterly TTM, or Annually."""
    ticker = ticker.strip().upper()
    try:
        series_data = financial_data_service.get_financial_chart_series(ticker, frequency=frequency, time_range=range)
        return series_data
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch financial history for {ticker}: {str(e)}")


@router.get("/{ticker}/price-history")
def get_price_history(
    ticker: str,
    interval: str = Query("daily", pattern="^(daily|weekly|monthly)$"),
    range: str = Query("5y", pattern="^(1y|3y|5y|10y|max)$")
):
    """Retrieve OHLCV price and trading volume history for chart rendering."""
    ticker = ticker.strip().upper()
    try:
        bars = financial_data_service.get_price_volume_history(ticker, interval=interval, time_range=range)
        return {"ticker": ticker, "interval": interval, "range": range, "bars": bars}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch price history for {ticker}: {str(e)}")


@router.get("/{ticker}/risk")
def get_stock_risk_assessment(ticker: str):
    """Retrieve 4 transparent risk sections: Trend Risk, Valuation Risk, Financial Risk, and Market Risk."""
    ticker = ticker.strip().upper()
    try:
        risk_data = financial_data_service.get_stock_risk_assessment(ticker)
        return risk_data
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to compute risk assessment for {ticker}: {str(e)}")


@router.post("/{ticker}/add-to-watchlist")
def add_to_watchlist(ticker: str, db: Session = Depends(get_db)):
    """Convenience action to add researched stock to user's active watchlist."""
    ticker = ticker.strip().upper()
    existing = db.query(WatchlistStock).filter(WatchlistStock.ticker == ticker).first()
    if existing:
        return {"message": f"{ticker} is already in your watchlist", "ticker": ticker, "added": False}

    # Retrieve short company name if available
    name = ticker
    try:
        overview = financial_data_service.get_company_overview(ticker)
        name = overview.get("profile", {}).get("name", ticker)
    except Exception:
        pass

    stock = WatchlistStock(
        ticker=ticker,
        name=name,
        enabled=True,
        shariah_status="NOT VERIFIED",  # Explicitly default to NOT VERIFIED per strict governance rules
        shariah_source="",
        shariah_date="",
        notes="Added via Stock Research terminal."
    )
    db.add(stock)
    db.commit()
    db.refresh(stock)
    return {"message": f"Successfully added {ticker} to watchlist", "ticker": ticker, "added": True}
