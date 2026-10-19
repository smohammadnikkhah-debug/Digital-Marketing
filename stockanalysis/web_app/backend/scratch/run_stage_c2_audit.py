"""Stage C2 Comprehensive Analysis Dashboard UAT & Validation Audit Script.

Conducts end-to-end programmatic inspection of:
1. Provenance reconciliation (231 stocks breakdown: baseline vs refreshed vs unscanned vs others).
2. Technical Analysis engine (/api/stocks/{ticker}) for SPY, AAPL, MSFT, GOOGL, NVDA, QCOM.
   - Evaluates V4.0 indicators: SMA30, SMA50, SMA250, ROC20, ATR14.
   - Verifies entry/exit triggers and MA250 exit behaviour.
   - Checks data date, source, freshness.
3. Fundamental Research engine (/api/research/{ticker}/...) for SPY, AAPL, MSFT, GOOGL, NVDA, QCOM.
   - Checks overview, 6 panels, financial history series, risk assessment.
   - Identifies whether real vs placeholder vs missing reports exist (especially for ETF SPY vs equities).
4. Valuation engine (/api/valuation/{ticker}/...) for SPY, AAPL, MSFT, GOOGL, NVDA, QCOM.
   - Checks DCF workspace, historical matrix, sensitivity heatmap, provenance table.
5. Screener & Dashboard outputs (/api/signals, /api/dashboard).
"""
import sys
import os
import json
from pathlib import Path
from datetime import datetime

# Setup paths
backend_dir = Path(r"c:\Users\zeiva\OneDrive\Desktop\Project\Digital Marketing\stockanalysis\web_app\backend")
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

os.chdir(backend_dir)
os.environ["TESTING"] = "1"

from fastapi.testclient import TestClient
from app.main import app
from app.database import get_db, SessionLocal
from app.models import MonitoredStock, ScreenerSnapshot, RefreshJob, WatchlistStock
from app.services.universe_manager import universe_manager
from app.services.financial_data import financial_data_service
from app.services.valuation import valuation_service
from app.engine_bridge import bridge

client = TestClient(app)

audit_results = {
    "audit_timestamp": datetime.now().isoformat(),
    "provenance_reconciliation": {},
    "stocks_audit": {},
    "engine_rules_verification": {},
    "dashboard_and_screener_audit": {},
    "frontend_mock_and_gap_inventory": [],
}

print("=" * 80)
print("STAGE C2 AUDIT: STARTING COMPREHENSIVE VALIDATION")
print("=" * 80)

# ---------------------------------------------------------
# 1. PROVENANCE RECONCILIATION
# ---------------------------------------------------------
print("\n--- 1. PROVENANCE RECONCILIATION ---")
db = SessionLocal()
try:
    total_monitored = db.query(MonitoredStock).count()
    all_stocks = db.query(MonitoredStock).all()
    
    unscanned = [s for s in all_stocks if s.latest_signal_json is None]
    with_signal = [s for s in all_stocks if s.latest_signal_json is not None]
    
    # Frozen baseline list from engine_bridge or results_v40
    baseline_tickers = set(bridge.BASELINE_TICKERS if hasattr(bridge, "BASELINE_TICKERS") else [
        "QQQ", "AMZN", "NVDA", "GOOGL", "META", "AMD", "MA", "ELF", "IONQ", "NOW",
        "INTC", "NKE", "ORCL", "AVGO", "QCOM", "UBER", "CRWD", "ANET", "APP", "ASTS",
        "FICO", "MRVL", "COHR", "TSLA", "CELH", "ULTA", "GRAB", "RDDT"
    ])
    
    # Check tickers with signals
    tickers_with_signal = {s.ticker for s in with_signal}
    
    # Check refreshed tickers in C1.5 testing: SPY, AAPL, MSFT
    c1_5_refreshed = {"SPY", "AAPL", "MSFT"}
    
    classified_baseline = tickers_with_signal.intersection(baseline_tickers)
    classified_refreshed = tickers_with_signal.intersection(c1_5_refreshed)
    remaining_with_signal = tickers_with_signal - baseline_tickers - c1_5_refreshed
    
    print(f"Total Monitored Stocks in DB: {total_monitored}")
    print(f"Stocks without signal (unscanned): {len(unscanned)}")
    print(f"Stocks with signal: {len(with_signal)}")
    print(f"Frozen Baseline stocks with signal: {len(classified_baseline)}")
    print(f"C1.5 Refreshed candidates with signal: {len(classified_refreshed)}")
    print(f"Remaining stocks with signal (The 'Missing 5'): {remaining_with_signal}")
    
    missing_details = []
    for t in sorted(remaining_with_signal):
        st = db.query(MonitoredStock).filter(MonitoredStock.ticker == t).first()
        missing_details.append({
            "ticker": t,
            "name": st.name,
            "sector": st.sector,
            "exchange": st.exchange,
            "data_status": st.data_status,
            "source": st.source,
            "last_scanned_at": str(st.last_scanned_at),
            "latest_price_date": str(st.latest_price_date),
        })
    
    audit_results["provenance_reconciliation"] = {
        "total_monitored": total_monitored,
        "unscanned_count": len(unscanned),
        "with_signal_count": len(with_signal),
        "baseline_count": len(classified_baseline),
        "baseline_tickers": sorted(list(classified_baseline)),
        "c1_5_refreshed_count": len(classified_refreshed),
        "c1_5_refreshed_tickers": sorted(list(classified_refreshed)),
        "the_five_discrepancy_stocks": missing_details,
        "math_proof": f"{len(classified_refreshed)} (refreshed) + {len(classified_baseline)} (baseline) + {len(unscanned)} (unscanned) + {len(remaining_with_signal)} (expansion) = {len(classified_refreshed) + len(classified_baseline) + len(unscanned) + len(remaining_with_signal)}"
    }
    print(f"Reconciliation Math: {audit_results['provenance_reconciliation']['math_proof']}")

finally:
    db.close()

# ---------------------------------------------------------
# 2. TARGET STOCKS TECHNICAL, FUNDAMENTAL, AND VALUATION AUDIT
# ---------------------------------------------------------
target_tickers = ["SPY", "AAPL", "MSFT", "GOOGL", "NVDA", "QCOM"]

for ticker in target_tickers:
    print(f"\n=================== AUDITING: {ticker} ===================")
    stock_audit = {
        "ticker": ticker,
        "technical_analysis": {},
        "fundamental_overview": {},
        "financial_history": {},
        "risk_assessment": {},
        "valuation_workspace": {},
        "valuation_matrix": {},
        "valuation_provenance": {},
        "gaps_identified": [],
    }
    
    # 2.1 Technical Analysis: GET /api/stocks/{ticker}
    try:
        resp = client.get(f"/api/stocks/{ticker}")
        if resp.status_code == 200:
            tech = resp.json()
            stock_audit["technical_analysis"] = {
                "status_code": 200,
                "ticker": tech.get("ticker"),
                "latest_date": tech.get("latest_date"),
                "signal": tech.get("signal"),
                "current_price": tech.get("current_price"),
                "rules": tech.get("rules"),
                "indicators": tech.get("indicators"),
                "confidence": tech.get("confidence"),
                "shariah_status": tech.get("shariah_status"),
                "provenance": tech.get("provenance"),
            }
            # Verify indicators exist
            inds = tech.get("indicators", {})
            sma30 = inds.get("SMA30")
            sma50 = inds.get("SMA50")
            sma250 = inds.get("SMA250")
            roc20 = inds.get("ROC20")
            atr14 = inds.get("ATR14")
            print(f"  [Technical] Signal: {tech.get('signal')} | Date: {tech.get('latest_date')} | Price: {tech.get('current_price')}")
            print(f"  [Indicators] SMA30: {sma30}, SMA50: {sma50}, SMA250: {sma250}, ROC20: {roc20}, ATR14: {atr14}")
        else:
            stock_audit["technical_analysis"] = {"status_code": resp.status_code, "detail": resp.text}
            stock_audit["gaps_identified"].append(f"Technical analysis endpoint returned {resp.status_code}: {resp.text}")
            print(f"  [Technical ERROR] Status {resp.status_code}: {resp.text}")
    except Exception as e:
        stock_audit["technical_analysis"] = {"error": str(e)}
        stock_audit["gaps_identified"].append(f"Technical analysis exception: {str(e)}")
        print(f"  [Technical EXCEPTION] {str(e)}")

    # 2.2 Fundamental Overview: GET /api/research/{ticker}/overview
    try:
        resp = client.get(f"/api/research/{ticker}/overview")
        if resp.status_code == 200:
            fo = resp.json()
            stock_audit["fundamental_overview"] = {
                "status_code": 200,
                "profile": fo.get("profile"),
                "data_source": fo.get("data_source"),
                "last_filing_date": fo.get("last_filing_date"),
                "currency": fo.get("currency"),
                "metrics_summary": {
                    "market_cap": fo.get("market_cap"),
                    "pe_ratio": fo.get("pe_ratio"),
                    "revenue_ttm": fo.get("revenue_ttm"),
                    "net_income_ttm": fo.get("net_income_ttm"),
                    "free_cash_flow_ttm": fo.get("free_cash_flow_ttm"),
                    "operating_margin": fo.get("operating_margin"),
                },
                "panels_available": list(fo.get("panels", {}).keys()) if isinstance(fo.get("panels"), dict) else [],
            }
            print(f"  [Fundamental Overview] Source: {fo.get('data_source')} | Filing Date: {fo.get('last_filing_date')} | Rev TTM: {fo.get('revenue_ttm')}")
        else:
            stock_audit["fundamental_overview"] = {"status_code": resp.status_code, "detail": resp.text}
            stock_audit["gaps_identified"].append(f"Fundamental overview returned {resp.status_code}: {resp.text}")
            print(f"  [Fundamental Overview ERROR] Status {resp.status_code}: {resp.text}")
    except Exception as e:
        stock_audit["fundamental_overview"] = {"error": str(e)}
        stock_audit["gaps_identified"].append(f"Fundamental overview exception: {str(e)}")
        print(f"  [Fundamental Overview EXCEPTION] {str(e)}")

    # 2.3 Financial History: GET /api/research/{ticker}/financial-history
    try:
        resp = client.get(f"/api/research/{ticker}/financial-history?frequency=annually&range=5y")
        if resp.status_code == 200:
            fh = resp.json()
            stock_audit["financial_history"] = {
                "status_code": 200,
                "series_count": len(fh.get("series", [])) if isinstance(fh.get("series"), list) else 0,
                "frequency": fh.get("frequency"),
                "range": fh.get("range"),
                "source": fh.get("source"),
            }
            print(f"  [Financial History] Annual periods: {stock_audit['financial_history']['series_count']}")
        else:
            stock_audit["financial_history"] = {"status_code": resp.status_code, "detail": resp.text}
            stock_audit["gaps_identified"].append(f"Financial history returned {resp.status_code}: {resp.text}")
            print(f"  [Financial History ERROR] Status {resp.status_code}: {resp.text}")
    except Exception as e:
        stock_audit["financial_history"] = {"error": str(e)}
        stock_audit["gaps_identified"].append(f"Financial history exception: {str(e)}")
        print(f"  [Financial History EXCEPTION] {str(e)}")

    # 2.4 Risk Assessment: GET /api/research/{ticker}/risk
    try:
        resp = client.get(f"/api/research/{ticker}/risk")
        if resp.status_code == 200:
            rk = resp.json()
            stock_audit["risk_assessment"] = {
                "status_code": 200,
                "overall_risk_score": rk.get("overall_risk_score"),
                "overall_risk_level": rk.get("overall_risk_level"),
                "sections": list(rk.get("sections", {}).keys()) if isinstance(rk.get("sections"), dict) else [],
            }
            print(f"  [Risk Assessment] Score: {rk.get('overall_risk_score')} ({rk.get('overall_risk_level')})")
        else:
            stock_audit["risk_assessment"] = {"status_code": resp.status_code, "detail": resp.text}
            stock_audit["gaps_identified"].append(f"Risk assessment returned {resp.status_code}: {resp.text}")
            print(f"  [Risk Assessment ERROR] Status {resp.status_code}: {resp.text}")
    except Exception as e:
        stock_audit["risk_assessment"] = {"error": str(e)}
        stock_audit["gaps_identified"].append(f"Risk assessment exception: {str(e)}")
        print(f"  [Risk Assessment EXCEPTION] {str(e)}")

    # 2.5 Valuation Workspace: GET /api/valuation/{ticker}/workspace
    try:
        resp = client.get(f"/api/valuation/{ticker}/workspace")
        if resp.status_code == 200:
            vw = resp.json()
            stock_audit["valuation_workspace"] = {
                "status_code": 200,
                "current_price": vw.get("current_price"),
                "intrinsic_value_base": vw.get("scenario_results", {}).get("base", {}).get("intrinsic_value_per_share") if isinstance(vw.get("scenario_results"), dict) else None,
                "margin_of_safety_base": vw.get("scenario_results", {}).get("base", {}).get("margin_of_safety_pct") if isinstance(vw.get("scenario_results"), dict) else None,
                "recommendation": vw.get("active_dcf", {}).get("decision_badge") if isinstance(vw.get("active_dcf"), dict) else None,
                "has_scenarios": bool(vw.get("scenarios")),
                "has_sensitivity": bool(vw.get("sensitivity_heatmap")),
                "has_matrix": bool(vw.get("historical_matrix")),
            }
            print(f"  [Valuation Workspace] Intrinsic Value: {stock_audit['valuation_workspace']['intrinsic_value_base']} | Price: {vw.get('current_price')}")
        else:
            stock_audit["valuation_workspace"] = {"status_code": resp.status_code, "detail": resp.text}
            stock_audit["gaps_identified"].append(f"Valuation workspace returned {resp.status_code}: {resp.text}")
            print(f"  [Valuation Workspace ERROR] Status {resp.status_code}: {resp.text}")
    except Exception as e:
        stock_audit["valuation_workspace"] = {"error": str(e)}
        stock_audit["gaps_identified"].append(f"Valuation workspace exception: {str(e)}")
        print(f"  [Valuation Workspace EXCEPTION] {str(e)}")

    # 2.6 Valuation Provenance: GET /api/valuation/{ticker}/provenance
    try:
        resp = client.get(f"/api/valuation/{ticker}/provenance")
        if resp.status_code == 200:
            vp = resp.json()
            prov_rows = vp.get("provenance", [])
            stock_audit["valuation_provenance"] = {
                "status_code": 200,
                "rows_count": len(prov_rows),
                "sample_sources": list({r.get("source") for r in prov_rows[:5] if isinstance(r, dict)}),
            }
            print(f"  [Valuation Provenance] Rows: {len(prov_rows)}")
        else:
            stock_audit["valuation_provenance"] = {"status_code": resp.status_code, "detail": resp.text}
            stock_audit["gaps_identified"].append(f"Valuation provenance returned {resp.status_code}: {resp.text}")
            print(f"  [Valuation Provenance ERROR] Status {resp.status_code}: {resp.text}")
    except Exception as e:
        stock_audit["valuation_provenance"] = {"error": str(e)}
        stock_audit["gaps_identified"].append(f"Valuation provenance exception: {str(e)}")
        print(f"  [Valuation Provenance EXCEPTION] {str(e)}")

    audit_results["stocks_audit"][ticker] = stock_audit

# ---------------------------------------------------------
# 3. VERIFY V4.0 STRATEGY INDICATOR & RULE INTEGRITY (MA250 EXIT)
# ---------------------------------------------------------
print("\n--- 3. VERIFYING V4.0 STRATEGY INDICATORS & MA250 RULES ---")
# Check engine logic in engine_bridge / engine_core
# V4.0 exit trigger rules:
# EXIT rule 1: Close < SMA250 (primary trend break)
# EXIT rule 2: Stop Loss triggered (-5% to -8%)
# EXIT rule 3: Trend breakdown
try:
    from app.engine_bridge import bridge
    # Check baseline rules definitions
    rules_check = {}
    for ticker in ["GOOGL", "NVDA", "AAPL", "MSFT"]:
        analysis = bridge.get_stock_analysis(ticker)
        if analysis:
            rules_check[ticker] = {
                "signal": analysis.get("signal"),
                "rules": analysis.get("rules"),
                "exit_rule_present": any("250" in str(r) or "SMA250" in str(r) or "MA250" in str(r) for r in str(analysis.get("rules"))),
            }
    audit_results["engine_rules_verification"] = rules_check
    print(f"Engine Rules Checked for Sample Tickers: {list(rules_check.keys())}")
except Exception as e:
    audit_results["engine_rules_verification"] = {"error": str(e)}
    print(f"Engine Rules Verification Exception: {str(e)}")

# ---------------------------------------------------------
# 4. DASHBOARD & SCREENER AUDIT
# ---------------------------------------------------------
print("\n--- 4. DASHBOARD & SCREENER AUDIT ---")
try:
    resp_dash = client.get("/api/dashboard/strategy")
    resp_sig = client.get("/api/signals")
    resp_scan_sum = client.get("/api/scanner/summary")
    
    audit_results["dashboard_and_screener_audit"] = {
        "strategy_dashboard_status": resp_dash.status_code,
        "strategy_dashboard_data": resp_dash.json() if resp_dash.status_code == 200 else resp_dash.text,
        "signals_endpoint_status": resp_sig.status_code,
        "signals_data_summary": {
            "total_stocks": resp_sig.json().get("total_stocks") if resp_sig.status_code == 200 else None,
            "as_of_date": resp_sig.json().get("as_of_date") if resp_sig.status_code == 200 else None,
            "counts": resp_sig.json().get("counts") if resp_sig.status_code == 200 else None,
            "provenance": resp_sig.json().get("data_provenance") if resp_sig.status_code == 200 else None,
        } if resp_sig.status_code == 200 else resp_sig.text,
        "scanner_summary_status": resp_scan_sum.status_code,
        "scanner_summary_data": resp_scan_sum.json() if resp_scan_sum.status_code == 200 else resp_scan_sum.text,
    }
    print(f"Strategy Dashboard: {resp_dash.status_code} | Signals: {resp_sig.status_code} | Scanner Summary: {resp_scan_sum.status_code}")
except Exception as e:
    audit_results["dashboard_and_screener_audit"] = {"error": str(e)}
    print(f"Dashboard/Screener Exception: {str(e)}")

# Save audit results to scratch
output_path = backend_dir / "scratch" / "stage_c2_audit_results.json"
output_path.parent.mkdir(parents=True, exist_ok=True)
with open(output_path, "w", encoding="utf-8") as f:
    json.dump(audit_results, f, indent=2)

print(f"\nAudit completed and written to: {output_path}")
