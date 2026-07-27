# Parameter Sensitivity & Friction Sweep Report — XAUUSD

> **Document Status:** Verified Parameter Sensitivity Report  
> **Total Scenarios Evaluated:** `200`  
> **Break-Even Spread Limit:** `$0.45 / oz`  
> **Break-Even Latency Limit:** `250 ms`  

---

## 1. Multi-Dimensional Friction Sensitivity Matrix

| Spread ($/oz) | Slippage ($/oz) | Latency (ms) | Total Friction ($/oz) | Net Expectancy ($/oz) | Profit Factor | Status |
|---|---|---|---|---|---|---|
| `$0.10` | `$0.05` | `50 ms` | `$0.15` | `+$0.55` | `1.63` | **PROFITABLE** |
| **`$0.15` (Baseline)** | **`$0.05`** | **`85 ms`** | **`$0.20`** | **`+$0.50`** | **`1.55`** | **PROFITABLE** |
| `$0.25` | `$0.10` | `120 ms` | `$0.36` | `+$0.34` | `1.42` | **PROFITABLE** |
| `$0.35` | `$0.15` | `180 ms` | `$0.51` | `+$0.19` | `1.28` | **MARGINAL** |
| `$0.50` | `$0.25` | `300 ms` | `$0.77` | `-$0.07` | `0.92` | **BREACHED** |
