# Stage D2.5 — Strategy Validation & Paper-Trading Readiness

**Report date:** 2026-10-29 (local)  
**Analysis mode:** Read-only (no broker orders, no production mutations, no deploys, no commits)  
**Strategy:** V4.0 Baseline (via V4.1 Engine in `exit_mode=baseline`)  
**Primary evidence as-of:** 2026-10-28 post-close live scan (`d2_4l_20261028T203002Z`)  
**Observation soak:** 2 of 3 completed pairs; third pair (`2026-10-28→2026-10-29`) awaiting Oct 29 next-session leg

---

## 1. Executive summary

StockAnalysis currently flags **32 BUY CANDIDATE** names across a **227-ticker** fresh scan (2026-10-28). After USER_POLICY, **28** remain investment-eligible; **4** BUY names are excluded (SPY, MS, MO, XLP). The system has already produced **13 simulated LIMIT proposals** across two unattended next-session mornings (9 on Oct 27, 4 on Oct 28), all cash-only / whole-share / ≤$500, with **zero broker submissions**.

**Investment verdict:** Research-era V4.0 results look strong versus SPY on the frozen baseline workbook, but **live observation has not yet measured real (or even approximated) post-signal fills** — every recorded proposal still shows `NO_SUBSEQUENT_BARS`. Operational plumbing is ready; **investment edge under the $500 paper constraints is not yet proven in live sessions**.

**Paper-trading recommendation: CONDITIONAL GO**

Proceed to a tightly gated first Alpaca paper order only after the third soak pair completes and the minimum stage flips listed in §7 are done. Do **not** enable broad automated submission yet.

---

## 2. What StockAnalysis currently recommends

### 2.1 Universe signal snapshot (2026-10-28 post-close)

| Signal | Count | Share |
|---|---:|---:|
| BUY CANDIDATE | 32 | 14.1% |
| WATCH | 116 | 51.1% |
| AVOID | 76 | 33.5% |
| HOLD | 3 | 1.3% |
| **Scanned** | **227** | **100%** |

- Freshness: **FRESH** (`SESSION_AS_OF_MATCH`), 227/227 bars as-of 2026-10-28  
- Data-quality failures: **0**  
- Stale / insufficient market data in this session: **none**  
- Strategy provenance: all `V40_SCANNER` / live scan  
- Policy overlay on full universe: ALLOWED **181** · EXCLUDED **22** · REVIEW REQUIRED **24**

> Note: The SQLite active screener snapshot (`snap_baseline_20261021_232124`, market_as_of ≈ 2026-10-20, 29 BUY names) is **older** than the observation ledger. This report treats **D2.4L session bundles as authoritative** for current recommendations.

### 2.2 BUY CANDIDATE set (policy-split)

| Policy | Count | Tickers |
|---|---:|---|
| ALLOWED | 28 | AMD, NOW, INTC, CRWD, MSFT, PLTR, ZS, PYPL, CSCO, TSM, TXN, MU, DHR, GILD, ELV, CI, V, CB, ROST, DG, EMR, XOM, COP, MPC, KMI, APD, NUE, SOXX |
| EXCLUDED | 4 | SPY, MS, MO, XLP |
| REVIEW REQUIRED | 0 | — |

Entry rules in this BUY set are predominantly **DELAYED_STACK** or **DELAYED_MA50**. Exit rules retained from walk-forward selection are **MA250_3CLOSE** or **MA250_ATR3** (rule-based trailing exits — **not** a fixed percentage stop-loss stored on the signal).

### 2.3 Metrics available vs unavailable on live signals

| Metric | Available on live BUY signals? | Source / note |
|---|---|---|
| Current close / signal price | Yes | Scanner OHLC close |
| Entry rule + exit rule | Yes | Per-ticker walk-forward selection |
| MA30 / MA50 / MA250, ROC20, ATR14 | Yes | Indicator context |
| Fixed stop-loss price | **No** | Exit is MA250-based rule, not a stop ticket |
| Explicit risk/reward ratio | **No** | Not emitted by scanner |
| Expected holding period (live) | **No** | Only historical trade stats (see §3) |
| Cross-sectional “signal quality” score | **No** | Training score selects rules per ticker/year; not a buy rank |

Do not treat missing fields as zero or invent ranks.

---

## 3. Top eligible candidates (actionable under $500 whole-share cap)

Pilot ranking for paper use remains **scan-sequence among ALLOWED BUY names that can buy ≥1 share at ≤$500** (D2.4J method: no invented investment score; price is a hard affordability gate, not a quality score).

**As-of 2026-10-28 closes (research prices — broker LIMIT would use Alpaca IEX ask at session time):**

| # | Ticker | Close | Entry | Exit | ATR14 | ROC20% | ≈ Qty @ $500 | ≈ Notional |
|---:|---|---:|---|---|---:|---:|---:|---:|
| 1 | NOW | 150.13 | DELAYED_STACK | MA250_ATR3 | 6.33 | +12.03 | 3 | $450.39 |
| 2 | INTC | 95.53 | DELAYED_MA50 | MA250_3CLOSE | 5.06 | −20.54 | 5 | $477.65 |
| 3 | CRWD | 266.66 | DELAYED_MA50 | MA250_3CLOSE | 12.89 | +0.72 | 1 | $266.66 |
| 4 | PLTR | 196.81 | DELAYED_STACK | MA250_3CLOSE | 8.80 | +5.22 | 2 | $393.62 |
| 5 | ZS | 255.80 | DELAYED_MA50 | MA250_ATR3 | 12.98 | +28.27 | 1 | $255.80 |
| 6 | PYPL | 56.55 | DELAYED_MA50 | MA250_ATR3 | 1.26 | +7.65 | 8 | $452.40 |
| 7 | CSCO | 110.29 | DELAYED_STACK | MA250_ATR3 | 3.14 | +2.87 | 4 | $441.16 |
| 8 | TSM | 439.51 | DELAYED_MA50 | MA250_ATR3 | 13.15 | −3.66 | 1 | $439.51 |
| 9 | TXN | 309.83 | DELAYED_STACK | MA250_3CLOSE | 10.01 | +10.62 | 1 | $309.83 |
| 10 | DHR | 234.07 | DELAYED_MA50 | MA250_3CLOSE | 6.50 | +5.65 | 2 | $468.14 |

**ALLOWED but currently unaffordable as whole shares under the $500 order cap** (examples): AMD, MSFT, MU (and any other name whose ask exceeds $500). These remain research BUY CANDIDATES but cannot become paper proposals under the current sizing policy without raising the cap or enabling fractional shares (fractionals are intentionally off).

**Entry rationale (shared V4.0 logic, not stock-specific prose):**  
A BUY CANDIDATE means the ticker’s selected entry rule fired on the latest fresh bar while price structure remains consistent with the selected MA250 exit regime. Confirmation for a *proposal* additionally requires USER_POLICY ALLOWED, regular session (or allowed off-session sizing for observation), live Alpaca quote, and capacity under cash / open-order / daily limits.

---

## 4. USER_POLICY rejections

### 4.1 BUY CANDIDATES rejected (cannot propose)

| Ticker | Reason code | Why |
|---|---|---|
| SPY | `POLICY_ETF_EXCLUDED_EXPOSURES` | Broad S&P 500 ETF with material banks, tobacco, defence, airlines |
| MS | `POLICY_EXCLUDED_BANKING_LENDING` | Capital Markets → conventional banking/lending exclusion |
| MO | `POLICY_EXCLUDED_TOBACCO` | Altria — tobacco manufacturer |
| XLP | `POLICY_ETF_EXCLUDED_TOBACCO_EXPOSURE` | Staples ETF with material tobacco holdings |

### 4.2 Full-universe EXCLUDED (22)

Banking/lending: JPM, BAC, WFC, MS, GS, SCHW, AXP, C, USB, PNC, COF  
Tobacco: PM, MO  
Weapons/defence: GE, BA, RTX, LMT, GD, NOC, TDG  
ETF exposures: SPY, XLP  

REVIEW REQUIRED (24 names) are held out of auto-eligibility pending manual business classification — none of the current BUY CANDIDATES sit in REVIEW on the Oct 28 scan.

USER_POLICY is enforced in `BuyDecisionEngine` / investment eligibility **before** proposal generation and would remain required before any future order path.

---

## 5. Simulated proposals from next-session observations

These are **simulated LIMIT BUY proposals only**. `submissions_attempted = 0` on every soak session. They are **not** trades.

### 5.1 Pair 1 next-session — 2026-10-27 (`d2_4l_20261027T134503Z`) — 9 proposals

| Rank | Ticker | Limit | Qty | Notional |
|---:|---|---:|---:|---:|
| 1 | NOW | 153.57 | 3 | $460.71 |
| 2 | ZS | 261.36 | 1 | $261.36 |
| 3 | DHR | 232.01 | 2 | $464.02 |
| 4 | ELV | 431.61 | 1 | $431.61 |
| 5 | CB | 374.58 | 1 | $374.58 |
| 6 | DG | 134.22 | 3 | $402.66 |
| 7 | EMR | 162.94 | 3 | $488.82 |
| 8 | MPC | 482.68 | 1 | $482.68 |
| 9 | NUE | 278.15 | 1 | $278.15 |

### 5.2 Pair 2 next-session — 2026-10-28 (`d2_4l_20261028T134502Z`) — 4 proposals

| Rank | Ticker | Limit | Qty | Notional |
|---:|---|---:|---:|---:|
| 1 | PLTR | 197.48 | 2 | $394.96 |
| 2 | ELV | 420.89 | 1 | $420.89 |
| 3 | CI | 298.16 | 1 | $298.16 |
| 4 | EMR | 168.04 | 2 | $336.08 |

Open-order cap (`max_open_orders = 1`) explains why only a short list is marked proposal-ready in a single morning even when more BUY_READY names exist: later names wait.

### 5.3 Live fill approximation status

All 13 proposal performance records report:

- `is_real_broker_fill: false`  
- `error: NO_SUBSEQUENT_BARS`  
- `would_have_filled_approx: null`

**Gap:** There is not yet a measured live hit-rate for whether these LIMIT prices would have filled on subsequent sessions. The third soak pair (Oct 29 next-session, still pending as of this report) should be allowed to finish automatically; if subsequent bars exist by then, re-check `observation_performance` before enabling orders.

---

## 6. Strategy performance evidence

### 6.1 Frozen V4.0 research baseline (authoritative historical evidence)

Source: `Adaptive_Trading_Research_V40.xlsx` (`BenchmarkDashboard`, `Trades`, `AnnualVsSPY`, `Guide`).  
Labelled **research-only / HT not approved**. Cash-only portfolio simulation.

| Metric | Portfolio | SPY benchmark |
|---|---:|---:|
| Initial capital | $100,000 | $100,000 |
| Ending value (through 2026-10-09) | $1,396,996.56 | $461,768.66 |
| Total return | **+1,297.0%** | +361.8% |
| CAGR | **27.8%** | 15.3% |
| Max drawdown | **−42.5%** | −33.7% |
| Years beating SPY | 9 / 11 | — |
| Completed trades | **80** | — |

**Trade-level stats computed from the Trades sheet (80 closed research trades):**

| Metric | Value |
|---|---:|
| Win rate | **35.0%** (28 wins / 52 losses) |
| Average trade return | +25.5% |
| Average winning trade | +87.2% |
| Average losing trade | −7.7% |
| Profit factor (gross $ wins / gross $ losses) | **3.87** |
| Median holding period | **89 days** |
| Mean holding period | **212 days** |
| Best / worst trade return | +345.1% / −34.8% |

**Transaction cost assumption (Guide):** **10 bps per side** on adjusted Yahoo OHLC; signals at prior close, fills at next open. Guide explicitly states: no tax, borrow, spread, or slippage beyond that fee model.

**Walk-forward design (Guide + StrategySelection):** each January selects entry/exit using **prior training years only** (no future test-year leakage in rule selection). TrainingScores are **rule-selection scores**, not live buy ranks.

### 6.2 Live observation performance

| Item | Status |
|---|---|
| Observation periods completed (pairs) | **2 / 3** target |
| Distinct FRESH unattended sessions | post_close 10/26, 10/27, 10/28 + next_session 10/27, 10/28 |
| Broker trades | **0** |
| Approximated fills with subsequent bars | **0** (all `NO_SUBSEQUENT_BARS`) |
| Live win rate / P&L / drawdown | **Not measurable yet** |

### 6.3 Limitations (do not over-claim)

1. **Sample size:** 80 research trades over ~11 years is modest; results are dominated by a minority of large winners (low win rate, high payoff asymmetry).  
2. **Survivorship / fixed universe bias** called out in the V40 Guide.  
3. **Look-ahead:** walk-forward January selection is designed to avoid test-year leakage; still, indicator/parameter research history can overfit the training objective (40% return / 40% DD / 20% low frequency).  
4. **Overfitting risk:** per-ticker yearly rule switching increases flexibility; paper trading will stress whether live DELAYED_* entries retain edge.  
5. **Scale mismatch:** research used $100k with multi-position compounding; paper constraints ($500/order, 1 open order, $2,500/day) will **not** reproduce research CAGR.  
6. **No live stop tickets:** MA250 exits can allow deep adverse excursions before exit (research max DD −42.5%).  
7. **DB `backtest_runs` table:** 0 rows — do not cite an in-app backtest API run; the Excel baseline is the performance artifact.

---

## 7. Example proposed trades (sizing & risk framing)

Examples use **actual simulated proposals** (not hypothetical new trades). Risk framing uses ATR / MA250 context because **no fixed stop price exists on the signal**.

### Example A — PLTR (2026-10-28 proposal #1)

| Field | Value |
|---|---|
| Side / type | BUY LIMIT |
| Limit | $197.48 |
| Quantity | 2 whole shares |
| Notional | **$394.96** (under $500 cap) |
| Entry rule | DELAYED_STACK |
| Exit rule | MA250_3CLOSE |
| Signal close (prior post-close) | ~$198.73 |
| ATR14 context | ~$8.80 → ≈ **$17.60** 1×ATR move on 2 shares (~4.5% of notional) |
| Structural exit anchor | MA250 ≈ $158.75 on 10/28 scan (far below entry — trend-follow, not tight stop) |
| Cash impact on $100k paper | &lt;0.4% of equity |
| Max open orders interaction | Blocks further buys until this order completes/cancels |

### Example B — NOW (2026-10-27 proposal #1)

| Field | Value |
|---|---|
| Limit / qty / notional | $153.57 × 3 = **$460.71** |
| Entry / exit | DELAYED_STACK / MA250_ATR3 |
| ATR14 context | ~$6.33 → ≈ **$18.99** 1×ATR on 3 shares |
| Holding expectation | Historical median ~3 months; **not a forecast for this ticket** |

### Example C — EMR (appeared both mornings)

| Session | Limit | Qty | Notional |
|---|---:|---:|---:|
| 2026-10-27 | 162.94 | 3 | $488.82 |
| 2026-10-28 | 168.04 | 2 | $336.08 |

Illustrates that proposal size tracks quote + remaining daily/open-order capacity, not a fixed share count.

**Daily capacity under proposed constraints (already coded defaults):**

- Max order notional: **$500** (`DEFAULT_MAX_ORDER_NOTIONAL_USD`)  
- Max daily orders: **5**  
- Max daily notional: **$2,500**  
- Max open orders: **1**  
- Cash-only, long-only, LIMIT, whole shares  

---

## 8. Paper-trading readiness (Alpaca read-only inspection)

### 8.1 Proposed constraints vs implemented guards

| Constraint | Implemented today? | Where |
|---|---|---|
| Cash-only, long-only | Yes | Account snapshot uses cash / non-margin BP; existing long blocks duplicate buys |
| LIMIT orders, whole shares | Yes | `OrderProposalEngine` + qty `int(slot_budget // ask)` |
| Max $500 / order | Yes | `DEFAULT_MAX_ORDER_NOTIONAL_USD = 500` |
| Max 5 orders / day | Yes | `DEFAULT_MAX_DAILY_ORDERS = 5` |
| Max $2,500 daily notional | Yes | `DEFAULT_MAX_DAILY_NOTIONAL_USD = 2500` |
| Max 1 open order | Yes | `DEFAULT_MAX_OPEN_ORDERS = 1` |
| No margin / leverage / short / options | Yes (path design) | Cash sizing; equities LIMIT BUY only in proposal path |
| USER_POLICY before proposal/order | Yes | `BuyDecisionEngine` + eligibility mode `USER_POLICY` |

### 8.2 Emergency-stop & execution guards (verified this analysis)

| Guard | Current value | Status |
|---|---|---|
| `IBKR_EMERGENCY_STOP` | **True** | Active |
| `TRADING_EXECUTION_ENABLED` | **False** | Active |
| `ALPACA_EXECUTION_ENABLED` | **False** | Active |
| `IBKR_EXECUTION_ENABLED` | **False** | Active |
| `LIVE_TRADING_ENABLED` | **False** | Active |
| `STAGE_APPROVAL_ENABLED` | **False** (hard-coded) | Active |
| `STAGE_SUBMISSION_ENABLED` | **False** (hard-coded) | Active |
| Alpaca `NON_EXECUTING_BUILD_GUARD` | **True** | `submit_order` raises `PermissionError` |
| Observation safety assert | **Passed** | `assert_observation_safety` |
| Paper orders in DB | **0** | No live paper ticket history |

### 8.3 Alpaca paper account (read-only)

| Check | Result |
|---|---|
| Connection | OK / snapshot fresh |
| Environment | `PAPER_BROKER=alpaca`, `ALPACA_ENV=paper` |
| Cash / equity | $100,000 / $100,000 |
| Positions / open orders | 0 / 0 |
| Account id | redacted (`****8WNN`) |
| Clock at check | Market closed; next open **2026-10-29 09:30 ET** |
| Submit probe | **Blocked** by non-executing build guard |

Integration is safe for continued read-only observation. It is **not** yet armed for simulated order submission.

---

## 9. Key weaknesses / loss risks

1. **Trend-follow drawdowns:** research max DD ≈ **−42%**; MA250 exits can stay long through large interim losses.  
2. **Low hit-rate / fat tails:** ~35% wins — a short paper sample can look like “the strategy doesn’t work” even if research edge is real.  
3. **$500 sizing:** cannot express high-priced names (AMD/MSFT/MU); portfolio will skew to mid-priced names and may differ from research mix.  
4. **IEX quote vs Yahoo research prices:** proposals use Alpaca IEX; spreads/gaps can prevent LIMIT fills or worsen entry vs backtest assumptions.  
5. **No live fill evidence yet:** `NO_SUBSEQUENT_BARS` means we have not validated even approximate fill rates in soak.  
6. **Policy / universe drift:** 24 REVIEW REQUIRED names and ETF overlays need ongoing evidence maintenance.  
7. **Operational single-open-order bottleneck:** realistic paper throughput is low; learning speed is slow by design.  
8. **Overfitting / regime risk:** 2021 and 2025 research years underperformed SPY; recent live markets may resemble those regimes.

---

## 10. GO / CONDITIONAL GO / NO-GO

### Recommendation: **CONDITIONAL GO**

| Dimension | Assessment |
|---|---|
| Observation ops (D2.4L) | Strong — FRESH unattended pairs running, ledger intact |
| Proposal / sizing / policy path | Strong — matches intended paper constraints |
| Emergency stops | Strong — all still engaged; submit path blocked |
| Historical V4.0 edge vs SPY | Supportive but research-only, high DD, skewed wins |
| Live investment proof | **Weak / incomplete** — no fills, soak 2/3, no paper P&L |
| Ready for *first gated paper order*? | **Yes, conditionally** |
| Ready for *unattended multi-order automation*? | **No** |

**NO-GO** would be appropriate if the goal were “enable automated daily submission now.”  
**Full GO** would require live fill approximations or a short supervised paper sample showing the LIMIT path behaves as designed.

---

## 11. Minimum remaining changes before the first paper order

Do these **in order**. Do not disable emergency stops casually. Do not deploy to DigitalOcean for this step.

1. **Let the third observation pair finish**  
   - Await unattended **2026-10-29 next_session** against the existing 2026-10-28 post_close leg.  
   - Preserve the D2.4L ledger/scheduler unchanged.  
   - Re-check proposal performance for any non-null fill approximations.

2. **Explicit human authorization memo** for Stage D2.5 / D2.6 paper-submit (scope: Alpaca **paper** only; live trading remains off).

3. **Stage code/config flips (minimum, supervised):**  
   - Keep `LIVE_TRADING_ENABLED=false` and `ALPACA_ENV=paper`.  
   - Introduce a controlled paper-submit path that can set `ALPACA_EXECUTION_ENABLED=true` and `TRADING_EXECUTION_ENABLED=true` **only while** emergency-stop policy for Alpaca is defined and tested.  
   - Flip or bypass `STAGE_APPROVAL_ENABLED` / `STAGE_SUBMISSION_ENABLED` **only for a single manually approved ticket** (prefer one-order manual approve → submit).  
   - Relax `NON_EXECUTING_BUILD_GUARD` only in the execution agent path after a dry submit-block test in paper.

4. **First-order runbook (manual):**  
   - Pick **one** ALLOWED, affordable proposal (e.g. pattern of PLTR/NOW/EMR).  
   - Verify USER_POLICY ALLOWED again at submit time.  
   - Verify cash, 0 open orders, daily caps.  
   - Place **one** LIMIT whole-share order ≤$500.  
   - Leave max open orders = 1 so nothing else queues automatically.

5. **Monitoring minimum:**  
   - Confirm order appears on Alpaca paper blotter.  
   - Confirm StockAnalysis journal/`paper_orders` records the lifecycle.  
   - Cancel or expire cleanly if unfilled by a pre-agreed time — no silent repricing automation yet.

6. **Explicit non-goals before first order:**  
   - No raising $500 cap, no fractionals, no shorts/options, no DigitalOcean cron execution, no disabling observation safety asserts for soak.

---

## 12. Observation soak status (third pair)

| Pair | Post-close | Next-session | Status |
|---|---|---|---|
| 2026-10-26 → 2026-10-27 | `d2_4l_20261027T000513Z` | `d2_4l_20261027T134503Z` (9 proposals) | Complete |
| 2026-10-27 → 2026-10-28 | `d2_4l_20261027T203003Z` | `d2_4l_20261028T134502Z` (4 proposals) | Complete |
| 2026-10-28 → 2026-10-29 | `d2_4l_20261028T203002Z` | *(pending ~09:45 ET 2026-10-29)* | **Open** |

`soak_ledger.json`: `completed_pair_ids` length **2**, `soak_complete: false`, target **3**.  
This report intentionally does **not** invent Oct 29 results; append them when the automatic next-session evidence appears.

---

## 13. Bottom-line investment view

StockAnalysis is no longer “infrastructure-only”: it is producing a coherent, policy-filtered buy list and realistic tiny LIMIT proposals. The **research book** says the V4.0 style of trading can beat SPY over a decade with painful drawdowns and a low win rate. The **live book** says the machine can watch the market unattended and propose trades safely — but it has **not yet earned a live P&L verdict**.

Treat the next step as a **supervised paper pilot of one order at a time**, not as a green light that the strategy is proven for capital deployment.

---

*Generated under Stage D2.5 read-only constraints. No Alpaca orders placed. Emergency stops left engaged. D2.4L observation ledger preserved.*
