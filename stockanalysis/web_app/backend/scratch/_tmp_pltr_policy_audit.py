"""Read-only audit: PLTR exclusion impact + historical proposal annotation + peer review."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from app.services.d2_4i_review_resolution import apply_local_review_resolutions
from app.services.observation_safety import assert_observation_safety
from app.services.user_policy_eligibility import (
    POLICY_ALLOWED,
    POLICY_EXCLUDED,
    POLICY_REVIEW,
    assert_user_policy_order_permitted,
    classify_user_policy,
)

BACKEND = Path(__file__).resolve().parents[1]
EV = BACKEND / "data_cache" / "evidence"
BUNDLE = EV / "d2_4l_20261028T203002Z" / "session_bundle.json"


def main() -> None:
    # Refresh local overlay so file evidence matches explicit exclusion (no prod DB writes)
    overlay = apply_local_review_resolutions()

    pltr = classify_user_policy(
        "PLTR",
        name="Palantir Technologies Inc.",
        sector="Technology",
        industry="Software - Infrastructure",
    )
    gate = assert_user_policy_order_permitted("PLTR")

    bundle = json.loads(BUNDLE.read_text(encoding="utf-8"))
    signals = {s["ticker"]: s for s in bundle.get("signals") or []}
    buy = bundle.get("buy_candidates") or []

    # Re-evaluate current BUY list under corrected policy (do not mutate bundle)
    reclass = []
    for c in buy:
        t = c["ticker"]
        s = signals.get(t, {})
        pol = classify_user_policy(
            t,
            name=s.get("name"),
            sector=s.get("sector"),
            industry=s.get("industry"),
        )
        reclass.append(
            {
                "ticker": t,
                "historical_bundle_policy": c.get("policy"),
                "current_user_policy_status": pol.get("user_policy_status"),
                "reason_codes": pol.get("reason_codes"),
                "proposal_permitted": pol.get("proposal_permitted"),
                "signal": s.get("signal"),
                "sector": s.get("sector"),
                "industry": s.get("industry"),
                "name": s.get("name"),
            }
        )

    eligible_now = [
        r
        for r in reclass
        if r["current_user_policy_status"] == POLICY_ALLOWED and r["signal"] == "BUY CANDIDATE"
    ]
    excluded_buys = [r for r in reclass if r["current_user_policy_status"] == POLICY_EXCLUDED]
    review_buys = [r for r in reclass if r["current_user_policy_status"] == POLICY_REVIEW]

    # Historical PLTR proposals (annotate only)
    historical = []
    for p in EV.rglob("session_bundle.json"):
        d = json.loads(p.read_text(encoding="utf-8"))
        for prop in d.get("simulated_proposals") or []:
            t = (prop.get("ticker") or "").upper()
            if t != "PLTR":
                continue
            historical.append(
                {
                    "evidence_bundle": p.parent.name,
                    "trading_day": d.get("trading_day"),
                    "mode": d.get("mode"),
                    "proposal": prop,
                    "historical_record_mutated": False,
                    "current_policy_annotation": "POLICY_INELIGIBLE",
                    "reason_codes": pltr.get("reason_codes"),
                    "note": (
                        "Historical observation artifact retained unchanged. "
                        "Under current USER_POLICY, PLTR is not eligible for "
                        "proposals, paper orders, or live orders."
                    ),
                }
            )

    # Manual review candidates among currently ALLOWED buys for military/defence uncertainty
    # (do NOT auto-exclude — report only)
    uncertain_review = []
    keywords = (
        "defense",
        "defence",
        "military",
        "weapon",
        "aerospace",
        "intelligence",
        "government",
        "cyber",
    )
    notes = {
        "CRWD": "CrowdStrike — cybersecurity with material government/defence customer exposure; manual review recommended.",
        "ZS": "Zscaler — zero-trust security with public-sector/defence customers; manual review recommended.",
        "CSCO": "Cisco — networking equipment sold into government and defence networks; manual review recommended.",
        "TXN": "Texas Instruments — semiconductors with known aerospace/defence end markets; manual review recommended.",
        "EMR": "Emerson — industrial automation; possible dual-use / government exposure; manual review recommended.",
        "MSFT": "Microsoft — broad commercial cloud with known defence cloud contracts (e.g. public-sector); manual review recommended.",
    }
    for r in eligible_now:
        t = r["ticker"]
        blob = f"{r.get('name')} {r.get('industry')} {r.get('sector')}".lower()
        flagged = t in ("CRWD", "ZS", "CSCO", "TXN", "EMR", "MSFT")
        if flagged or any(k in blob for k in keywords):
            uncertain_review.append(
                {
                    "ticker": t,
                    "current_status": POLICY_ALLOWED,
                    "recommended_action": "MANUAL_REVIEW",
                    "why": notes.get(t)
                    or (
                        "Industry/name keywords suggest possible defence/government exposure; "
                        "not auto-excluded."
                    ),
                    "auto_excluded": False,
                }
            )

    safety = assert_observation_safety(phase="pltr_policy_correction")

    out = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "pltr_classification": pltr,
        "pltr_order_gate": gate,
        "overlay_refresh": overlay,
        "universe_note": (
            "PLTR remains in the research/scan universe; research_visible=True; "
            "marked POLICY_EXCLUDED for proposals/orders."
        ),
        "latest_post_close_buy_reeval": {
            "as_of": bundle.get("trading_day"),
            "historical_buy_candidate_count": len(buy),
            "eligible_buy_count_under_corrected_policy": len(eligible_now),
            "eligible_tickers": [r["ticker"] for r in eligible_now],
            "excluded_buy_tickers": [
                {"ticker": r["ticker"], "reason_codes": r["reason_codes"]} for r in excluded_buys
            ],
            "review_buy_tickers": [r["ticker"] for r in review_buys],
        },
        "historical_pltr_proposals_annotated": historical,
        "additional_manual_review_recommended": uncertain_review,
        "safety": safety,
        "execution_unchanged": {
            "submissions_attempted": 0,
            "note": "Alpaca execution left disabled; emergency stops intact.",
        },
    }

    out_dir = EV / f"user_policy_pltr_exclusion_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "PLTR_POLICY_EXCLUSION_AUDIT.json"
    path.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print(json.dumps({
        "audit_path": str(path),
        "eligible_buy_count": len(eligible_now),
        "eligible": [r["ticker"] for r in eligible_now],
        "excluded_buys": [r["ticker"] for r in excluded_buys],
        "manual_review": [r["ticker"] for r in uncertain_review],
        "historical_pltr_proposals": len(historical),
        "pltr_status": pltr.get("user_policy_status"),
        "pltr_reasons": pltr.get("reason_codes"),
        "safety_passed": safety.get("passed"),
    }, indent=2))


if __name__ == "__main__":
    main()
