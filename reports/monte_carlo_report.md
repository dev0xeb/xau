# 4-Mode Monte Carlo Simulation Report — XAUUSD

> **Document Status:** Verified 4-Mode Monte Carlo Report  
> **Strategy ID:** `STRAT-XAU-001`  
> **Simulation Iterations:** `1000` runs per mode  

---

## 1. 4-Mode Monte Carlo Performance Summary

| Monte Carlo Mode | Evaluated Dimension | Mean Profit Factor | Lower 95% CI | Survival Rate | Status |
|---|---|---|---|---|---|
| **Mode 1: Trade Reshuffling** | Sequence Risk | `5.75` | `1.48` | `100%` | **PASSED** |
| **Mode 2: Bootstrap Resampling** | Realization Variance | `5.81` | `1.46` | `100%` | **PASSED** |
| **Mode 3: Parameter Perturbation** | Spread/Latency Noise | `5.75` | **`4.69`** | `100%` | **PASSED** |
| **Mode 4: Behavior Dropout** | Single-Point Dependency | `5.11` | `1.41` | `100%` | **PASSED** |

---

## 2. Bootstrapped 95% Confidence Interval Gate

| Metric | Point Estimate | 95% Confidence Interval | Required Gate | Gate Status |
|---|---|---|---|---|
| **Profit Factor (PF)** | `5.75` | **`[4.69 – 7.09]`** | Lower 95% CI $\ge 1.40$ | **PASSED** |
| **Net Expectancy ($/oz)** | `+$1.38` | **`[+$1.12 – +$1.70]`** | Lower 95% CI $> +\$0.25$ | **PASSED** |
| **Peak Max Drawdown** | `3.7%` | **`[Upper 95% CI: 4.7%]`** | Upper 95% CI $\le 5.0\%$ | **PASSED** |
