# USER_POLICY Correction — PLTR Excluded (Military / Defence Exposure)

**Date:** 2026-10-29  
**Orders submitted:** 0  
**Execution flags:** unchanged (Alpaca execution remains disabled; emergency stops intact)

## Change

PLTR (Palantir Technologies) is now **EXCLUDED** under USER_POLICY with reason code **`MILITARY_DEFENCE_EXPOSURE`** (also tagged `POLICY_EXCLUDED_WEAPONS_DEFENCE`).

| Surface | Behaviour |
|---|---|
| Research / 227-stock scan universe | **Retained** — `research_visible=True` |
| Eligible BUY / proposals / paper / live orders | **Blocked** |
| Historical observation bundles | **Unchanged** — annotated as policy-ineligible |

## Eligible BUY count (re-eval of 2026-10-28 post-close)

| Metric | Count |
|---|---:|
| Historical BUY CANDIDATES in bundle | 32 |
| Eligible under corrected USER_POLICY | **27** |
| BUY names now EXCLUDED | SPY, MS, MO, XLP, **PLTR** |

**Eligible tickers (27):** AMD, NOW, INTC, CRWD, MSFT, ZS, PYPL, CSCO, TSM, TXN, MU, DHR, GILD, ELV, CI, V, CB, ROST, DG, EMR, XOM, COP, MPC, KMI, APD, NUE, SOXX

## Historical PLTR proposals (annotated, not mutated)

| Bundle | Day | Proposal |
|---|---|---|
| `d2_4l_20261027T000828Z` | 2026-10-26 | PLTR 2 × $208.06 = $416.12 (pilot_rank 2) |
| `d2_4l_20261028T134502Z` | 2026-10-28 | PLTR 2 × $197.48 = $394.96 (pilot_rank 1) |

Annotation: **POLICY_INELIGIBLE** under current USER_POLICY. Records left intact.

## Additional companies for manual review (not auto-excluded)

Currently still ALLOWED among BUY candidates, but flagged for human review of military / defence / intelligence exposure:

| Ticker | Why review |
|---|---|
| CRWD | Cybersecurity with material government/defence customers |
| ZS | Public-sector / defence zero-trust customers |
| CSCO | Networking sold into government & defence networks |
| TXN | Semiconductors with aerospace/defence end markets |
| EMR | Industrial automation; possible dual-use / government exposure |
| MSFT | Commercial cloud with known defence/public-sector contracts |

Do **not** auto-approve these as “clear” of rule 3 without documented evidence; leave as ALLOWED until manual decision.

## Gates & tests

- Explicit exclusion: `EXPLICIT_ACTIVITY_EVIDENCE["PLTR"]`
- Overlay sync: `CRM_PLTR_OVERLAYS["PLTR"]` → EXCLUDED
- Proposal path: `BuyDecisionEngine` / `assert_user_policy_order_permitted` / risk `user_policy_eligibility`
- Submission path: `AlpacaExecutionAgent.execute_paper_order` USER_POLICY reject before submit
- Tests: `tests/test_user_policy_pltr_exclusion.py` (+ updated D2.4I/J expectations)

Audit JSON: under `data_cache/evidence/user_policy_pltr_exclusion_*/PLTR_POLICY_EXCLUSION_AUDIT.json`
