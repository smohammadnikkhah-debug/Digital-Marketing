"""Read-only USER_POLICY + ranking extract for D2.5."""
from __future__ import annotations

import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parents[2]  # Digital Marketing
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(BACKEND))

from app.config import (
    ALPACA_ENV,
    ALPACA_EXECUTION_ENABLED,
    DEFAULT_FEE_BPS,
    IBKR_EMERGENCY_STOP,
    IBKR_EXECUTION_ENABLED,
    INVESTMENT_ELIGIBILITY_MODE,
    LIVE_TRADING_ENABLED,
    PAPER_BROKER,
    TRADING_EXECUTION_ENABLED,
)
from app.services.observation_safety import assert_observation_safety
from app.services.user_policy_eligibility import classify_user_policy

pc = json.loads(
    (BACKEND / "data_cache/evidence/d2_4l_20261028T203002Z/session_bundle.json").read_text(
        encoding="utf-8"
    )
)
by = {s["ticker"]: s for s in pc["signals"]}

excl, review = [], []
allowed_n = 0
for s in pc["signals"]:
    r = classify_user_policy(
        ticker=s.get("ticker"),
        sector=s.get("sector"),
        industry=s.get("industry"),
        name=s.get("name") or s.get("company_name"),
    )
    st = r.get("user_policy_status")
    item = {
        "ticker": s.get("ticker"),
        "signal": s.get("signal"),
        "status": st,
        "reason_codes": r.get("reason_codes"),
        "evidence_note": r.get("evidence_note"),
        "sector": s.get("sector"),
        "industry": s.get("industry"),
    }
    if st == "EXCLUDED":
        excl.append(item)
    elif st == "REVIEW REQUIRED":
        review.append(item)
    else:
        allowed_n += 1

allowed_buys = [c for c in pc["buy_candidates"] if c.get("policy") == "ALLOWED"]
ranked = []
for i, c in enumerate(allowed_buys, 1):
    s = by[c["ticker"]]
    close = float(s["close"])
    ranked.append(
        {
            "scan_rank": i,
            "ticker": c["ticker"],
            "close": close,
            "entry_rule": c["entry_rule"],
            "exit_rule": s.get("exit_rule"),
            "atr14": s.get("atr14"),
            "roc20_pct": s.get("roc20_pct"),
            "ma50": s.get("ma50"),
            "ma250": s.get("ma250"),
            "sector": s.get("sector"),
            "industry": s.get("industry"),
            "name": s.get("name"),
            "whole_share_under_500": close <= 500.0,
            "approx_qty_at_500": int(500 // close) if close > 0 else 0,
            "approx_notional_at_500": round(int(500 // close) * close, 2) if close > 0 else 0,
        }
    )

proposals = []
for run in ["d2_4l_20261027T134503Z", "d2_4l_20261028T134502Z"]:
    b = json.loads(
        (BACKEND / f"data_cache/evidence/{run}/session_bundle.json").read_text(encoding="utf-8")
    )
    for p in b.get("simulated_proposals") or []:
        proposals.append({"run": run, "trading_day": b.get("trading_day"), **p})

out = {
    "policy_counts": {
        "ALLOWED": allowed_n,
        "EXCLUDED": len(excl),
        "REVIEW_REQUIRED": len(review),
    },
    "excluded_all": excl,
    "excluded_buy_candidates": [e for e in excl if e["signal"] == "BUY CANDIDATE"],
    "review_buy_candidates": [e for e in review if e["signal"] == "BUY CANDIDATE"],
    "ranked_allowed_buys": ranked,
    "top10_affordable": [r for r in ranked if r["whole_share_under_500"]][:10],
    "top10_scan_sequence": ranked[:10],
    "proposals": proposals,
    "safety": assert_observation_safety(phase="d2_5_readonly"),
    "flags": {
        "IBKR_EMERGENCY_STOP": IBKR_EMERGENCY_STOP,
        "TRADING_EXECUTION_ENABLED": TRADING_EXECUTION_ENABLED,
        "ALPACA_EXECUTION_ENABLED": ALPACA_EXECUTION_ENABLED,
        "IBKR_EXECUTION_ENABLED": IBKR_EXECUTION_ENABLED,
        "LIVE_TRADING_ENABLED": LIVE_TRADING_ENABLED,
        "PAPER_BROKER": PAPER_BROKER,
        "ALPACA_ENV": ALPACA_ENV,
        "INVESTMENT_ELIGIBILITY_MODE": INVESTMENT_ELIGIBILITY_MODE,
        "DEFAULT_FEE_BPS": DEFAULT_FEE_BPS,
    },
}
path = BACKEND / "scratch/_tmp_d2_5_policy_out.json"
path.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
print("wrote", path)
print("policy", out["policy_counts"])
print("excluded buys", [e["ticker"] for e in out["excluded_buy_candidates"]])
print("top10 affordable", [r["ticker"] for r in out["top10_affordable"]])
print("safety_passed", out["safety"]["passed"], out["flags"])
