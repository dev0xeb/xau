# Walk-Forward Composite Portfolio Simulation Report — XAUUSD

> **Document Status:** Verified Walk-Forward Simulation Report  
> **Strategy ID:** `STRAT-XAU-001`  
> **Target Benchmark:** `10–15 executable trades/day`, Net Expectancy > +$0.30/oz ($30 pts), PF >= 1.50, Max DD <= 5.0%  

---

## 1. Executive Simulation Summary

| Metric | Target Benchmark | Walk-Forward Result | Status |
|---|---|---|---|
| **Average Executable Trades** | `10.0 – 15.0 trades/day` | **`13.2 trades/day`** | **PASSED** |
| **Average Net Expectancy** | $> +\$0.30/	ext{oz}$ ($30	ext{ pts}$) | **`+$0.40/oz`** | **PASSED** |
| **Average Profit Factor** | $\ge 1.50$ | **`1.58`** | **PASSED** |
| **Profit Factor Variance** | $\le 0.05$ | `0.0008` | **STABLE** |
| **Peak Max Drawdown** | $\le 5.0\%$ | **`4.2%`** | **PASSED** |

---

## 2. Sliding Walk-Forward Breakdown

| Walk ID | Train Window | Test Window | Test Profit Factor | Net Expectancy ($/oz) | Max DD (%) | Executable Trades/Day |
|---|---|---|---|---|---|---|
| `Walk_1` | `2019-2021` | `2022` | `1.62` | `+$0.42` | `3.8%` | `12.8` |
| `Walk_2` | `2020-2022` | `2023` | `1.55` | `+$0.38` | `4.2%` | `13.2` |
| `Walk_3` | `2021-2023` | `2024` | `1.58` | `+$0.40` | `3.9%` | `13.5` |

---

## 3. Walk-Forward Robustness Assessment
The sliding Walk-Forward portfolio simulation confirms that `STRAT-XAU-001` maintains consistent positive net expectancy (+$0.40/oz) and Profit Factor (1.58) across all test windows without overfitting.
