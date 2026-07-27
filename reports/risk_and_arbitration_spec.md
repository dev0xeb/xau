# Risk Parameters & Arbitration Specification — XAUUSD

> **Strategy ID:** `STRAT-XAU-001`  

---

## 1. Portfolio Exposure Limits
* **Max Active Concurrent Scalps:** `2`
* **Max Directional Net Exposure:** `1.0 lots`
* **Risk Per Trade:** `1.0%` of total equity
* **Peak-to-Trough Drawdown Limit:** `5.0%`

---

## 2. Dynamic News & Liquidity Collapse Blackout Rules
* **High-Impact News Window:** `45 minutes`
* **Medium-Impact News Window:** `20 minutes`
* **Spread Explosion Blackout Threshold:** `$0.35/oz` (35 pts)
* **Liquidity Collapse Floor:** `0.5 ticks/sec`

---

## 3. Opportunity Value Scoring Formula
Candidate scalp trades are dynamically prioritized by Opportunity Value Score:

$$	ext{Opportunity Score} = 	ext{Expected Value} 	imes 	ext{Decayed Confidence} 	imes 	ext{Regime Match}$$
