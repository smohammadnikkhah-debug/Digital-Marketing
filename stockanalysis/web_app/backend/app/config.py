"""Application Configuration for Adaptive Trading V4.0 Web Application."""
import os
from pathlib import Path

# Paths
BACKEND_DIR = Path(__file__).resolve().parent.parent
WEB_APP_DIR = BACKEND_DIR.parent
PROJECT_ROOT = WEB_APP_DIR.parent

# Engine discovery: prioritize self-contained engine_core for container deployments
LOCAL_ENGINE_CORE = BACKEND_DIR / "engine_core"
if LOCAL_ENGINE_CORE.exists() and (LOCAL_ENGINE_CORE / "engine.py").exists():
    ACTIVE_ENGINE_DIR = LOCAL_ENGINE_CORE
    V41_ENGINE_DIR = LOCAL_ENGINE_CORE
    V40_ENGINE_DIR = LOCAL_ENGINE_CORE
    PRICE_CACHE_DIR = LOCAL_ENGINE_CORE / "price_cache" if (LOCAL_ENGINE_CORE / "price_cache").exists() else (BACKEND_DIR / "data_cache" / "price_cache")
    DEFAULT_UNIVERSE_PATH = LOCAL_ENGINE_CORE / "Stock_Universe.xlsx"
    BASELINE_EXCEL_PATH = LOCAL_ENGINE_CORE / "results_v40" / "Adaptive_Trading_Research_V40.xlsx"
else:
    V41_ENGINE_DIR = PROJECT_ROOT / "adaptive_trading_v41"
    V40_ENGINE_DIR = PROJECT_ROOT / "adaptive_trading_v40"
    ACTIVE_ENGINE_DIR = V41_ENGINE_DIR if V41_ENGINE_DIR.exists() else V40_ENGINE_DIR
    PRICE_CACHE_DIR = V40_ENGINE_DIR / "price_cache" if (V40_ENGINE_DIR / "price_cache").exists() else (BACKEND_DIR / "data_cache" / "price_cache")
    DEFAULT_UNIVERSE_PATH = V40_ENGINE_DIR / "Stock_Universe.xlsx"
    BASELINE_EXCEL_PATH = V40_ENGINE_DIR / "results_v40" / "Adaptive_Trading_Research_V40.xlsx"

import sys
if str(ACTIVE_ENGINE_DIR) not in sys.path:
    sys.path.insert(0, str(ACTIVE_ENGINE_DIR))
EXPORTS_DIR = BACKEND_DIR / "exports"
EXPORTS_DIR.mkdir(parents=True, exist_ok=True)

# Rolling Research Cache & Registries (Separated from frozen baseline)
DATA_CACHE_DIR = BACKEND_DIR / "data_cache"
ROLLING_PRICE_CACHE_DIR = DATA_CACHE_DIR / "price_cache"
ROLLING_PRICE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
UNIVERSE_REGISTRY_PATH = DATA_CACHE_DIR / "universe_registry.json"
FINANCIALS_CACHE_DIR = DATA_CACHE_DIR / "financials"
VALUATION_CACHE_DIR = DATA_CACHE_DIR / "valuation_runs"
VALUATION_CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Environment & Production Guards
ENVIRONMENT = os.getenv("ENVIRONMENT", "development").strip().lower()
IS_PRODUCTION = ENVIRONMENT == "production"

# Database: SQLite default for local development, mandatory PostgreSQL for production
_raw_db_url = os.getenv("DATABASE_URL")

if IS_PRODUCTION:
    if not _raw_db_url or not _raw_db_url.strip():
        raise RuntimeError(
            "FATAL CONFIGURATION ERROR: ENVIRONMENT is 'production' but DATABASE_URL is not set. "
            "Silent fallback to SQLite in production is strictly prohibited."
        )
    if _raw_db_url.strip().startswith("sqlite"):
        raise RuntimeError(
            "FATAL CONFIGURATION ERROR: Production cannot use SQLite DATABASE_URL. "
            "A PostgreSQL connection string pointing to Supabase schema 'stockanalysis' is required."
        )
else:
    if not _raw_db_url:
        _raw_db_url = f"sqlite:///{BACKEND_DIR / 'adaptive_platform.db'}"

_raw_db_url = _raw_db_url.strip()
if _raw_db_url.startswith("postgres://"):
    DATABASE_URL = _raw_db_url.replace("postgres://", "postgresql+psycopg2://", 1)
elif _raw_db_url.startswith("postgresql://") and not _raw_db_url.startswith("postgresql+"):
    DATABASE_URL = _raw_db_url.replace("postgresql://", "postgresql+psycopg2://", 1)
else:
    DATABASE_URL = _raw_db_url

DB_SCHEMA = os.getenv("DB_SCHEMA", "stockanalysis")
WORKER_MODE = os.getenv("WORKER_MODE", "embedded")  # "embedded" (web runs in-process worker) or "standalone" (decoupled worker container)
SNAPSHOT_RETENTION_COUNT = int(os.getenv("SNAPSHOT_RETENTION_COUNT", "30"))
JOB_RETENTION_COUNT = int(os.getenv("JOB_RETENTION_COUNT", "50"))

# Security & Auth
SECRET_KEY = os.getenv("SECRET_KEY", "adaptive-trading-v40-super-secret-key-2026")
STOCKANALYSIS_ADMIN_KEY = os.getenv("STOCKANALYSIS_ADMIN_KEY", "stockanalysis-admin-key-dev-local-2026")
KNOWN_DEV_INGEST_KEYS = {
    "ibkr-ingest-key-dev-local-2026",
    "test_gateway_ibkr_ingest_key_2026",
    "dev-key",
    "default",
}

_raw_ingest_key = os.getenv("IBKR_INGESTION_KEY", os.getenv("STOCKANALYSIS_IBKR_INGEST_KEY", "")).strip()
if IS_PRODUCTION:
    if not _raw_ingest_key or _raw_ingest_key in KNOWN_DEV_INGEST_KEYS:
        # Production fails closed: missing, empty, or known dev keys cannot be used
        IBKR_INGESTION_KEY = ""
    else:
        IBKR_INGESTION_KEY = _raw_ingest_key
else:
    IBKR_INGESTION_KEY = _raw_ingest_key or "ibkr-ingest-key-dev-local-2026"
IBKR_PAPER_ENABLED = os.getenv("IBKR_PAPER_ENABLED", "true").strip().lower() in ("true", "1", "yes")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 7 days

# Strategy Defaults (strictly V4.0 baseline)
DEFAULT_CAPITAL = 100000.0
DEFAULT_MAX_POSITIONS = 5
DEFAULT_TRAIN_YEARS = 5
DEFAULT_FEE_BPS = 10.0
DEFAULT_MIN_BUYS = 2

# Signal Colors (from V4.0 Excel definition)
SIGNAL_PALETTE = {
    "BUY CANDIDATE": {"bg": "#C6EFCE", "text": "#006100", "border": "#A3E4B0"},
    "WATCH": {"bg": "#FFF2CC", "text": "#7F6000", "border": "#FFE699"},
    "HOLD": {"bg": "#D9E1E8", "text": "#404040", "border": "#BDC9D4"},
    "EXIT": {"bg": "#FF9999", "text": "#9C0006", "border": "#FF6B6B"},
    "AVOID": {"bg": "#8B0000", "text": "#FFFFFF", "border": "#660000"}
}

# Data Provenance Tracking
DATA_PROVENANCE = {
    "mode": "FROZEN_BASELINE",
    "badge_text": "Frozen Baseline Dataset (Oct 9, 2026)",
    "as_of_date": "2026-10-09",
    "description": "Audited V4.0 quantitative baseline research snapshot. 100% deterministic, cached Yahoo adjusted OHLC.",
    "is_refreshed": False,
    "strategy_version": "V4.0 Baseline (via V4.1 Engine in --exit-mode baseline)",
}
