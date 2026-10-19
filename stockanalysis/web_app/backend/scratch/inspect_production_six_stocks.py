import urllib.request
import urllib.error
import json
from pathlib import Path

headers = {"User-Agent": "Audit/1.0"}
stocks = ["SPY", "AAPL", "MSFT", "GOOGL", "NVDA", "QCOM"]

results = {}

for ticker in stocks:
    print(f"\n==================== {ticker} ====================")
    r = {}
    
    # Technical
    try:
        url = f"https://mozarex.com/stockanalysis/api/stocks/{ticker}"
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=12) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            bars = data.get("bars", [])
            lb = bars[-1] if bars else {}
            r["technical"] = {
                "status": "AVAILABLE",
                "signal": data.get("signal"),
                "latest_price": data.get("latest_price"),
                "as_of": data.get("as_of"),
                "selected_entry": data.get("selected_entry"),
                "selected_exit": data.get("selected_exit"),
                "explanation": data.get("explanation"),
                "shariah_status": data.get("shariah_status"),
                "indicators": {
                    "ma30": lb.get("ma30"),
                    "ma50": lb.get("ma50"),
                    "ma250": lb.get("ma250"),
                    "roc20": lb.get("roc20"),
                    "atr14": lb.get("atr14"),
                }
            }
            print(f"TECH: Signal={data.get('signal')} | Price=${data.get('latest_price')} | AsOf={data.get('as_of')}")
            print(f"      Entry={data.get('selected_entry')} | Exit={data.get('selected_exit')}")
            print(f"      MA30={lb.get('ma30')} | MA50={lb.get('ma50')} | MA250={lb.get('ma250')} | ROC20={lb.get('roc20')}% | ATR14={lb.get('atr14')}")
    except Exception as e:
        r["technical"] = {"status": "ERROR", "error": str(e)}
        print(f"TECH ERROR: {e}")

    # Overview
    try:
        url = f"https://mozarex.com/stockanalysis/api/research/{ticker}/overview"
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=12) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            prof = data.get("profile", {})
            val = data.get("valuation", {})
            cf = data.get("cash_flow", {})
            r["overview"] = {
                "status": "AVAILABLE",
                "name": prof.get("name"),
                "is_sec_verified": prof.get("is_sec_verified"),
                "sec_cik": prof.get("sec_cik"),
                "latest_sec_filing_date": prof.get("latest_sec_filing_date"),
                "pe_formatted": val.get("trailing_pe", {}).get("formatted"),
                "market_cap_formatted": val.get("market_cap", {}).get("formatted"),
                "fcf_formatted": cf.get("free_cash_flow", {}).get("formatted"),
            }
            print(f"OVERVIEW: Name={prof.get('name')} | SEC_Verified={prof.get('is_sec_verified')} | FilingDate={prof.get('latest_sec_filing_date')}")
            print(f"          PE={val.get('trailing_pe', {}).get('formatted')} | MktCap={val.get('market_cap', {}).get('formatted')} | FCF={cf.get('free_cash_flow', {}).get('formatted')}")
    except Exception as e:
        r["overview"] = {"status": "ERROR", "error": str(e)}
        print(f"OVERVIEW ERROR: {e}")

    # Valuation
    try:
        url = f"https://mozarex.com/stockanalysis/api/valuation/{ticker}/workspace"
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=12) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            q = data.get("quote", {})
            dcf = data.get("active_dcf", {})
            mos = data.get("margin_of_safety", {})
            r["valuation"] = {
                "status": "AVAILABLE",
                "current_price": q.get("current_price"),
                "fair_value": dcf.get("fair_value_per_share"),
                "target_entry_price": dcf.get("target_entry_price"),
                "margin_of_safety_pct": mos.get("current_margin_of_safety_pct"),
                "recommendation": mos.get("recommendation"),
            }
            print(f"VALUATION: Price=${q.get('current_price')} | FV=${dcf.get('fair_value_per_share')} | TargetEntry=${dcf.get('target_entry_price')}")
            print(f"           MoS={mos.get('current_margin_of_safety_pct')}% | Rec={mos.get('recommendation')}")
    except Exception as e:
        r["valuation"] = {"status": "ERROR", "error": str(e)}
        print(f"VALUATION ERROR: {e}")

    results[ticker] = r

out_file = Path(r"c:\Users\zeiva\OneDrive\Desktop\Project\Digital Marketing\stockanalysis\web_app\backend\scratch\prod_inspection_results.json")
with open(out_file, "w", encoding="utf-8") as f:
    json.dump(results, f, indent=2)

print(f"\nInspection saved to {out_file}")
