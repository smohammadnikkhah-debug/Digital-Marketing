# Stage D2.6 — Controlled Alpaca Paper Pilot Readiness

**Generated:** 2026-10-28T21:34:31Z (read-only preparation)  
**Evidence:** `stockanalysis/web_app/backend/data_cache/evidence/d2_6_20261028T213431Z/d2_6_readiness.json`  
**Orders placed:** **0** (paper and live)  
**Execution flags changed:** **No** — emergency stop and execution-disabled defaults preserved  

---

## Recommendation: **NO-GO**

**Blocking prerequisite:** D2.4L soak is **incomplete** (2 of 3 pairs). Keep all execution blocked until the unattended **2026-10-29 next_session** closes pair `2026-10-28→2026-10-29` and `soak_ledger.json` shows `soak_complete=true`.

Pilot prep otherwise looks healthy: candidate selected, live Alpaca quote used for sizing, paper endpoint verified, one-order manual gate verified, submit path still blocked.

---

## 1. D2.4L final observation pair

| Check | Result |
|---|---|
| Completed pairs | `2026-10-26→2026-10-27`, `2026-10-27→2026-10-28` |
| Target | 3 |
| `soak_complete` | **false** |
| Oct 29 next_session evidence | **Missing** |
| Prerequisite met | **No** |

**Remaining prerequisite:** Allow the Windows unattended observation poller to run **next_session** in the 09:45 ET window on **2026-10-29**. Do not force-run out of window. Do not enable broker execution while waiting.

---

## 2. Selected pilot candidate

Selection method: scan-sequence among USER_POLICY **ALLOWED** BUY CANDIDATES from latest FRESH post-close bundle (`d2_4l_20261028T203002Z`), then first name that can buy **≥1 whole share** from a **current Alpaca IEX ask** under **$500**.

| Field | Value |
|---|---|
| Ticker | **NOW** (ServiceNow) |
| Bundle scan position | 3rd BUY row (AMD skipped: ask above $500 whole-share cap) |
| Signal | BUY CANDIDATE · FRESH · as-of 2026-10-28 |
| Entry / exit | `DELAYED_STACK` / `MA250_ATR3` |
| USER_POLICY | **ALLOWED** (re-classified independently) |
| Research close (bundle) | $150.13 — **not used as limit** |
| Live Alpaca ask / bid | **$127.89 / $127.25** (`ALPACA_IEX`) |
| Qty / limit / notional | **3** / **$127.89** / **$383.67** |
| Quote 30s freshness | **False** (after-hours / stale print — refresh in regular session before any submit) |

Higher-ranked ALLOWED name skipped: **AMD** — live ask not whole-share affordable under $500.

---

## 3. Independent price / risk / sizing validation

- Limit price comes from **Alpaca IEX ask at readiness time**, not from Oct 27 simulated proposal ($153.57) or research close ($150.13).
- Whole-share math: `int(min(500, cash) // ask) = 3`; notional $383.67 ≤ $500.
- Cash on paper account: **$100,000** (sufficient).
- **No fixed stop-loss price** on V4.0 signals. Risk plan for pilot:
  - Strategy exit rule: `MA250_ATR3`
  - ATR14 context from signal ≈ $6.33 → ~**$18.99** 1×ATR dollar move on 3 shares (illustrative only)
  - Hard loss bound for this ticket: full notional **$383.67** (worst case if worthless — not expected, but the cash at risk)
  - Portfolio open-order cap remains **1**

---

## 4. Alpaca paper verification (no submit)

| Check | Result |
|---|---|
| Credentials present | Yes |
| Connected | Yes |
| Account (redacted) | `****8WNN` |
| Status / blocked | Active; trading_blocked false |
| Cash / equity / cash BP | $100,000 / $100,000 / $100,000 |
| Positions / open orders | 0 / 0 |
| Configured trading URL | `https://paper-api.alpaca.markets` |
| Live API rejected | Yes (paper-only invariant) |
| Exact orders endpoint (documented) | `https://paper-api.alpaca.markets/v2/orders` |
| SDK submit path (documented, not called) | `TradingClient(paper=True, url_override=…).submit_order(LimitOrderRequest(…))` |
| `submit_order` probe | **Blocked** (`NON_EXECUTING_BUILD_GUARD`) |
| Submissions attempted | **0** |

---

## 5. LIMIT order preview (not submitted)

| Field | Preview |
|---|---|
| Side / type / TIF | BUY / LIMIT / DAY |
| Ticker | NOW |
| Quantity | 3 |
| Limit | $127.89 |
| Notional | $383.67 |
| Broker / env | alpaca / paper |
| Signal rationale | V4.0 BUY CANDIDATE; entry `DELAYED_STACK`; exit `MA250_ATR3` |
| Policy | USER_POLICY ALLOWED |
| Stop / risk | No broker stop ticket; exit via `MA250_ATR3`; $500 order cap; 1 open order |
| Status | `PREVIEW_ONLY_NOT_SUBMITTED` |

### Safety checks that must pass before any future submit

1. D2.4L `soak_complete == true` (3 pairs)  
2. Explicit human authorization for **one** paper order  
3. `ALPACA_ENV=paper` and URL `paper-api.alpaca.markets`  
4. USER_POLICY ALLOWED re-checked at approval time  
5. Fresh regular-session Alpaca quote; whole-share qty ≥ 1 under $500  
6. Cash ≥ notional; open orders = 0; daily caps OK; no existing long in NOW  
7. Lifecycle: propose → `AWAITING_APPROVAL` → **manual** approve → single submit  
8. `can_auto_resubmit=false`; no retries/batch  
9. `LIVE_TRADING_ENABLED=false`  
10. Immediately restore execution-disabled defaults after the single submit attempt  

---

## 6. One-order manual pilot gate

Implemented/verified in `app/services/paper_pilot_gate.py` (tests: `tests/test_d2_6_paper_pilot_gate.py` — 6 passed).

| Invariant | Value |
|---|---|
| `PILOT_MAX_ORDERS` | 1 |
| Auto-submit / auto-retry / batch | **False / False / False** |
| Manual approval required | **True** |
| `STAGE_APPROVAL_ENABLED` | False |
| `STAGE_SUBMISSION_ENABLED` | False |
| `TRADING_EXECUTION_ENABLED` | False |
| `ALPACA_EXECUTION_ENABLED` | False |
| `IBKR_EMERGENCY_STOP` | True |
| Gate verification | **Passed** |

Existing `OrderExecutionService` already supports `propose_order` → `AWAITING_APPROVAL` → `approve_order` with emergency-stop denial and `can_auto_resubmit=False`. D2.6 adds an explicit pilot gate wrapper that refuses to treat preparation as authorization.

---

## 7. Tracking availability for the pilot

| Surface | Available? |
|---|---|
| `paper_orders` DB + event audit | Yes (0 rows today) |
| Lifecycle states | DRAFT → AWAITING_APPROVAL → APPROVED → SUBMITTED → FILL/CANCEL/REJECT |
| Alpaca positions / orders read | Yes (0 / 0) |
| Position P&L fields | `unrealized_pl`, `unrealized_plpc`, `avg_entry_price`, `market_value` |
| Fill approximation module | Yes (`observation_performance`) — not a broker fill |
| SPY benchmark | In universe; V40 AnnualVsSPY + observation helpers |
| Real broker fills to date | **0** |

---

## 8. Exact remaining authorization steps

0. **DO NOT authorize execution** while soak is incomplete.  
1. Wait for unattended **2026-10-29 next_session**; confirm `completed_pair_ids` length **3** and `soak_complete=true`.  
2. Re-run `run_d2_6_readiness()` in a **regular US session** and confirm quote freshness + preview still valid for NOW (or next eligible name).  
3. Written authorization for **one** Alpaca paper LIMIT order only.  
4. Confirm paper account binding; keep `LIVE_TRADING_ENABLED=false`.  
5. Controlled, temporary enablement of paper submit path for that single manually approved order only (no batch/retry).  
6. `propose_order` → manual `approve_order` → **one** submit → restore disabled defaults immediately.  
7. Monitor Alpaca blotter + `PaperOrder` lifecycle + unrealized P&L vs SPY.

---

## 9. Bottom line

| Area | Status |
|---|---|
| Soak prerequisite | **Fail** (2/3) |
| Candidate + live sizing preview | Pass (NOW, $383.67) — refresh quote in session |
| Alpaca paper connectivity / endpoint | Pass |
| One-order manual gate / emergency stops | Pass (still blocking submit) |
| Tracking surfaces | Pass |
| **Execute now?** | **NO-GO** |

Code added for preparation only: `paper_pilot_gate.py` + unit tests. No production data mutation, no commits, no deploy, no orders.
