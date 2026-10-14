"""Stock Analysis Router."""
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from app.engine_bridge import bridge
from app.database import get_db
from app.models import WatchlistStock
from app.config import PRICE_CACHE_DIR, ROLLING_PRICE_CACHE_DIR
from app.services.universe_manager import universe_manager

router = APIRouter(prefix="/api/stocks", tags=["Stock Analysis"])


@router.get("")
def list_available_stocks(db: Session = Depends(get_db)):
    """List all available tickers across baseline, rolling cache, and active universe."""
    tickers = {}
    # Query database first
    db_stocks = db.query(WatchlistStock).all()
    db_map = {s.ticker: s for s in db_stocks}

    # Discover baseline cached CSVs
    if PRICE_CACHE_DIR.exists():
        for f in PRICE_CACHE_DIR.glob("*.csv"):
            ticker = f.stem.replace("IDX_", "^")
            if ticker != "SPY":
                db_item = db_map.get(ticker)
                tickers[ticker] = {
                    "ticker": ticker,
                    "name": db_item.name if db_item and db_item.name else ticker,
                    "enabled": db_item.enabled if db_item else True,
                    "shariah_status": db_item.shariah_status if db_item else "NOT VERIFIED"
                }

    # Discover rolling cached CSVs
    if ROLLING_PRICE_CACHE_DIR.exists():
        for f in ROLLING_PRICE_CACHE_DIR.glob("*.csv"):
            ticker = f.stem.replace("IDX_", "^")
            if ticker != "SPY" and ticker not in tickers:
                db_item = db_map.get(ticker)
                u_item = universe_manager.get_stock(ticker)
                name = db_item.name if db_item and db_item.name else (u_item.get("name") if u_item else ticker)
                tickers[ticker] = {
                    "ticker": ticker,
                    "name": name,
                    "enabled": True,
                    "shariah_status": db_item.shariah_status if db_item else "NOT VERIFIED"
                }

    # Discover active universe stocks
    for u in universe_manager.get_all(include_inactive=False):
        t = u["ticker"]
        if t != "SPY" and t not in tickers:
            db_item = db_map.get(t)
            tickers[t] = {
                "ticker": t,
                "name": u.get("name", t),
                "enabled": True,
                "shariah_status": db_item.shariah_status if db_item else "NOT VERIFIED"
            }

    return sorted(tickers.values(), key=lambda x: x["ticker"])


@router.get("/{ticker}")
def get_stock_analysis(ticker: str, db: Session = Depends(get_db)):
    """Retrieve full analysis for a specific ticker."""
    stock = db.query(WatchlistStock).filter(WatchlistStock.ticker == ticker.upper()).first()
    sh_info = {
        "status": stock.shariah_status if stock else "NOT VERIFIED",
        "source": stock.shariah_source if stock else "",
        "date": stock.shariah_date if stock else "",
    }
    analysis = bridge.get_stock_analysis(ticker, custom_shariah=sh_info)
    if not analysis:
        raise HTTPException(status_code=404, detail=f"Stock data for '{ticker}' not found in cache")
    return analysis
