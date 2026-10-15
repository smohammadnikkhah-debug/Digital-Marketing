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
    PRICE_CACHE_DIR = LOCAL_ENGINE_CORE / "price_cache"
    DEFAULT_UNIVERSE_PATH = LOCAL_ENGINE_CORE / "Stock_Universe.xlsx"
    BASELINE_EXCEL_PATH = LOCAL_ENGINE_CORE / "results_v40" / "Adaptive_Trading_Research_V40.xlsx"
else:
    V41_ENGINE_DIR = PROJECT_ROOT / "adaptive_trading_v41"
    V40_ENGINE_DIR = PROJECT_ROOT / "adaptive_trading_v40"
    ACTIVE_ENGINE_DIR = V41_ENGINE_DIR if V41_ENGINE_DIR.exists() else V40_ENGINE_DIR
    PRICE_CACHE_DIR = V40_ENGINE_DIR / "price_cache"
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

# Database: SQLite default with auto-switch to PostgreSQL / Supabase
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{BACKEND_DIR / 'adaptive_platform.db'}")

# Security & Auth
SECRET_KEY = os.getenv("SECRET_KEY", "adaptive-trading-v40-super-secret-key-2026")
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
