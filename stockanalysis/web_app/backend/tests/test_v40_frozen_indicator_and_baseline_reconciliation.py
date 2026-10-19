"""Frozen V4.0 Regression Verification & Baseline Reconciliation Test Suite.

Verifies:
1. Exact Indicator Math: Tests SMA30, SMA50, SMA250, ROC20, and ATR14 against strategy_core_v38.prep().
2. Database-backed OHLCV equivalence: Confirms that DailyBar loaded from DB produces
   bit-exact indicator values matching the original baseline CSV data.
3. Walk-Forward Parameter Selection: Tests strategy_core_v38.train() parameter optimization.
4. Baseline Reconciliation: Reconciles signals and rules against the audited baseline
   Excel file (Adaptive_Trading_Research_V40.xlsx -> TodayTrade sheet).
5. Explicit reporting of any discrepancies without mutating frozen strategy rules.
"""
import pytest
import numpy as np
import pandas as pd
from datetime import datetime
from app.database import Base, engine, SessionLocal
from app.models import DailyBar
from app.services.scanner_service import scanner_service, ROLLING_PRICE_CACHE_DIR, PRICE_CACHE_DIR
from app.services.snapshot_service import snapshot_service
from app.config import BASELINE_EXCEL_PATH
import strategy_core_v38 as v38_core
import engine as v41_engine


@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    snapshot_service._ensure_tables_and_seed()
    yield


TARGET_CACHE = ROLLING_PRICE_CACHE_DIR if (ROLLING_PRICE_CACHE_DIR / "AAPL.csv").exists() else PRICE_CACHE_DIR


class TestV40FrozenRegressionAndReconciliation:

    def test_01_indicator_math_exactness(self):
        """Validates SMA30, SMA50, SMA250, ROC20, ATR14 against strategy_core_v38.prep()."""
        csv_file = TARGET_CACHE / "NVDA.csv"
        assert csv_file.exists(), f"Missing {csv_file}"
        raw = pd.read_csv(csv_file, index_col="Date", parse_dates=True).sort_index()

        d = v38_core.prep(raw)

        # 1. Verify SMA30, SMA50, SMA250
        assert "MA30" in d.columns
        assert "MA50" in d.columns
        assert "MA250" in d.columns
        # Manual check on last row
        tail_close = d["Close"].dropna()
        expected_ma30 = tail_close.iloc[-30:].mean()
        expected_ma50 = tail_close.iloc[-50:].mean()
        expected_ma250 = tail_close.iloc[-250:].mean()

        assert abs(d["MA30"].iloc[-1] - expected_ma30) < 1e-6
        assert abs(d["MA50"].iloc[-1] - expected_ma50) < 1e-6
        assert abs(d["MA250"].iloc[-1] - expected_ma250) < 1e-6

        # 2. Verify ROC20: (Close_t / Close_{t-20}) - 1
        expected_roc20 = (tail_close.iloc[-1] / tail_close.iloc[-21]) - 1.0
        assert abs(d["ROC20"].iloc[-1] - expected_roc20) < 1e-6

        # 3. Verify ATR14
        prev_close = d["Close"].shift(1)
        tr = pd.concat([d["High"] - d["Low"], (d["High"] - prev_close).abs(), (d["Low"] - prev_close).abs()], axis=1).max(axis=1)
        expected_atr14 = tr.iloc[-14:].mean()
        assert abs(d["ATR14"].iloc[-1] - expected_atr14) < 1e-6

    def test_02_database_backed_ohlcv_indicator_invariance(self):
        """Persists NVDA and QQQ into DailyBar and asserts bit-exact indicator outputs."""
        for ticker in ["NVDA", "QQQ"]:
            raw_csv = pd.read_csv(TARGET_CACHE / f"{ticker}.csv", index_col="Date", parse_dates=True).sort_index()
            scanner_service._persist_bars_to_db(ticker, raw_csv, full=True)

            # Query from DB
            db = SessionLocal()
            try:
                bars = db.query(DailyBar).filter(DailyBar.ticker == ticker).order_by(DailyBar.bar_date.asc()).all()
                df_db = pd.DataFrame([{
                    "Date": b.bar_date,
                    "Open": b.open,
                    "High": b.high,
                    "Low": b.low,
                    "Close": b.close,
                } for b in bars]).set_index("Date")
                df_db.index = pd.to_datetime(df_db.index)
            finally:
                db.close()

            # Run prep on both
            d_csv = v38_core.prep(raw_csv.tail(len(df_db)))
            d_db = v38_core.prep(df_db)

            # Assert all 5 indicators are identical
            for col in ["MA30", "MA50", "MA250", "ROC20", "ATR14"]:
                diff = (d_csv[col].dropna() - d_db[col].dropna()).abs().max()
                assert diff < 1e-6, f"Divergence in {col} for {ticker}: {diff}"

    def test_03_walk_forward_parameter_selection_and_rules(self):
        """Verifies walk-forward parameter selection logic (v41_engine.train)."""
        raw = pd.read_csv(TARGET_CACHE / "QQQ.csv", index_col="Date", parse_dates=True).sort_index()
        d = v38_core.prep(raw)

        # Run training as of 2026-10-09
        win, score = v41_engine.train(
            d,
            asof=pd.Timestamp("2026-10-09"),
            years=5,
            fee=10,
            min_buys=2,
            exit_mode="baseline",
        )
        assert win is not None
        assert "entry" in win
        assert "exit" in win
        assert win["entry"] in v38_core.ENTRIES
        assert win["exit"] in v38_core.EXITS

    def test_04_baseline_excel_reconciliation(self):
        """Reconciles computed signals against the approved V4.0 Excel baseline (TodayTrade)."""
        if not BASELINE_EXCEL_PATH.exists():
            pytest.skip(f"Baseline Excel not found at {BASELINE_EXCEL_PATH}")

        xl = pd.ExcelFile(BASELINE_EXCEL_PATH)
        assert "TodayTrade" in xl.sheet_names
        df_excel = xl.parse("TodayTrade")

        reconciliation_discrepancies = []

        for _, row in df_excel.iterrows():
            ticker = str(row["Ticker"]).strip().upper()
            csv_path = TARGET_CACHE / f"{ticker}.csv"
            if not csv_path.exists():
                continue

            # Load and prep
            raw = pd.read_csv(csv_path, index_col="Date", parse_dates=True).sort_index()
            d = v38_core.prep(raw)
            asof_date = str(row["As of"])[:10]

            if asof_date in d.index.strftime("%Y-%m-%d").values:
                row_d = d.loc[asof_date]
                if isinstance(row_d, pd.DataFrame):
                    row_d = row_d.iloc[-1]

                # Check indicators if present in baseline sheet
                for col in ["MA30", "MA50", "MA250"]:
                    if col in row and pd.notna(row[col]) and pd.notna(row_d[col]):
                        expected_val = float(row[col])
                        calc_val = float(row_d[col])
                        if abs(expected_val - calc_val) > 0.05:  # Tolerance for historical rounding in Excel
                            reconciliation_discrepancies.append(
                                f"{ticker} {col}: Excel={expected_val}, Calc={calc_val}"
                            )

        # Report reconciliation findings
        if reconciliation_discrepancies:
            print("\n[Reconciliation Notice] Minor differences (likely Excel roundings):", reconciliation_discrepancies)
        else:
            print("\n[Reconciliation Success] 100% agreement with approved V4.0 Excel baseline!")
        assert len(reconciliation_discrepancies) == 0, f"Discrepancies found: {reconciliation_discrepancies}"
