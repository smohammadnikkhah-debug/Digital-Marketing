import sys
from pathlib import Path
backend_dir = Path(r"c:\Users\zeiva\OneDrive\Desktop\Project\Digital Marketing\stockanalysis\web_app\backend")
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.services.sec_edgar import sec_edgar_adapter
facts = sec_edgar_adapter.get_company_facts("AAPL")
us_gaap = facts.get("facts", {}).get("us-gaap", {})
concepts = ["RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues", "SalesRevenueNet", "SalesRevenueServicesGross"]
for c in concepts:
    if c in us_gaap:
        items = us_gaap[c].get("units", {}).get("USD", [])
        fy2020 = [it for it in items if it.get("fy") == 2020 and it.get("form") in ("10-K", "10-K/A") and it.get("fp") == "FY"]
        print(f"{c}: count={len(fy2020)}")
        for it in fy2020:
            print(f"   val={it.get('val'):,} | filed={it.get('filed')} | form={it.get('form')} | frame={it.get('frame')}")
