"""One-off timing bench for D2.4L scanner diagnosis (local)."""
from __future__ import annotations

import sys
import time
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.services.scanner_service import scanner_service  # noqa: E402


def main() -> None:
    tickers = ["AAPL", "MSFT", "KMI", "PYPL", "ROST"]
    rows = []
    for t in tickers:
        t0 = time.perf_counter()
        df, _stale = scanner_service.fetch_or_update_stock(t, force_full=False)
        t_price = time.perf_counter() - t0
        if df is None or getattr(df, "empty", True):
            print(f"{t}: NO_DATA prices={t_price:.2f}s", flush=True)
            continue
        import engine as v41

        t1 = time.perf_counter()
        d = v41.prep(df)
        t_prep = time.perf_counter() - t1
        t2 = time.perf_counter()
        win = scanner_service.optimize_v40_rule(d, d.index[-1])
        t_opt = time.perf_counter() - t2
        t4 = time.perf_counter()
        sig = scanner_service.evaluate_stock_signal(t, df)
        t_eval = time.perf_counter() - t4
        total = time.perf_counter() - t0
        entry = (win or {}).get("entry")
        rows.append((t, t_price, t_prep, t_opt, t_eval, total))
        print(
            f"{t}: prices={t_price:.2f}s prep={t_prep:.2f}s optimize={t_opt:.2f}s "
            f"evaluate_full={t_eval:.2f}s wall={total:.2f}s entry={entry} "
            f"sig={sig.get('signal')}",
            flush=True,
        )
    if not rows:
        return
    avg_opt = sum(r[3] for r in rows) / len(rows)
    avg_eval = sum(r[4] for r in rows) / len(rows)
    print("---", flush=True)
    print(f"avg_optimize={avg_opt:.2f}s avg_evaluate_full={avg_eval:.2f}s", flush=True)
    print(f"est_230_optimize_min={avg_opt * 230 / 60:.1f}", flush=True)
    print(f"est_230_full_eval_min={avg_eval * 230 / 60:.1f}", flush=True)
    # Second pass: evaluate again (shows re-train cost if no cache)
    t = "AAPL"
    t0 = time.perf_counter()
    df = scanner_service.get_price_df(t)
    scanner_service.evaluate_stock_signal(t, df)
    print(f"second_eval_{t}={time.perf_counter() - t0:.2f}s (no cache)", flush=True)


if __name__ == "__main__":
    main()
