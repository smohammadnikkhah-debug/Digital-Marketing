import os
from fastapi import FastAPI, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
from sqlalchemy import text
import pandas as pd

from app.database import engine, Base, SessionLocal, is_sqlite
from app.models import WatchlistStock, User
from app.auth import hash_password
from app.config import DEFAULT_UNIVERSE_PATH, EXPORTS_DIR, WEB_APP_DIR, IS_PRODUCTION, DB_SCHEMA
from app.routers import (
    dashboard,
    signals,
    stock_analysis,
    stock_research,
    watchlist,
    portfolio,
    backtesting,
    risk_analytics,
    settings,
    valuation,
    scanner,
)

# Initialize database schema
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Adaptive Trading V4.0 Platform API",
    description="Research-only web application API strictly adhering to the V4.0 Adaptive Trading baseline.",
    version="4.0.0",
)

# CORS configuration for Vite frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(dashboard.router)
app.include_router(signals.router)
app.include_router(stock_analysis.router)
app.include_router(stock_research.router)
app.include_router(valuation.router)
app.include_router(watchlist.router)
app.include_router(portfolio.router)
app.include_router(backtesting.router)
app.include_router(risk_analytics.router)
app.include_router(settings.router)
app.include_router(scanner.router)

# Mount compiled React SPA if built
FRONTEND_DIST = (WEB_APP_DIR / "frontend" / "dist").resolve()
if FRONTEND_DIST.exists():
    app.mount("/app", StaticFiles(directory=str(FRONTEND_DIST), html=True), name="static_app")


@app.on_event("startup")
def init_db_data():
    """Seed initial watchlist and demo admin user if database is empty."""
    db = SessionLocal()
    try:
        # Check if users table is empty
        if not db.query(User).first():
            admin = User(
                username="admin",
                email="admin@adaptivetrading.local",
                hashed_password=hash_password("admin"),
                role="admin"
            )
            db.add(admin)
            db.commit()

        # Check if watchlist is empty
        if not db.query(WatchlistStock).first() and DEFAULT_UNIVERSE_PATH.exists():
            df = pd.read_excel(DEFAULT_UNIVERSE_PATH, sheet_name="Stocks")
            for _, r in df.iterrows():
                ticker = str(r["Ticker"]).strip().upper()
                if not ticker or ticker == "SPY":
                    continue
                enabled_val = str(r.get("Enabled", "Yes")).strip().lower() in ("yes", "y", "1", "true")
                stock = WatchlistStock(
                    ticker=ticker,
                    name=ticker,
                    enabled=enabled_val,
                    shariah_status="NOT VERIFIED",  # Explicitly default to NOT VERIFIED
                    notes=str(r.get("Notes", "")) if pd.notna(r.get("Notes")) else ""
                )
                db.add(stock)
            db.commit()
        # Check if portfolio transactions are empty (local SQLite dev only when explicitly requested; NEVER in production)
        from app.models import PortfolioTransaction
        from app.services.user_portfolio import get_or_create_portfolio, seed_sample_portfolio
        if is_sqlite and not IS_PRODUCTION and os.getenv("SEED_SAMPLE_PORTFOLIO", "false").lower() in ("true", "1"):
            if not db.query(PortfolioTransaction).first():
                p = get_or_create_portfolio(db)
                seed_sample_portfolio(db, p.id)
    except Exception as e:
        print(f"Startup data init notice: {e}")
    finally:
        db.close()

    # Initialize screener snapshot and monitored stocks in database
    from app.services.snapshot_service import snapshot_service
    snapshot_service._ensure_tables_and_seed()

    # Start the automated nightly scan scheduler
    from app.jobs import scheduler
    scheduler.start()


@app.get("/api/health")
def health_check(response: Response):
    """Liveness and readiness probe verifying application runtime and real database connectivity."""
    db_status = "healthy"
    db_error = None
    db_type = "sqlite" if is_sqlite else "postgresql"

    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1;"))
    except Exception as e:
        db_status = "unhealthy"
        db_error = str(e)
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    payload = {
        "status": db_status,
        "engine": "Adaptive Trading V4.0 Baseline",
        "research_only": True,
        "database": {
            "type": db_type,
            "schema": DB_SCHEMA,
            "status": db_status,
        }
    }
    if db_error:
        payload["database"]["error"] = db_error

    return payload


@app.get("/")
def root():
    return RedirectResponse(url="/app/")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)
