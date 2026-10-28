"""Generate Markdown reliability report from one or more IEX evidence JSON files."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List

from alpaca_verification import reprocess_evidence_file


def _fmt_pct(v) -> str:
    return "n/a" if v is None else f"{v:.2f}%"


def _fmt_num(v) -> str:
    return "n/a" if v is None else f"{v:.4f}"


def render_report(evidences: List[Dict[str, Any]], title: str, historical: bool = False) -> str:
    lines: List[str] = []
    banner = "HISTORICAL REPROCESS — not a live multi-session campaign" if historical else "LIVE / SCHEDULED CAMPAIGN"
    lines.append(f"# {title}")
    lines.append("")
    lines.append(f"**Label:** {banner}")
    lines.append("")
    lines.append(
        "Alpaca IEX is a **non-consolidated single-venue** feed (not NBBO). "
        "This assessment does **not** establish consolidated quote quality or fill quality."
    )
    lines.append("")
    lines.append("Execution policy thresholds (unchanged): max spread **0.50%**, max age **30s**, "
                 "regular US session, positive uncrossed two-sided quotes, future skew ≤ **2s**.")
    lines.append("")

    for ev in evidences:
        session = ev.get("session") or {}
        sid = session.get("session_id") or session.get("label") or "session"
        lines.append(f"## Session: `{sid}`")
        if session.get("source_evidence"):
            lines.append(f"- Source evidence: `{session['source_evidence']}`")
        if session.get("minutes_after_open") is not None:
            lines.append(f"- Minutes after US open: {session['minutes_after_open']}")
        lines.append(
            f"- Market session at run: {session.get('market_session_at_run', 'n/a')}"
        )
        feed = (ev.get("feed_connectivity_contract") or {}).get("verdict")
        fresh = (ev.get("execution_freshness_contract") or {}).get("all_fresh_within_30s")
        suit = (ev.get("execution_suitability_contract") or {}).get("overall_execution_suitability")
        lines.append(f"- Feed connectivity: **{feed}**")
        lines.append(f"- All fresh within 30s: **{fresh}**")
        lines.append(f"- Overall execution suitability: **{suit}**")
        lines.append(f"- Orders placed during verification: "
                     f"**{ev.get('orders_placed_during_verification', 0)}**")
        lines.append("")
        lines.append("| Symbol | Recv/Att | Feed% | Fresh% | Spread% | Exec% | Spread med | Age med |")
        lines.append("|---|---:|---:|---:|---:|---:|---:|---:|")
        for sym, row in (ev.get("symbol_reliability") or {}).items():
            lines.append(
                f"| {sym} | {row['samples_received']}/{row['samples_attempted']} | "
                f"{_fmt_pct(row['feed_connectivity_pass_pct'])} | "
                f"{_fmt_pct(row['freshness_pass_pct'])} | "
                f"{_fmt_pct(row['spread_pass_pct'])} | "
                f"{_fmt_pct(row['execution_suitability_pass_pct'])} | "
                f"{_fmt_num(row['spread_pct_median'])} | "
                f"{_fmt_num(row['quote_age_seconds_median'])} |"
            )
        lines.append("")

    # Cross-session narrative hints
    lines.append("## Interpretation notes")
    lines.append("")
    lines.append("- Treat missing sessions (machine off / API failure / holiday) as **inconclusive**, not PASS.")
    lines.append("- Do **not** relax the 0.50% spread threshold to manufacture a PASS.")
    lines.append("- High early-session spread volatility on single-name IEX books is expected; "
                 "SPY often tighter than AAPL/MSFT.")
    lines.append("- A market-data reliability PASS does **not** authorize paper or live trading.")
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", action="append", required=True, help="Evidence JSON path (repeatable)")
    parser.add_argument("--output", required=True, help="Markdown output path")
    parser.add_argument("--title", default="Alpaca IEX Market Data Reliability Report")
    parser.add_argument("--historical", action="store_true")
    parser.add_argument("--reprocess", action="store_true", help="Rebuild aggregates before reporting")
    args = parser.parse_args()

    evidences = []
    for p in args.evidence:
        path = Path(p)
        if args.reprocess:
            evidences.append(reprocess_evidence_file(path))
        else:
            evidences.append(json.loads(path.read_text(encoding="utf-8")))

    md = render_report(evidences, args.title, historical=args.historical)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(md, encoding="utf-8")
    print(f"Wrote {out.resolve()}")


if __name__ == "__main__":
    main()
