"""Pytest configuration for StockAnalysis Stage D2 test taxonomy.

Markers:
- safe_local: unit/SQLite tests with no live broker or production database
- isolated_postgres: disposable Postgres only (not production)
- live_alpaca_readonly: live Alpaca paper API read-only calls
- prod_db: production/shared DB (requires STOCKANALYSIS_ALLOW_PROD_DB_TESTS=1)
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

_BACKEND_DIR = Path(__file__).resolve().parent.parent
_SAFE_SQLITE = f"sqlite:///{(_BACKEND_DIR / 'adaptive_platform_pytest.db').as_posix()}"

# Default: force SQLite so accidental prod DATABASE_URL cannot mutate shared DBs.
if os.getenv("STOCKANALYSIS_FORCE_SQLITE", "1").strip().lower() in ("1", "true", "yes"):
    os.environ["DATABASE_URL"] = os.environ.get("STOCKANALYSIS_TEST_DATABASE_URL", _SAFE_SQLITE)
    os.environ.setdefault("ENVIRONMENT", "development")


def pytest_configure(config):
    config.addinivalue_line("markers", "safe_local: local unit/SQLite tests")
    config.addinivalue_line("markers", "isolated_postgres: isolated disposable PostgreSQL")
    config.addinivalue_line("markers", "live_alpaca_readonly: live Alpaca paper read-only")
    config.addinivalue_line("markers", "prod_db: production database tests (explicit auth required)")


_SAFE_LOCAL_FILES = (
    "test_alpaca_execution_agent",
    "test_market_data_contract",
    "test_stage_d2_2",
    "test_d2_2_migration",
    "test_d2_3a1_database_safety",
    "test_ibkr_paper_execution_foundation",
    "test_ibkr_paper_integration",
    "test_postgresql_semantics",
)


def pytest_collection_modifyitems(config, items):
    allow_prod = os.getenv("STOCKANALYSIS_ALLOW_PROD_DB_TESTS", "").strip().lower() in ("1", "true", "yes")

    for item in items:
        path = str(item.fspath).replace("\\", "/")

        if "test_d2_3a1_final_verification" in path:
            item.add_marker(pytest.mark.prod_db)
            if not allow_prod:
                item.add_marker(
                    pytest.mark.skip(
                        reason="prod_db skipped (set STOCKANALYSIS_ALLOW_PROD_DB_TESTS=1)"
                    )
                )
        elif "test_isolated_postgres_migration" in path:
            item.add_marker(pytest.mark.isolated_postgres)
        elif "test_alpaca_paper_integration" in path:
            item.add_marker(pytest.mark.live_alpaca_readonly)
        elif any(key in path for key in _SAFE_LOCAL_FILES):
            item.add_marker(pytest.mark.safe_local)
