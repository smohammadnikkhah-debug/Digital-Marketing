"""Read-only D2.5 evidence extraction. Does not modify production data."""
from __future__ import annotations

import json
import sqlite3
from collections import Counter
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
EVIDENCE = BACKEND / "data_cache" / "evidence"
DB = BACKEND / "adaptive_platform.db"
OUT = BACKEND / "scratch" / "_tmp_d2_5_extract_out.json"


def load_bundle(name: str) -> dict:
    p = EVIDENCE / name / "session_bundle.json"
    return json.loads(p.read_text(encoding="utf-8"))


def summarize_candidate(c) -> dict:
    if isinstance(c, str):
        return {"ticker": c, "_all_keys": ["ticker"]}
    if not isinstance(c, dict):
        return {"raw": repr(c), "_all_keys": []}
    sig = c.get("signal") if isinstance(c.get("signal"), dict) else c
    keys_of_interest = [
        "ticker", "signal", "price", "close", "last_price", "entry_price",
        "stop_loss", "stop", "target", "risk_reward", "rr", "holding_period",
        "expected_holding_days", "avg_holding_days", "entry_rule", "entry_condition",
        "rationale", "reason", "reason_codes", "score", "train_sharpe",
        "train_win_rate", "oos_sharpe", "oos_return", "win_rate", "profit_factor",
        "market_as_of", "market_as_of_date", "strategy_version", "sector",
        "user_policy_status", "shariah_status", "investment_classification",
        "classification", "proposed_quantity", "proposed_limit_price",
    ]
    out = {}
    for k in keys_of_interest:
        if k in sig and sig[k] is not None:
            out[k] = sig[k]
        elif k in c and c[k] is not None:
            out[k] = c[k]
    # keep nested decision/proposal snippets small
    for nest in ("decision", "details", "ranking", "performance"):
        if nest in c and c[nest] is not None:
            out[nest] = c[nest]
    out["_all_keys"] = sorted(set(list(sig.keys()) + list(c.keys())))
    return out


def main() -> None:
    latest_pc = "d2_4l_20261028T203002Z"
    ns_runs = [
        "d2_4l_20261027T134503Z",
        "d2_4l_20261028T134502Z",
    ]
    pc = load_bundle(latest_pc)

    # Signal distribution
    signals = pc.get("signals") or []
    dist = Counter()
    for s in signals:
        if isinstance(s, dict):
            dist[str(s.get("signal") or s.get("status") or "UNKNOWN")] += 1
        else:
            dist["NON_DICT"] += 1

    # Buy candidates detail
    buy_cands = pc.get("buy_candidates") or []
    buy_summaries = [summarize_candidate(c) for c in buy_cands]

    # Policy excluded buy candidates
    by_pol = pc.get("buy_candidates_by_policy") or {}
    excluded = by_pol.get("EXCLUDED") or []
    review = by_pol.get("REVIEW REQUIRED") or []
    allowed = by_pol.get("ALLOWED") or []

    # Also collect USER_POLICY rejections from signals if present
    policy_rejects = []
    for s in signals:
        if not isinstance(s, dict):
            continue
        ups = str(s.get("user_policy_status") or "").upper()
        if ups in ("EXCLUDED", "REVIEW REQUIRED", "BLOCKED"):
            policy_rejects.append({
                "ticker": s.get("ticker"),
                "signal": s.get("signal"),
                "user_policy_status": s.get("user_policy_status"),
                "user_policy_reason": s.get("user_policy_reason") or s.get("policy_reason") or s.get("reason_codes"),
                "sector": s.get("sector"),
                "industry": s.get("industry"),
            })

    # Freshness / data quality
    freshness = pc.get("freshness") or {}
    scan = pc.get("scan_summary") or {}

    # Proposals from next_session runs
    proposals_by_run = {}
    perf_by_run = {}
    for run in ns_runs:
        b = load_bundle(run)
        props = b.get("simulated_proposals") or []
        proposals_by_run[run] = []
        for p in props:
            proposals_by_run[run].append({
                "ticker": p.get("ticker") or (p.get("proposal") or {}).get("symbol"),
                "proposal": p.get("proposal") or {k: p.get(k) for k in (
                    "symbol", "action", "order_type", "quantity", "limit_price",
                    "currency", "broker", "account_id", "notes"
                ) if k in p},
                "decision": p.get("decision"),
                "investment_classification": p.get("investment_classification"),
                "execution_readiness": p.get("execution_readiness"),
                "ranking": p.get("ranking"),
                "reason_codes": p.get("reason_codes"),
                "_keys": sorted(p.keys()),
            })
        perf_by_run[run] = b.get("performance") or []

    # Sample signal keys from first buy candidate
    sample_keys = buy_summaries[0]["_all_keys"] if buy_summaries else []

    # DB query
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(
        "SELECT ticker, latest_signal_json FROM monitored_stocks "
        "WHERE is_active=1 AND json_extract(latest_signal_json,'$.signal')='BUY CANDIDATE' "
        "ORDER BY ticker"
    )
    db_buys = []
    for row in cur.fetchall():
        sig = json.loads(row["latest_signal_json"])
        db_buys.append(summarize_candidate(sig))
    cur.execute(
        "SELECT COUNT(*) FROM monitored_stocks WHERE is_active=1"
    )
    active = cur.fetchone()[0]
    cur.execute(
        "SELECT json_extract(latest_signal_json,'$.signal') AS sig, COUNT(*) c "
        "FROM monitored_stocks WHERE is_active=1 GROUP BY sig ORDER BY c DESC"
    )
    db_dist = [(r["sig"], r["c"]) for r in cur.fetchall()]
    cur.execute("SELECT COUNT(*) FROM backtest_runs")
    backtest_runs = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM paper_orders")
    paper_orders = cur.fetchone()[0]
    # snapshot
    try:
        cur.execute(
            "SELECT id, market_as_of_date, buy_candidates_count, total_stocks, created_at "
            "FROM screener_snapshots WHERE is_active=1"
        )
        snap = dict(cur.fetchone() or {})
    except Exception as e:
        snap = {"error": str(e)}
    conn.close()

    # USER_POLICY evidence files
    up_dir = BACKEND / "data_cache" / "user_policy"
    up_files = sorted(p.name for p in up_dir.glob("*")) if up_dir.exists() else []

    result = {
        "latest_post_close": latest_pc,
        "trading_day": pc.get("trading_day"),
        "freshness": freshness,
        "scan_summary": scan,
        "signal_distribution_bundle": dict(dist),
        "policy_eligibility_breakdown": pc.get("policy_eligibility_breakdown"),
        "buy_candidates_count": len(buy_cands),
        "buy_candidates_by_policy_counts": {
            k: len(v) if isinstance(v, list) else v for k, v in by_pol.items()
        },
        "buy_candidates": buy_summaries,
        "excluded_buy_candidates": [summarize_candidate(c) for c in excluded],
        "review_buy_candidates": [summarize_candidate(c) for c in review],
        "allowed_buy_candidates": [summarize_candidate(c) for c in allowed],
        "policy_rejects_from_signals_count": len(policy_rejects),
        "policy_rejects_sample": policy_rejects[:40],
        "proposals_by_run": proposals_by_run,
        "perf_by_run": perf_by_run,
        "sample_buy_keys": sample_keys,
        "db": {
            "active": active,
            "signal_dist": db_dist,
            "buy_candidates": db_buys,
            "backtest_runs": backtest_runs,
            "paper_orders": paper_orders,
            "active_snapshot": snap,
        },
        "user_policy_files": up_files[:50],
    }
    OUT.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    print(f"Wrote {OUT}")
    print("buy_candidates", len(buy_summaries))
    print("sample_keys", sample_keys[:60])
    print("db_buys", len(db_buys), "active", active)
    print("proposals", {k: len(v) for k, v in proposals_by_run.items()})


if __name__ == "__main__":
    main()
