import sys
from pathlib import Path
backend_dir = Path(r"c:\Users\zeiva\OneDrive\Desktop\Project\Digital Marketing\stockanalysis\web_app\backend")
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.services.sec_edgar import sec_edgar_adapter
from app.services.financial_data import financial_data_service
from app.services.valuation import valuation_service

print("=" * 60)
print("1. INVESTIGATING AAPL REVENUE CAGR")
print("=" * 60)

facts = sec_edgar_adapter.get_company_facts("AAPL")
us_gaap = facts.get("facts", {}).get("us-gaap", {})

def get_annual_sec(concepts, unit="USD"):
    by_fy = {}
    for c in concepts:
        if c in us_gaap:
            items = us_gaap[c].get("units", {}).get(unit, [])
            for it in items:
                if it.get("form") in ("10-K", "10-K/A") and it.get("fp") == "FY" and it.get("fy") and it.get("val") is not None:
                    by_fy[int(it["fy"])] = float(it["val"])
    return by_fy

revs = get_annual_sec(["RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues", "SalesRevenueNet"])
print("AAPL Raw Revenues by Fiscal Year:")
for y in sorted(revs.keys()):
    print(f"  FY{y}: ${revs[y]:,.2f}")

fys = sorted(revs.keys())
latest_fy = fys[-1]
print(f"\nLatest FY: {latest_fy} (${revs[latest_fy]:,.2f})")
print(f"FY - 1: {fys[-2]} (${revs[fys[-2]]:,.2f}) -> Growth: {((revs[latest_fy] - revs[fys[-2]]) / revs[fys[-2]] * 100):.2f}%")
print(f"fys[-6]: {fys[-6]} (${revs[fys[-6]]:,.2f})")
cagr_5y = ((revs[latest_fy] / revs[fys[-6]]) ** (1.0 / 5.0) - 1.0) * 100.0
print(f"5Y CAGR (FY{fys[-6]} to FY{latest_fy}): {cagr_5y:.2f}%")
print(f"fys[-11]: {fys[-11]} (${revs[fys[-11]]:,.2f})")
cagr_10y = ((revs[latest_fy] / revs[fys[-11]]) ** (1.0 / 10.0) - 1.0) * 100.0
print(f"10Y CAGR (FY{fys[-11]} to FY{latest_fy}): {cagr_10y:.2f}%")

print("\n=" * 60)
print("2. INVESTIGATING GOOGL NET CASH & SIGN ARITHMETIC")
print("=" * 60)

googl_ov = financial_data_service.get_company_overview("GOOGL")
bs = googl_ov.get("balance_sheet", {})
cf = googl_ov.get("cash_flow", {})
val = googl_ov.get("valuation", {})
mg = googl_ov.get("margins_and_growth", {})
risk = financial_data_service.get_stock_risk_assessment("GOOGL")
fin_risk = risk.get("sections", {}).get("financial_risk", {}) if risk else {}

print("Balance Sheet Panel:")
for k, v in bs.items():
    if isinstance(v, dict):
        print(f"  {k}: value={v.get('value')} | formatted={v.get('formatted')}")

print("\nFinancial Risk Assessment Panel:")
for k, v in fin_risk.items():
    print(f"  {k}: {v}")

print("\nValuation Workspace EV to Equity Bridge:")
vw_googl = valuation_service.get_full_workspace("GOOGL")
for step in vw_googl.get("active_dcf", {}).get("bridge_steps", []):
    print(f"  {step.get('step')}: {step.get('formatted_amount')} ({step.get('description')})")
