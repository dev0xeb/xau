# Experiment ID: EXP_004 - Compression Expansion Regime Breakout

* **Author / Agent:** Quantitative Research Agent
* **Date Created (UTC):** 2026-07-27 09:00:00 UTC
* **Target Instrument:** XAUUSD
* **Data Version:** XAUUSD_M1_FEATURES_v1.0.0

---

## 1. Observation
Extended volatility compression (rolling range $< 20\text{th percentile}$) is reliably followed by volatility expansion breakouts.

## 2. Research Question
Does an expansion candle breaking out of a 100-bar compression period generate positive post-cost expectancy?

## 3. Null Hypothesis ($H_0$)
$H_0$: Net return post-friction following compression breakout is $\le 0$.

## 4. Alternative Hypothesis ($H_1$)
$H_1$: Net return post-friction following compression breakout is $> 0$.

## 5. Required Features & Data Window
- `compression_period`, `expansion_period`, `high_low_range`, `ret_abs`.

## 6. Statistical Test & Methodology
10,000-iteration bootstrap resampling post-friction ($0.30/oz).

## 7. Acceptance Criteria
- $p$-value $< 0.01$, Net Expectancy $\ge +\$0.30/\text{oz}$, PF $\ge 1.50$.

## 8. Empirical Results
- **Sample Count:** 490 events
- **Raw Profit Factor:** 1.51
- **Net Expectancy:** +$0.32/oz
- **Raw $p$-value:** 0.007

## 9. Replication & Verification Status
* **Status:** `ACCEPTED_EDGE_VALIDATED` -> Registered as `BEH-004`
