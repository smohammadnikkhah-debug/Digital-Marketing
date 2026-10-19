import sys
from pathlib import Path
backend_dir = Path(r"c:\Users\zeiva\OneDrive\Desktop\Project\Digital Marketing\stockanalysis\web_app\backend")
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.services.valuation import valuation_service

for t in ['GOOGL', 'AAPL', 'MSFT', 'NVDA', 'QCOM']:
    try:
        m = valuation_service.get_historical_matrix(t)
        print(f"{t}: Years={m.get('fiscal_years')} | Rows={len(m.get('rows', []))}")
        for r in m.get('rows', [])[:4]:
            print(f"   {r.get('label')}: Latest={r.get('latest_fy_formatted')}, 5Y={r.get('hist_5y_formatted')}, 10Y={r.get('hist_10y_formatted')}")
    except Exception as e:
        print(f"{t} Matrix error: {e}")
