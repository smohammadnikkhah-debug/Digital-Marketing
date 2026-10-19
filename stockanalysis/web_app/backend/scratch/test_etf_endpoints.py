import sys
from pathlib import Path
backend_dir = Path(r"c:\Users\zeiva\OneDrive\Desktop\Project\Digital Marketing\stockanalysis\web_app\backend")
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

for ticker in ["SPY", "QQQ"]:
    print(f"\n=================== TESTING ETF: {ticker} ===================")
    endpoints = [
        f"/api/stocks/{ticker}",
        f"/api/research/{ticker}/overview",
        f"/api/research/{ticker}/financial-history?frequency=quarterly&range=5y",
        f"/api/research/{ticker}/price-history?interval=daily&range=5y",
        f"/api/research/{ticker}/risk",
        f"/api/valuation/{ticker}/workspace",
        f"/api/valuation/{ticker}/matrix",
        f"/api/valuation/{ticker}/provenance",
        f"/api/valuation/{ticker}/defaults",
        f"/api/valuation/{ticker}/peers",
    ]
    for ep in endpoints:
        resp = client.get(ep)
        detail = ""
        if resp.status_code != 200:
            try:
                detail = resp.json().get("detail", resp.text[:100])
            except Exception:
                detail = resp.text[:100]
        print(f"  {ep.split('?')[0]:<35} -> {resp.status_code} {detail}")
