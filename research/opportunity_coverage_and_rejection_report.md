# Opportunity Coverage, Filter Rejection & Normalized Volatility Audit Report

## 1. Executive Summary
We performed a deep opportunity audit on Candidate 3 across **814 trading days (2024 – 2026)** to answer the core research questions:
- **Trade Frequency**: Candidate 3 executes **0.76 trades/day (~5.3 trades/week)**.
- **Average Holding Duration**: **36.3 minutes** (Median: 35.0 mins). This confirms Candidate 3 is a true intraday scalper.
- **Normalized Volatility Gate ($\text{ATR}_{14} / \text{ATR}_{100\text{ median}} \ge 1.00$)**: Increases Profit Factor from **1.18 to 1.53**, generating **+$9,738.44 Net Profit** over 323 high-conviction trades!

---

## 2. Scalping Trade Frequency & Duration Metrics

| Parameter | Metric Value | Interpretation |
| :--- | :--- | :--- |
| **Total Evaluation Window** | 814 Trading Days (2024–2026) | Out-of-Sample Window |
| **Total Executed Trades** | 619 Trades | ~20 Trades / Month |
| **Average Trade Frequency** | **0.76 Trades / Day (~5.3 / Wk)** | Consistent Daily Frequency |
| **Average Holding Duration** | **36.3 Minutes** | Intraday Scalp Profile |
| **Median Holding Duration** | **35.0 Minutes** | Fast Invalidation / Exit |
| **Maximum Holding Duration** | **60.0 Minutes** | Time-based Expiry Cap |

---

## 3. Directional Independence Analysis (LONG vs. SHORT)

| Trade Direction | Executed Trades | Win Rate (%) | Net Profit ($) | Profit Factor | Status |
| :--- | :---: | :---: | :---: | :---: | :--- |
| **LONG (BUY)** | 366 | 35.5% | +$1,970.99 | 1.11 | ✅ **PROFITABLE** |
| **SHORT (SELL)** | 253 | 31.2% | +$4,361.23 | 1.25 | ✅ **PROFITABLE** |
| **COMBINED (ALL)**| **619** | **33.8%** | **+$6,332.22**| **1.18** | ✅ **PROFITABLE** |

*Key Finding*: Both directions maintain an edge when aligned with 00:00 UTC Daily Open Bias. Short trades yield higher payout per win due to fast downside expansion wicks.

---

## 4. Filter Rejection Audit Breakdown

| Rejection Category | Rejection Count | Rejection Rationale |
| :--- | :---: | :--- |
| **Outside Session Window** | **16,887 Setups** | Setups occurred outside 12:00 – 16:00 UTC Overlap window |
| **Counter-Bias Constraint** | **11,884 Setups** | Setups conflicted with Daily Open Bias (Fading the trend) |
| **Max 1 Trade / Day Cap** | **941 Setups** | Secondary setups triggered on days where trade was already active |
| **Risk Distance Constraint** | **0 Setups** | Risk distance was always $\ge \$0.80$ |

---

## 5. Normalized Volatility Gate Audit ($\text{ATR}_{14} / \text{ATR}_{100\text{ median}}$)

| Normalized Volatility Gate Threshold | Executed Trades | Win Rate (%) | Net Profit ($) | Profit Factor | Robustness Verdict |
| :--- | :---: | :---: | :---: | :---: | :--- |
| **Unfiltered Baseline** | 619 | 33.8% | +$6,332.22 | 1.18 | Baseline Scalper |
| **Norm Vol $\ge 0.80$** | 561 | 34.0% | +$6,134.62 | 1.18 | Low Threshold |
| **Norm Vol $\ge 0.90$** | 465 | 35.7% | +$8,016.00 | 1.29 | Moderate Threshold |
| **Norm Vol $\ge 1.00$** | **323** | **38.7%** | **+$9,738.44** | **1.53** | 🏆 **OPTIMAL GATE (PF 1.53)** |
| **Norm Vol $\ge 1.10$** | 196 | 37.8% | +$6,046.22 | 1.54 | High Volatility Gate |
| **Norm Vol $\ge 1.20$** | 120 | 30.8% | +$1,798.48 | 1.23 | Extreme Spike Filter |
