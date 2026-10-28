"""Investigate D2.4L STALE_MIXED for a completed post-close evidence run."""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.config import DATA_CACHE_DIR, V40_STRATEGY_VERSION  # noqa: E402
from app.services.observation_freshness import assess_scan_freshness  # noqa: E402
from app.services.ticker_integrity import (  # noqa: E402
    PROPOSED_TICKER_ALIASES,
    investigate_problem_tickers,
    resolve_proposed_alias,
)
from app.services.us_session_freshness import parse_market_as_of  # noqa: E402

RUN = DATA_CACHE_DIR / "evidence" / "d2_4l_20261026T233205Z"
EXPECTED = date(2026, 10, 26)


def main() -> int:
    rows = json.loads((RUN / "scan_rows.json").read_text(encoding="utf-8"))
    post = json.loads((RUN / "d2_4l_post_close.json").read_text(encoding="utf-8"))
    bundle = json.loads((RUN / "session_bundle.json").read_text(encoding="utf-8"))

    print("=== RUN META ===")
    print("run_id", post.get("run_id"))
    print("trading_day", post.get("trading_day_et"))
    print("freshness_status", (post.get("freshness") or {}).get("status"))
    print("freshness_reason", (post.get("freshness") or {}).get("reason_code"))
    print("expected_session", (post.get("freshness") or {}).get("expected_session"))
    print("as_of_distribution", (post.get("freshness") or {}).get("as_of_distribution"))
    print("matching", (post.get("freshness") or {}).get("matching_expected_count"))
    print("evaluable", (post.get("freshness") or {}).get("evaluable_count"))
    print("data_freshness_counts", (post.get("freshness") or {}).get("data_freshness_counts"))
    print("universe", post.get("universe_count"), "scanned", post.get("successfully_scanned"))
    print("signal_dist", post.get("signal_distribution"))
    print("soak", (post.get("soak_status") or {}).get("observed_completed_pairs"))

    # Recompute freshness for verification
    recomputed = assess_scan_freshness(rows, expected_session=EXPECTED)
    print("\n=== RECOMPUTED FRESHNESS ===")
    print(json.dumps({k: recomputed[k] for k in (
        "status", "reason_code", "expected_session", "as_of_distribution",
        "matching_expected_count", "evaluable_count", "coverage_pct_matching_expected",
        "data_freshness_counts",
    )}, indent=2))

    # Classify rows
    by_asof = defaultdict(list)
    by_dfresh = Counter()
    by_signal = Counter()
    no_asof = []
    matching = []
    stale = []
    insufficient = []
    for r in rows:
        t = r.get("ticker")
        sig = str(r.get("signal") or "")
        dfresh = str(r.get("data_freshness") or "UNKNOWN")
        by_dfresh[dfresh] += 1
        by_signal[sig] += 1
        as_of = parse_market_as_of(r.get("market_as_of_date") or r.get("as_of"))
        if sig == "INSUFFICIENT DATA" or dfresh == "INSUFFICIENT_DATA":
            insufficient.append(r)
        if as_of is None:
            no_asof.append(r)
        else:
            by_asof[as_of.isoformat()].append(t)
            if as_of == EXPECTED:
                matching.append(r)
            elif as_of < EXPECTED:
                stale.append(r)

    print("\n=== COUNTS ===")
    print("rows", len(rows))
    print("as_of_match_expected_FRESH_bars", len(matching))
    print("as_of_behind_STALE_bars", len(stale))
    print("no_as_of", len(no_asof))
    print("insufficient_signal_or_freshness", len(insufficient))
    print("data_freshness field", dict(by_dfresh))
    print("signals", dict(by_signal))
    print("as_of buckets", {k: len(v) for k, v in sorted(by_asof.items())})

    print("\n=== STALE SYMBOLS (as_of < 2026-10-26) ===")
    stale_detail = []
    for r in sorted(stale, key=lambda x: (str(x.get("as_of")), str(x.get("ticker")))):
        stale_detail.append(
            {
                "ticker": r.get("ticker"),
                "as_of": r.get("market_as_of_date") or r.get("as_of"),
                "data_freshness": r.get("data_freshness"),
                "signal": r.get("signal"),
                "refresh_status": r.get("refresh_status"),
                "validation_status": r.get("validation_status"),
            }
        )
        print(
            f"  {r.get('ticker')}: as_of={r.get('market_as_of_date') or r.get('as_of')} "
            f"dfresh={r.get('data_freshness')} sig={r.get('signal')} "
            f"refresh={r.get('refresh_status')}"
        )

    print("\n=== INSUFFICIENT ===")
    for r in insufficient:
        print(
            f"  {r.get('ticker')}: as_of={r.get('market_as_of_date') or r.get('as_of')} "
            f"dfresh={r.get('data_freshness')} validation={r.get('validation_status')} "
            f"refresh={r.get('refresh_status')}"
        )

    # BUY candidates freshness
    buys = [
        r for r in rows
        if str(r.get("signal") or "").upper() in ("BUY CANDIDATE", "BUY")
    ]
    buy_stale = []
    buy_fresh = []
    buy_other = []
    for r in buys:
        as_of = parse_market_as_of(r.get("market_as_of_date") or r.get("as_of"))
        if as_of == EXPECTED:
            buy_fresh.append(r.get("ticker"))
        elif as_of is not None and as_of < EXPECTED:
            buy_stale.append((r.get("ticker"), str(as_of)))
        else:
            buy_other.append(r.get("ticker"))
    print("\n=== BUY CANDIDATES ===")
    print("total", len(buys))
    print("fresh_as_of", len(buy_fresh))
    print("stale_as_of", buy_stale)
    print("other", buy_other)

    # Known symbols
    known = ["SQ", "XYZ", "MMC", "QUALCOMM", "QCOM"]
    print("\n=== KNOWN SYMBOLS IN SCAN ===")
    by_t = {str(r.get("ticker")).upper(): r for r in rows}
    for t in known:
        r = by_t.get(t)
        if not r:
            print(f"  {t}: NOT IN SCAN ROWS")
            continue
        print(
            f"  {t}: as_of={r.get('market_as_of_date') or r.get('as_of')} "
            f"dfresh={r.get('data_freshness')} sig={r.get('signal')} "
            f"refresh={r.get('refresh_status')} alias={resolve_proposed_alias(t)}"
        )

    # Price cache last dates for stale + known
    print("\n=== PRICE CACHE LAST DATES (stale + known) ===")
    cache_dir = DATA_CACHE_DIR / "price_cache"
    check = sorted({r.get("ticker") for r in stale} | set(known))
    for t in check:
        p = cache_dir / f"{t}.csv"
        if not p.exists():
            print(f"  {t}: NO_CACHE_FILE")
            continue
        import pandas as pd

        df = pd.read_csv(p)
        last = str(df.iloc[-1].get("Date")) if len(df) else None
        print(f"  {t}: cache_rows={len(df)} last={last}")

    # Integrity proposal (no writes)
    yahoo_bars = {}
    for t in known:
        p = cache_dir / f"{t}.csv"
        if p.exists():
            import pandas as pd
            df = pd.read_csv(p)
            yahoo_bars[t] = len(df)
        else:
            yahoo_bars[t] = 0
    inv = investigate_problem_tickers(
        universe_tickers=list(by_t),
        registry_records={t: {"name": (by_t.get(t) or {}).get("name")} for t in known},
        yahoo_bars=yahoo_bars,
        alpaca_quote_ok={},
    )
    print("\n=== TICKER INTEGRITY (proposal only) ===")
    print(json.dumps(inv, indent=2, default=str)[:4000])

    # Can we regenerate legitimately?
    # Strict: soak eligibility requires aggregate FRESH. STALE_MIXED cannot be
    # reclassified. Options: wait for next session, or re-run post-close after
    # fixing symbol data IF bars for 2026-10-26 become available for stale names.
    print("\n=== REGENERATION VERDICT ===")
    n_stale = len(stale)
    n_insuff = len(insufficient)
    print(
        json.dumps(
            {
                "can_mark_run_FRESH_without_data_change": False,
                "reason": "Strict freshness: matching < evaluable → STALE_MIXED",
                "stale_ticker_count": n_stale,
                "insufficient_count": n_insuff,
                "fresh_evaluable_count": len(matching),
                "legitimate_regenerate_same_session_if": (
                    "Re-fetch Yahoo for stale/insufficient symbols and confirm "
                    "their cache last date is 2026-10-26, then re-run post-close "
                    "--fresh for the same trading day. Only legitimate if those "
                    "bars truly exist (delisted/renamed symbols may never be FRESH)."
                ),
                "must_wait_next_session_if": (
                    "Stale symbols cannot obtain 2026-10-26 bars (bad ticker / "
                    "delisted / provider gap). Then abandon this pair's eligibility "
                    "and start the next trading day's post-close."
                ),
                "pair_not_counted": True,
                "proposed_aliases": dict(PROPOSED_TICKER_ALIASES),
            },
            indent=2,
        )
    )

    out = RUN / "freshness_investigation.json"
    out.write_text(
        json.dumps(
            {
                "stale_detail": stale_detail,
                "insufficient_tickers": [r.get("ticker") for r in insufficient],
                "buy_stale": buy_stale,
                "buy_fresh_count": len(buy_fresh),
                "recomputed": recomputed,
                "integrity": inv,
            },
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )
    print("\nWrote", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
