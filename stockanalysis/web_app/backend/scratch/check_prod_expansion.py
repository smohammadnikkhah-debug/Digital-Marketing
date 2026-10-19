import urllib.request
import json

headers = {"User-Agent": "Audit/1.0"}
targets = ["NEWIPO", "ADBE", "CRM", "PANW", "PLTR"]

print("=== CHECKING PRODUCTION UNIVERSE FOR 5 EXPANSION STOCKS ===")
for t in targets:
    url = f"https://mozarex.com/stockanalysis/api/scanner/universe?search={t}"
    try:
        r = urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=10)
        data = json.loads(r.read())
        stocks = data.get("stocks", [])
        found = [s for s in stocks if s.get("ticker") == t]
        if found:
            st = found[0]
            print(f"PROD FOUND {t}: name='{st.get('name')}', sector='{st.get('sector')}', status='{st.get('data_status')}', signal='{st.get('signal')}', source='{st.get('source')}'")
        else:
            print(f"PROD NOT FOUND: {t}")
    except Exception as e:
        print(f"PROD ERROR {t}: {e}")
