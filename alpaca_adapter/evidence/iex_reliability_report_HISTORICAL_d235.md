# Alpaca IEX Reliability — Historical D2.3B.5 Evidence

**Label:** HISTORICAL REPROCESS — not a live multi-session campaign

Alpaca IEX is a **non-consolidated single-venue** feed (not NBBO). This assessment does **not** establish consolidated quote quality or fill quality.

Execution policy thresholds (unchanged): max spread **0.50%**, max age **30s**, regular US session, positive uncrossed two-sided quotes, future skew ≤ **2s**.

## Session: `HISTORICAL_REPROCESS`
- Source evidence: `iex_validation_20261024_0045.json`
- Market session at run: n/a
- Feed connectivity: **PASS**
- All fresh within 30s: **True**
- Overall execution suitability: **FAIL**
- Orders placed during verification: **0**

| Symbol | Recv/Att | Feed% | Fresh% | Spread% | Exec% | Spread med | Age med |
|---|---:|---:|---:|---:|---:|---:|---:|
| AAPL | 3/3 | 100.00% | 100.00% | 66.67% | 66.67% | 0.4430 | 0.7200 |
| MSFT | 3/3 | 100.00% | 100.00% | 33.33% | 33.33% | 1.9190 | 3.3600 |
| SPY | 3/3 | 100.00% | 100.00% | 100.00% | 100.00% | 0.0160 | 0.3700 |

## Interpretation notes

- Treat missing sessions (machine off / API failure / holiday) as **inconclusive**, not PASS.
- Do **not** relax the 0.50% spread threshold to manufacture a PASS.
- High early-session spread volatility on single-name IEX books is expected; SPY often tighter than AAPL/MSFT.
- A market-data reliability PASS does **not** authorize paper or live trading.
