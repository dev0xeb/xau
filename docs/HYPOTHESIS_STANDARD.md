# Hypothesis Standard Template — XAUUSD Scalp Lab

> **Document Status:** Mandatory Research Template  
> **Usage:** Every experiment file created in `experiments/` MUST follow this exact 9-point structure.

---

# Experiment ID: `EXP_XXX_[SHORT_TITLE]`

* **Author / Agent:**  
* **Date Created (UTC):**  
* **Target Instrument:** XAUUSD  
* **Data Version:**  

---

## 1. Observation
*Describe the empirical observation or market phenomenon in XAUUSD tick/M1 data that inspired this hypothesis (e.g. liquidity sweep after initial London open range breakout).*

## 2. Research Question
*State the precise quantitative question being evaluated.*

## 3. Null Hypothesis ($H_0$)
*State the null hypothesis (e.g., $H_0$: Net return following trigger $X$ is $\le 0$ post-cost).*

## 4. Alternative Hypothesis ($H_1$)
*State the alternative hypothesis (e.g., $H_1$: Net return following trigger $X$ is $> 0$ post-cost).*

## 5. Required Features & Data Window
*Specify the exact features, bar intervals (Tick/M1), and historical date range required to test the hypothesis.*

## 6. Statistical Test & Methodology
*Define the statistical test method (e.g., Welch's t-test, Mann-Whitney U, 10,000-iteration bootstrap resampling) and friction parameters applied.*

## 7. Acceptance Criteria
*List the precise mathematical criteria required to accept $H_1$ (e.g., $p < 0.01$, Net Expectancy $> +\$0.15$, $N_{\text{trades/day}} \ge 10$).*

## 8. Empirical Results
*Record test statistics, p-values, sample sizes, distribution plots, and cost-adjusted expectancy.*

## 9. Replication & Verification Status
* **Status:** `[PENDING | REJECTED_H0_ACCEPTED | ACCEPTED_EDGE_VALIDATED]`
* **In-Sample Period:**  
* **Out-of-Sample Period:**  
* **Replication Hash:**  
