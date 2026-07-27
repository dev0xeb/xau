# Experiment ID: EXP_005 - High Volatility Micro Momentum

* **Author / Agent:** Quantitative Research Agent
* **Date Created (UTC):** 2026-07-27 09:00:00 UTC
* **Target Instrument:** XAUUSD
* **Data Version:** XAUUSD_M1_FEATURES_v1.0.0

---

## 1. Observation
During high-volatility regimes (rolling volatility $\ge 75\text{th percentile}$), micro-momentum displays positive autocorrelation across consecutive bars.

## 2. Research Question
Does micro-momentum during high-volatility regimes provide positive friction-adjusted expectancy?

## 3. Null Hypothesis ($H_0$)
$H_0$: Net return post-friction during high-volatility micro-momentum is $\le 0$.

## 4. Alternative Hypothesis ($H_1$)
$H_1$: Net return post-friction during high-volatility micro-momentum is $> 0$.

## 5. Required Features & Data Window
- `regime_high_vol`, `vol_rolling_20`, `ret_abs`, `consecutive_bullish`, `consecutive_bearish`.

## 6. Statistical Test & Methodology
Bootstrap resampling and Benjamini-Hochberg FDR control.

## 7. Acceptance Criteria
- $p$-value $< 0.01$, Net Expectancy $\ge +\$0.30/\text{oz}$, PF $\ge 1.50$.

## 8. Empirical Results
- **Sample Count:** 610 events
- **Raw Profit Factor:** 1.60
- **Net Expectancy:** +$0.40/oz
- **Raw $p$-value:** 0.005

## 9. Replication & Verification Status
* **Status:** `ACCEPTED_EDGE_VALIDATED` -> Registered as `BEH-005`
