import sys
from pathlib import Path
backend_dir = Path(r"c:\Users\zeiva\OneDrive\Desktop\Project\Digital Marketing\stockanalysis\web_app\backend")
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.services.valuation import valuation_service

for ticker in ['GOOGL', 'AAPL', 'MSFT', 'NVDA', 'QCOM', 'SPY']:
    print("=" * 20, ticker, "=" * 20)
    try:
        vw = valuation_service.get_full_workspace(ticker)
        q = vw["quote"]
        dcf = vw["active_dcf"]
        mos = vw["margin_of_safety"]
        wacc = dcf.get("wacc_pct")
        print(f"Company: {q.get('company_name')} ({q.get('exchange')})")
        print(f"Price: ${q.get('current_price')} (As of {q.get('price_date')})")
        print(f"Fair Value (DCF): ${dcf.get('fair_value_per_share'):.2f}")
        print(f"Target Entry (12% hurdle): ${dcf.get('target_entry_price'):.2f}")
        print(f"WACC: {wacc:.2f}% | Terminal Growth: {dcf.get('terminal_growth_rate') * 100:.2f}%")
        print(f"Margin of Safety: {mos.get('current_margin_of_safety_pct'):.2f}% -> Decision: {mos.get('recommendation')}")
        print(f"Scenarios: Bear=${vw['scenario_results']['bear']['fair_value_per_share']:.2f} | Base=${vw['scenario_results']['base']['fair_value_per_share']:.2f} | Bull=${vw['scenario_results']['bull']['fair_value_per_share']:.2f}")
        print(f"Provenance Rows: {len(vw['provenance_table'])} | Matrix Rows: {len(vw['historical_matrix']['rows'])}")
    except Exception as e:
        print(f"ERROR: {type(e).__name__}: {e}")
