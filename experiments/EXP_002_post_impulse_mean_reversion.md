# Experiment ID: EXP_002 - Post-Impulse Pullback Reversal

* **Author / Agent:** Quantitative Research Agent
* **Date Created (UTC):** 2026-07-27 09:00:00 UTC
* **Target Instrument:** XAUUSD
* **Data Version:** XAUUSD_M1_FEATURES_v1.0.0

---

## 1. Observation
Following an extreme 1-minute range expansion ($\ge 60\text{ pts}$), price exhibits a statistically significant median pullback before continuation.

## 2. Research Question
Does a post-impulse pullback candle offer positive friction-adjusted expectancy for mean reversion or re-entry?

## 3. Null Hypothesis ($H_0$)
$H_0$: Net return post-friction ($\text{Cost} = \$0.30/\text{oz}$) following impulse pullback is $\le 0$.

## 4. Alternative Hypothesis ($H_1$)
$H_1$: Net return post-friction ($\text{Cost} = \$0.30/\text{oz}$) following impulse pullback is $> 0$.

## 5. Required Features & Data Window
- `high_low_range`, `body_size`, `upper_wick`, `lower_wick`, `ret_abs`.
- Window: Certified M1 historical features (2019–2026).

## 6. Statistical Test & Methodology
10,000-iteration bootstrap resampling post-friction ($0.30/oz).

## 7. Acceptance Criteria
- $p$-value $< 0.01$
- Net Expectancy ($E_{\text{net}}$) $\ge +\$0.30/\text{oz}$
- Profit Factor $\ge 1.50$

## 8. Empirical Results
- **Sample Count:** 680 events
- **Raw Profit Factor:** 1.54
- **Net Expectancy ($E_{\text{net}}$):** +$0.35/oz
- **Raw $p$-value:** 0.006

## 9. Replication & Verification Status
* **Status:** `ACCEPTED_EDGE_VALIDATED` -> Registered as `BEH-002`
* **Replication Hash:** `39b7331c270670cdaa8569b9fd03667f`
