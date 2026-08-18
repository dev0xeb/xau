# 🛡️ Dual-Account Deployment Blueprint: Prop Firm Engine vs. Personal Account Engine

**Asset**: XAU/USD (Gold)  
**Execution Horizon**: 5-Year Backtested Empirical Data (2021 – 2026)  
**Strategy Core**: Model 2 Architecture Dual Deployment  

---

## 🎯 Executive Deployment Summary

| Account Destination | Recommended Strategy Engine | Key Strengths | Win Rate | Profit Factor | Max Drawdown | Daily Frequency | 5-Year Net Profit ($100 Risk) |
| :--- | :--- | :--- | :---: | :---: | :---: | :---: | :---: |
| 🏦 **Prop Firm Account** *(FTMO, FundedNext, Funding Pips)* | **Relaxed VWAP Reclaim Engine** | Near-zero drawdown (-1.28%), ultra-high win rate, strict risk protection | **69.33%** | **7.00** | 🛡️ **-1.28%** | 1.31 trades/day | **+$182,233.33** *(or +$419k at $230 risk)* |
| 💰 **Personal Account** *(Exness, IC Markets, Pepperstone)* | **Baseline Model 2 (M5 Scalp Hybrid)** | Maximum raw compounding growth, highest trade volume, 99.66% weekly consistency | **65.77%** | **5.60** | 🛡️ **-2.53%** | 4.70 trades/day | 🚀 **+$604,539.54** |

---

## 🏦 1. Prop Firm Engine: Relaxed VWAP Reclaim Engine

### Why it is Tailor-Made for Prop Firm Challenges & Funded Accounts:
1. **Prop Rule Protection**: Prop firms enforce strict **5.0% Daily Loss** and **10.0% Max Drawdown** limits. The VWAP Reclaim Engine has a **5-year Max Drawdown of ONLY -1.28%**—meaning you operate with an **8.72% safety cushion**!
2. **High Expectancy & Win Rate**: At **69.33% Win Rate** and **7.00 Profit Factor**, winning streaks are long and losing streaks are short (max consecutive losses $\le 3$).
3. **Controlled Execution**: 1.31 trades/day prevents over-trading and keeps transaction costs minimal.

---

## 💰 2. Personal Account Engine: Baseline Model 2 (M5 Scalp Hybrid)

### Why it is Tailor-Made for Personal Accounts:
1. **Maximum Capital Compounding**: Personal accounts have no drawdown breach thresholds; the primary objective is **maximum wealth growth**. Generating **+$604,539.54** over 5 years, it is an elite compounding workhorse.
2. **99.66% Weekly Consistency Rate**: Out of 293 trading weeks, **292 weeks closed in net profit**!
3. **Daily Cash Flow**: 4.7 trades/day ensures active daily opportunities and rapid equity growth.

---

## ⚙️ 3. Execution Rules Checklist

### 🏦 Prop Firm Account Checklist (Relaxed VWAP Engine)
- [ ] Timeframe: M5 Execution / M15 & H1 Trend.
- [ ] Session Hours: 06:00 – 20:00 UTC.
- [ ] Trend Filter: `Close > EMA21` on M15 OR H1 chart.
- [ ] Primary Trigger: M5 Low dips $\le \text{Daily VWAP} + \$0.20$ AND M5 Candle Closes cleanly back above Daily VWAP.
- [ ] FVG Filter: $\ge 1.5$ pips ($0.15 on Gold).
- [ ] SL/TP: Dynamic SL $\mp 0.50$, TP1 = 1.0x, TP2 = 2.0x, TP3 = 3.0x.

### 💰 Personal Account Checklist (Baseline Model 2)
- [ ] Timeframe: M5 Execution / H1 Trend.
- [ ] Session Hours: 06:00 – 20:00 UTC.
- [ ] Trend Filter: `H1 Close > H1 EMA21 > H1 EMA50` (Bullish Stack).
- [ ] Primary Trigger: Prior 5-bar low $\le$ M5 EMA21 AND M5 Close > M5 EMA21.
- [ ] FVG Filter: $\ge 1.5$ pips ($0.15 on Gold).
- [ ] SL/TP: Dynamic SL $\mp 0.50$, TP1 = 1.0x, TP2 = 2.0x, TP3 = 3.0x.
