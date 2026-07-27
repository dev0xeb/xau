# Portfolio Decision Engine Summary — XAUUSD

> **Document Status:** Verified Portfolio Decision Engine Summary  
> **Total Candidates Generated:** `13`  

---

## 1. 5-Tier Opportunity Ranking Breakdown

| Tier Classification | Score Range | Decision Code | Action Status | Candidate Count |
|---|---|---|---|---|
| **Priority Execute** | `90.0 – 100.0` | `EXECUTE` | Adaptive Risk 1.5% | `0` |
| **Ready** | `75.0 – 89.9` | `EXECUTE` | Adaptive Risk 1.0% | `13` |
| **Watch** | `60.0 – 74.9` | `NO_TRADE` | Logged Only | `0` |
| **Ignore** | `40.0 – 59.9` | `NO_TRADE` | Logged Only | `0` |
| **Reject** | `0.0 – 39.9` | `NO_TRADE` | Logged Only | `0` |

---

## 2. Structured `NO_TRADE` Reason Code Distribution
All non-executing candidates explicitly record structured reason codes (`INSUFFICIENT_CONFIDENCE`, `SPREAD_TOO_HIGH`, `REGIME_MISMATCH`, `BEHAVIOR_CONFLICT`, `RISK_EXCEEDED`, `CORRELATION_EXCEEDED`, `NEWS_BLACKOUT`, `PORTFOLIO_EXPOSURE_EXCEEDED`).
