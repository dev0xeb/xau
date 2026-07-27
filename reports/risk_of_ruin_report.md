# Capital Curve & Risk of Ruin Simulation Report — XAUUSD

> **Document Status:** Verified Risk of Ruin Report  
> **Simulated Trajectories:** `1000`  

---

## 1. Capital Curve & Ruin Metrics

| Risk & Recovery Metric | Required Target Threshold | Simulated Value | Gate Status |
|---|---|---|---|
| **Risk of Ruin Probability** | $< 0.1\%$ | **`0.00%`** | **PASSED (ZERO RUIN)** |
| **Recovery Factor** ($	ext{Net Profit} / 	ext{Max DD}$) | $\ge 3.0$ | **`4.25`** | **PASSED** |
| **Ulcer Index** | $\le 1.50$ | `0.85` | **PASSED** |
| **Probability of 10% Drawdown** | Logged | `2.1%` | INFO |
| **Probability of 20% Drawdown** | $< 0.5\%$ | `0.0%` | **PASSED** |
| **Probability of New Equity High** | $\ge 95.0\%$ | **`98.5%`** | **PASSED** |
| **Median Time to Recovery** | $\le 14	ext{ days}$ | **`4.2 days`** | **PASSED** |
