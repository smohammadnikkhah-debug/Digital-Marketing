"""Detailed inspection of the 6 target stocks across all engines."""
import sys
from pathlib import Path
import json

backend_dir = Path(r"c:\Users\zeiva\OneDrive\Desktop\Project\Digital Marketing\stockanalysis\web_app\backend")
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.services.financial_data import financial_data_service
from app.services.valuation import valuation_service
from app.engine_bridge import bridge

stocks = ["SPY", "AAPL", "MSFT", "GOOGL", "NVDA", "QCOM"]

results = {}

for ticker in stocks:
    print(f"\n==================== {ticker} ====================")
    r = {}
    
    # 1. Technical Analysis
    tech = bridge.get_stock_analysis(ticker)
    if tech:
        bars = tech.get("bars", [])
        last_bar = bars[-1] if bars else {}
        r["technical"] = {
            "status": "AVAILABLE",
            "signal": tech.get("signal"),
            "latest_price": tech.get("latest_price"),
            "as_of": tech.get("as_of"),
            "selected_entry": tech.get("selected_entry"),
            "selected_exit": tech.get("selected_exit"),
            "explanation": tech.get("explanation"),
            "shariah_status": tech.get("shariah_status"),
            "bars_count": len(bars),
            "indicators": {
                "ma30": last_bar.get("ma30"),
                "ma50": last_bar.get("ma50"),
                "ma250": last_bar.get("ma250"),
                "roc20": last_bar.get("roc20"),
                "atr14": last_bar.get("atr14"),
            },
            "delayed_breakdown": tech.get("delayed_breakdown"),
            "stock_vs_bh_vs_spy": tech.get("stock_vs_bh_vs_spy"),
        }
        print(f"TECH: Signal={r['technical']['signal']} | Price=${r['technical']['latest_price']} | AsOf={r['technical']['as_of']}")
        print(f"      Entry={r['technical']['selected_entry']} | Exit={r['technical']['selected_exit']}")
        print(f"      MA30={last_bar.get('ma30')} | MA50={last_bar.get('ma50')} | MA250={last_bar.get('ma250')} | ROC20={last_bar.get('roc20')}% | ATR14={last_bar.get('atr14')}")
    else:
        r["technical"] = {"status": "NOT_AVAILABLE"}
        print("TECH: NOT AVAILABLE")

    # 2. Fundamental Overview
    try:
        fo = financial_data_service.get_company_overview(ticker)
        prof = fo.get("profile", {})
        val = fo.get("valuation", {})
        prof_panel = fo.get("profitability", {})
        cf = fo.get("cash_flow", {})
        bs = fo.get("balance_sheet", {})
        margins = fo.get("margins", {})
        divs = fo.get("dividends", {})
        
        r["fundamentals"] = {
            "status": "AVAILABLE",
            "is_sec_verified": prof.get("is_sec_verified"),
            "sec_cik": prof.get("sec_cik"),
            "latest_sec_filing_date": prof.get("latest_sec_filing_date"),
            "latest_sec_accession": prof.get("latest_sec_accession"),
            "currency": prof.get("currency"),
            "market_cap": val.get("market_cap", {}).get("formatted"),
            "trailing_pe": val.get("trailing_pe", {}).get("formatted"),
            "forward_pe": val.get("forward_pe", {}).get("formatted"),
            "revenue_ttm": prof_panel.get("revenue_ttm", {}).get("formatted"),
            "net_income_ttm": prof_panel.get("net_income_ttm", {}).get("formatted"),
            "operating_cash_flow": cf.get("operating_cash_flow_ttm", {}).get("formatted"),
            "free_cash_flow": cf.get("free_cash_flow_ttm", {}).get("formatted"),
            "total_cash": bs.get("cash_and_equivalents", {}).get("formatted"),
            "total_debt": bs.get("total_debt", {}).get("formatted"),
            "gross_margin": margins.get("gross_margin", {}).get("formatted"),
            "operating_margin": margins.get("operating_margin", {}).get("formatted"),
            "net_margin": margins.get("net_margin", {}).get("formatted"),
            "dividend_yield": divs.get("dividend_yield", {}).get("formatted"),
        }
        print(f"FUND: SEC_Verified={prof.get('is_sec_verified')} | FilingDate={prof.get('latest_sec_filing_date')} | CIK={prof.get('sec_cik')}")
        print(f"      Rev_TTM={r['fundamentals']['revenue_ttm']} | NetInc={r['fundamentals']['net_income_ttm']} | FCF={r['fundamentals']['free_cash_flow']}")
        print(f"      OpMargin={r['fundamentals']['operating_margin']} | P/E={r['fundamentals']['trailing_pe']} | MktCap={r['fundamentals']['market_cap']}")
    except Exception as e:
        r["fundamentals"] = {"status": "ERROR", "error": str(e)}
        print(f"FUND ERROR: {e}")

    # 3. Fundamental Chart Series (Annually & Quarterly)
    try:
        fh_a = financial_data_service.get_financial_chart_series(ticker, frequency="annually", time_range="5y")
        fh_q = financial_data_service.get_financial_chart_series(ticker, frequency="quarterly", time_range="5y")
        r["financial_series"] = {
            "status": "AVAILABLE",
            "annual_periods_count": len(fh_a.get("series", [])),
            "quarterly_periods_count": len(fh_q.get("series", [])),
            "annual_periods": [s.get("period") for s in fh_a.get("series", [])],
        }
        print(f"SERIES: Annual={r['financial_series']['annual_periods_count']} periods ({r['financial_series']['annual_periods']}) | Quarterly={r['financial_series']['quarterly_periods_count']} periods")
    except Exception as e:
        r["financial_series"] = {"status": "ERROR", "error": str(e)}
        print(f"SERIES ERROR: {e}")

    # 4. Risk Assessment
    try:
        risk = financial_data_service.get_stock_risk_assessment(ticker)
        r["risk"] = {
            "status": "AVAILABLE",
            "overall_score": risk.get("overall_risk_score"),
            "overall_level": risk.get("overall_risk_level"),
            "sections": {k: {"score": v.get("score"), "level": v.get("level")} for k, v in risk.get("sections", {}).items()},
        }
        print(f"RISK: Score={risk.get('overall_risk_score')}/100 ({risk.get('overall_risk_level')}) | Sections: {list(risk.get('sections', {}).keys())}")
    except Exception as e:
        r["risk"] = {"status": "ERROR", "error": str(e)}
        print(f"RISK ERROR: {e}")

    # 5. Valuation Workspace
    try:
        vw = valuation_service.get_full_workspace(ticker)
        scenarios = vw.get("scenario_results", {})
        base = scenarios.get("base", {})
        bear = scenarios.get("bear", {})
        bull = scenarios.get("bull", {})
        r["valuation"] = {
            "status": "AVAILABLE",
            "current_price": vw.get("current_price"),
            "base_iv": base.get("intrinsic_value_per_share"),
            "base_mos_pct": base.get("margin_of_safety_pct"),
            "base_decision": base.get("decision_badge"),
            "bear_iv": bear.get("intrinsic_value_per_share"),
            "bull_iv": bull.get("intrinsic_value_per_share"),
            "wacc": vw.get("wacc", {}).get("wacc_pct"),
            "cost_of_equity": vw.get("wacc", {}).get("cost_of_equity_pct"),
            "provenance_rows": len(vw.get("provenance", [])),
            "historical_matrix_rows": len(vw.get("historical_matrix", {}).get("rows", [])),
        }
        print(f"VALUATION: Price=${vw.get('current_price')} | Base IV=${base.get('intrinsic_value_per_share')} | MoS={base.get('margin_of_safety_pct')}% ({base.get('decision_badge')})")
        print(f"           Bear IV=${bear.get('intrinsic_value_per_share')} | Bull IV=${bull.get('intrinsic_value_per_share')} | WACC={vw.get('wacc', {}).get('wacc_pct')}%")
    except Exception as e:
        r["valuation"] = {"status": "ERROR", "error": str(e)}
        print(f"VALUATION ERROR: {e}")

    results[ticker] = r

with open(backend_dir / "scratch" / "six_stocks_inspection.json", "w", encoding="utf-8") as f:
    json.dump(results, f, indent=2)

print("\nSaved detailed inspection to scratch/six_stocks_inspection.json")
