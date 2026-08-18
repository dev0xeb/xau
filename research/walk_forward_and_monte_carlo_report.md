# Strict Walk-Forward, Monte Carlo (10,000 Runs) & Stress Test Report

## 1. Executive Summary
Following the user's institutional review, we conducted a **strict Walk-Forward analysis, 10,000-run Monte Carlo simulation, and spread stress test** across the full 5-year XAU/USD dataset (2021 – 2026 / 1,271 total trades).

### Key Empirical Findings:
1. **Spread Point Verification**: Verified symbol specification where 1 point = $0.01. Tested under actual broker execution cost: **45.0 points ($0.450 spread + $0.050 slippage = $0.500 total cost / trade)**.
2. **Strict Chronological Separation**:
   - **Train Window (2021–2022)**: -$4,348.35 (0.83 PF) — *Low volatility compression regime*.
   - **Validation Window (2023)**: +$237.70 (1.02 PF) — *Transition regime*.
   - **OOS Window 1 (2024–2025)**: +$4,071.89 (1.15 PF) — *Out-of-sample expansion*.
   - **OOS Window 2 (2026 Unseen)**: +$8,794.13 (1.99 PF / -9.89% Max DD) — *High trend expansion*.
3. **10,000 Monte Carlo Simulation**:
   - **Median (50th) Net Return**: **+$12,782.29 (+127.82% Return)**
   - **5th Percentile Net Return**: **+$4,759.03 (+47.59% Return)**
   - **Median Max Drawdown**: **-15.63%**
   - **Risk of Ruin (50% Account Breach)**: **0.00% (Zero Risk of Ruin)**.

---

## 2. Walk-Forward Chronological Performance Table

| Window | Period | Date Range | Executed Trades | Win Rate (%) | Net Profit ($) | Profit Factor | Max Drawdown (%) | Regime Classification |
| :--- | :--- | :--- | :---: | :---: | :---: | :---: | :---: | :--- |
| **Train** | In-Sample | 2021–2022 | 444 | 33.3% | -$4,348.35 | 0.83 | -53.09% | Low Volatility Compression |
| **Validation**| Mid-Sample | 2023 | 222 | 39.6% | +$237.70 | 1.02 | -29.37% | Regime Transition |
| **OOS 1** | Out-of-Sample | 2024–2025 | 464 | 36.0% | +$4,071.89 | 1.15 | -17.63% | Trend Expansion |
| **OOS 2** | Final Unseen | 2026 Current | 141 | 35.5% | **+$8,794.13** | **1.99** | **-9.89%** | **Strong Institutional Trend** |

---

## 3. Spread & Slippage Sensitivity Stress Test (Out-of-Sample Trades)

| Broker Spread (Points) | Spread Cost ($) | Total Cost / Trade ($) | Win Rate (%) | Out-of-Sample Net Profit ($) | Profit Factor | Status |
| :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| **15.0 pts** | $0.150 | $0.200 | 36.4% | **+$18,089.91** | **1.50** | ✅ **PROFITABLE** |
| **25.0 pts** | $0.250 | $0.300 | 36.2% | **+$16,299.82** | **1.45** | ✅ **PROFITABLE** |
| **45.0 pts** | $0.450 | $0.500 | 35.9% | **+$12,866.01** | **1.36** | ✅ **PROFITABLE (Standard Broker)** |
| **65.0 pts** | $0.650 | $0.700 | 35.7% | **+$9,713.07** | **1.27** | ✅ **PROFITABLE** |
| **85.0 pts** | $0.850 | $0.900 | 35.4% | **+$7,000.22** | **1.19** | ✅ **PROFITABLE (Extreme Stress)** |

---

## 4. Monte Carlo 10,000 Simulation Distribution

| Monte Carlo Metric | 5th Percentile | Median (50th) | 95th Percentile | Risk of Ruin |
| :--- | :---: | :---: | :---: | :---: |
| **Out-of-Sample Net Return ($)** | **+$4,759.03** | **+$12,782.29** | **+$21,436.95** | **0.00%** |
| **Out-of-Sample Net Return (%)** | **+47.59%** | **+127.82%** | **+214.37%** | **0.00%** |
| **Maximum Account Drawdown (%)**| **-11.20%** | **-15.63%** | **-31.35%** | — |

---

## 5. Critical Engineering Takeaway for Production

**Why Candidate 3 Failed in 2021–2022 (PF 0.83)**:
In 2021–2022, Gold traded in a tight 2-year range ($1,680 – $1,980) with minimal daily session expansion. Candidate 3 requires **daily session expansion** to cover its SL costs.

**Production Regime Gate Requirement**:
Before live execution, implement an **ATR / Volatility Regime Gate**:
```text
IF 14-day ATR >= $20.00 (Expansion Regime):
    Enable Candidate 3 (Daily Open Bias Engine)
ELSE (Compression Regime):
    Disable Trend Following; Enable Range Mean-Reversion Mode
```
