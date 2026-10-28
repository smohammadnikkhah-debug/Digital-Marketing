"""Enrich D2.5 candidate/proposal tables from evidence + V40 excel (read-only)."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
EV = BACKEND / "data_cache" / "evidence"
OUT = BACKEND / "scratch" / "_tmp_d2_5_enrich_out.json"


def load(name: str) -> dict:
    return json.loads((EV / name / "session_bundle.json").read_text(encoding="utf-8"))


def main() -> None:
    pc = load("d2_4l_20261028T203002Z")
    by_ticker = {s["ticker"]: s for s in pc["signals"]}

    # Full buy candidate table
    rows = []
    for c in pc["buy_candidates"]:
        t = c["ticker"]
        s = by_ticker.get(t, {})
        rows.append({
            "ticker": t,
            "policy": c.get("policy"),
            "investment": c.get("investment"),
            "entry_rule": c.get("entry_rule") or s.get("entry_rule"),
            "exit_rule": s.get("exit_rule"),
            "close": s.get("close"),
            "signal_price": c.get("signal_price") or s.get("close"),
            "ma30": s.get("ma30"),
            "ma50": s.get("ma50"),
            "ma250": s.get("ma250"),
            "roc20_pct": s.get("roc20_pct"),
            "atr14": s.get("atr14"),
            "sector": s.get("sector"),
            "industry": s.get("industry"),
            "name": s.get("name"),
            "shariah_status": s.get("shariah_status"),
            "user_policy_status": s.get("user_policy_status"),
            "user_policy_reason": s.get("user_policy_reason") or s.get("policy_reason") or s.get("exclusion_reason"),
            "market_as_of_date": s.get("market_as_of_date"),
            "data_freshness": s.get("data_freshness"),
            "strategy_version": s.get("strategy_version"),
            "signal_source": s.get("signal_source"),
            "signal_keys": sorted(s.keys()),
        })

    # Policy exclusions across universe
    excluded_universe = []
    review_universe = []
    for s in pc["signals"]:
        # policy may be only on buy_candidates; check user_policy fields / separate breakdown
        pass

    # From buy candidates + try to find policy details in journal or nested files
    # Load user_policy evidence if any
    up_dir = BACKEND / "data_cache" / "user_policy"
    up_meta = {}
    if up_dir.exists():
        for p in up_dir.glob("*.json"):
            try:
                up_meta[p.name] = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                up_meta[p.name] = {"_error": "parse_failed"}

    # Proposals detail joined with prior post_close signals
    proposals = []
    for run, prior in [
        ("d2_4l_20261027T134503Z", "d2_4l_20261027T000513Z"),
        ("d2_4l_20261028T134502Z", "d2_4l_20261027T203003Z"),
    ]:
        b = load(run)
        prior_b = load(prior)
        prior_sig = {s["ticker"]: s for s in prior_b.get("signals") or []}
        prior_bc = {c["ticker"]: c for c in prior_b.get("buy_candidates") or []}
        for p in b.get("simulated_proposals") or []:
            t = p["ticker"]
            s = prior_sig.get(t, {})
            proposals.append({
                "run": run,
                "trading_day": b.get("trading_day"),
                "ticker": t,
                "pilot_rank": p.get("pilot_rank"),
                "proposed_limit": p.get("proposed_limit"),
                "proposed_qty": p.get("proposed_qty"),
                "proposed_notional": p.get("proposed_notional"),
                "entry_rule": prior_bc.get(t, {}).get("entry_rule") or s.get("entry_rule"),
                "exit_rule": s.get("exit_rule"),
                "signal_price": prior_bc.get(t, {}).get("signal_price") or s.get("close"),
                "close": s.get("close"),
                "atr14": s.get("atr14"),
                "sector": s.get("sector"),
                "ma50": s.get("ma50"),
                "ma250": s.get("ma250"),
                "roc20_pct": s.get("roc20_pct"),
                "policy": prior_bc.get(t, {}).get("policy"),
                "investment": prior_bc.get(t, {}).get("investment"),
            })

    # Optimize cache sample for walk-forward metrics
    opt = BACKEND / "data_cache" / "observation" / "optimize_cache"
    opt_samples = []
    if opt.exists():
        files = sorted(opt.glob("*_2026-10-28_*.json"))[:5]
        for f in files:
            d = json.loads(f.read_text(encoding="utf-8"))
            opt_samples.append({"file": f.name, "keys": sorted(d.keys()) if isinstance(d, dict) else type(d).__name__, "preview": d if not isinstance(d, dict) else {k: d[k] for k in list(d)[:25]}})

    # V40 excel sheets/summary
    xlsx = BACKEND / "engine_core" / "results_v40" / "Adaptive_Trading_Research_V40.xlsx"
    if not xlsx.exists():
        xlsx = BACKEND.parents[1] / "adaptive_trading_v40" / "results_v40" / "Adaptive_Trading_Research_V40.xlsx"
    v40 = {"path": str(xlsx), "exists": xlsx.exists()}
    if xlsx.exists():
        try:
            import openpyxl
            wb = openpyxl.load_workbook(xlsx, read_only=True, data_only=True)
            v40["sheets"] = wb.sheetnames
            for sheet in wb.sheetnames[:12]:
                ws = wb[sheet]
                rows_preview = []
                for i, row in enumerate(ws.iter_rows(values_only=True)):
                    rows_preview.append([str(c) if c is not None else None for c in row[:20]])
                    if i >= 8:
                        break
                v40[f"sheet::{sheet}"] = rows_preview
            wb.close()
        except Exception as e:
            v40["error"] = str(e)

    # USER_POLICY excluded buy candidates with reasons from D2.4H report or policy service files
    excluded = [r for r in rows if r.get("policy") == "EXCLUDED"]
    allowed = [r for r in rows if r.get("policy") == "ALLOWED"]

    # Try reading policy classification from user_policy store used by eligibility
    # Also parse excluded list from d2_4h evidence if present
    d24h = list((EV).glob("d2_4h_*/D2_4H_USER_POLICY_ELIGIBILITY_REPORT.md"))
    d24j = list((EV).glob("d2_4j_*/D2_4J_PILOT_READINESS_REPORT.md"))

    # Classification of why not BUY_READY for candidates that didn't get proposals
    # From next_session rejected - look at journal or bundle for decision reasons
    ns = load("d2_4l_20261028T134502Z")
    # Check if there's more detail in d2_4l_next_session.json
    detail_path = EV / "d2_4l_20261028T134502Z" / "d2_4l_next_session.json"
    detail = json.loads(detail_path.read_text(encoding="utf-8")) if detail_path.exists() else {}

    result = {
        "as_of": pc.get("trading_day"),
        "signal_distribution": pc["scan_summary"]["signal_distribution"],
        "buy_candidates_enriched": rows,
        "excluded_buy_candidates": excluded,
        "allowed_buy_candidates": allowed,
        "allowed_count": len(allowed),
        "excluded_count": len(excluded),
        "proposals": proposals,
        "optimize_cache_samples": opt_samples,
        "v40": {k: v for k, v in v40.items() if not k.startswith("sheet::") or True},
        "d24h_reports": [str(p) for p in d24h],
        "d24j_reports": [str(p) for p in d24j],
        "next_session_detail_keys": sorted(detail.keys()) if isinstance(detail, dict) else None,
        "user_policy_files": list(up_meta.keys()),
        "policy_eligibility_breakdown": pc.get("policy_eligibility_breakdown"),
    }

    # shrink v40 sheet dumps but keep summary-like sheets fully-ish
    OUT.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    print("wrote", OUT)
    print("allowed", len(allowed), "excluded", len(excluded))
    print("allowed tickers", [r["ticker"] for r in allowed])
    print("excluded", [(r["ticker"], r.get("sector"), r.get("user_policy_reason")) for r in excluded])
    print("v40 sheets", v40.get("sheets"))
    print("proposals", len(proposals))


if __name__ == "__main__":
    main()
