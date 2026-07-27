# Success Metrics & Edge Benchmarks — XAUUSD Scalp Lab

> **Document Status:** Statistical Evaluation Standard  
> **Target Asset:** XAUUSD Intraday Scalping  
> **Canonical Target Benchmark:** Average 10–15 executed XAUUSD intraday trades per day, with positive expectancy after spread, slippage, and latency over a statistically meaningful validation window.

---

## 1. Unit & Measurement Standards

To prevent ambiguity when evaluating Maximum Favorable Excursion (MFE), Maximum Adverse Excursion (MAE), Stop Loss (SL), and Take Profit (TP), price units in Gold (`XAUUSD`) are defined as follows:

| Term / Unit | Definition | Numerical Value | Example |
|---|---|---|---|
| **USD / oz** | Price in USD per Troy Ounce | Primary Price Unit | `$2350.50` |
| **Point (pt)** | Minimum tick increment ($0.01) | `$0.01` per oz | `$2350.50 \to \$2350.51` = 1 point |
| **Pip / Big Point** | Standard broker pip convention ($0.10) | `$0.10` per oz (10 pts) | `$2350.50 \to \$2350.60` = 1 pip |

All statistical expectancy calculations in this laboratory are expressed natively in **USD per troy ounce ($\text{USD/oz}$)**.

---

## 2. Frequency Measurement Protocol

Trade frequency ($N_{\text{daily}}$) is evaluated as a **rolling average or median over a 20–30 trading day validation sample**, avoiding false rejections due to quiet market regimes, bank holidays, or low-volatility sessions:

$$\bar{N}_{\text{daily}} = \frac{1}{W} \sum_{d=1}^{W} N_d \quad \text{where } W \in [20, 30] \text{ trading days}$$

---

## 3. Tiered Performance Framework

All statistical edges discovered in this laboratory are evaluated against a three-tiered performance hierarchy:

```text
┌─────────────────────────────────────────────────────────────┐
│                    STRETCH GOAL                             │
│ Avg 12–20 trades/day | PF ≥ 1.80 | Sharpe ≥ 3.5 | DD ≤ 3.5%  │
├─────────────────────────────────────────────────────────────┤
│                  TARGET PERFORMANCE                         │
│ Avg 10–15 trades/day | Net Expectancy +$0.30–$0.50/oz | PF≥1.50│
├─────────────────────────────────────────────────────────────┤
│                 MINIMUM VIABILITY FLOOR                     │
│ Avg ≥ 5 trades/day | Net Expectancy > +$0.15/oz | PF ≥ 1.25  │
└─────────────────────────────────────────────────────────────┘
```

---

## 4. Quantitative Metric Specifications by Tier

### Tier 1: Minimum Viability Floor
* **Purpose:** Statistical proof that an edge exists above random noise.
* **Trade Frequency ($\bar{N}_{\text{daily}}$):** $\ge 5\text{ executed trades/day}$ (20-day rolling avg).
* **Net Expectancy ($E_{\text{net}}$):** $> +\$0.15/\text{oz}$ ($15\text{ pts}$) post-friction.
* **Profit Factor (Gross Wins / Gross Losses):** $\ge 1.25$
* **Statistical Significance:** $p < 0.05$ (Student's t-test / bootstrap resampling).
* **Action:** Eligible for further refinement; NOT eligible for live/demo strategy deployment.

### Tier 2: Target Performance Bar (Aggressive Scalper Benchmark)
* **Purpose:** Satisfies the core laboratory mandate for high-frequency aggressive scalping.
* **Trade Frequency ($\bar{N}_{\text{daily}}$):** **Average 10–15 executed intraday trades per day** (20–30 day rolling sample).
* **Net Expectancy ($E_{\text{net}}$):** **$+\$0.30\text{ to } +\$0.50/\text{oz}$** ($30–50\text{ pts}$) post-friction.
* **Profit Factor:** $\ge 1.50$
* **Sharpe Ratio (Annualized intraday basis):** $\ge 2.50$
* **Maximum Drawdown:** $\le 5.0\%$ of equity curve in simulation.
* **Statistical Significance:** $p < 0.01$ across $\ge 60$ trading days.
* **Regime Stability:** Positive expectancy across at least 2 of 3 major trading sessions (London, NY, Asian).
* **Action:** Eligible for behavior registry certification & execution pipeline design.

### Tier 3: Stretch Goal / Demo Progression Bar
* **Purpose:** Outstanding edge quality justifying immediate live demo deployment.
* **Trade Frequency ($\bar{N}_{\text{daily}}$):** Average $12–20\text{ executed trades/day}$.
* **Net Expectancy ($E_{\text{net}}$):** $> +\$0.50/\text{oz}$ ($50\text{ pts}$) post-friction.
* **Profit Factor:** $\ge 1.80$
* **Sharpe Ratio:** $\ge 3.50$
* **Sortino Ratio:** $\ge 4.50$
* **Maximum Drawdown:** $\le 3.5\%$
* **Regime Stability:** Positive expectancy across ALL 3 sessions (London, NY, Asian).
* **Action:** Priority candidate for automated live-demo execution testing.

---

## 5. Standard Friction Baseline (XAUUSD)

All net expectancy calculations ($E_{\text{net}}$) subtract real-world execution friction:

$$E_{\text{net}} = \frac{1}{N} \sum_{k=1}^{N} \left( \Delta P_k - \text{Spread}_k - \text{Slippage}_k - \text{Commission}_k \right)$$

* **Average Bid-Ask Spread:** $\$0.15–\$0.25/\text{oz}$ ($15–25\text{ pts}$)
* **Execution Slippage:** $\$0.05–\$0.10/\text{oz}$ ($5–10\text{ pts}$)
* **Commission:** $\$0.05/\text{oz}$ round-turn equivalent ($5\text{ pts}$)
* **Mandatory Total Friction Deduction:** **$\$0.25–\$0.40/\text{oz}$ per scalp trade** ($25–40\text{ pts}$)
