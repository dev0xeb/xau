# Data Quality Audit Specification — XAUUSD Scalp Lab

> **Document Status:** Quality Gate Specification  
> **Target Asset:** XAUUSD Tick & M1 Datasets  
> **Purpose:** Quantitative rejection thresholds for invalid or corrupt data  

---

## 1. Quality Gate Principles

No raw dataset may enter `data/processed/` or be utilized for statistical edge discovery without passing all quantitative quality checks specified herein. An audit report must be generated and logged alongside dataset metadata in `data/metadata/`.

---

## 2. Quantitative Audit Checks & Thresholds

| Audit Category | Verification Method | Rejection Threshold | Action on Failure |
|---|---|---|---|
| **Timestamp Monotonicity** | Check `t[i] > t[i-1]` | Any negative time step (`t[i] <= t[i-1]`) | Auto-sort if duplicate/unsorted; reject if timestamps non-recoverable |
| **Duplicate Ticks** | Check for identical timestamp + bid + ask | > 0.05% duplicate entries | Deduplicate automatically; log warning if count > 0 |
| **Negative / Zero Spread** | Check `ask > bid` | `ask - bid <= 0` | Flag as corrupt tick; reject tick |
| **Extreme Spread Spikes** | Check `spread > max_allowed_spread` | Spread > $3.00 (300 pips/points in XAUUSD) | Flag tick/candle as anomalous; log event |
| **Price Outliers / Bad Ticks** | Check price percentage change relative to rolling window | Single tick change > 1.5% without multi-tick volume continuity | Flag as outlier spike; reject corrupt tick |
| **Missing M1 Bar Gaps** | Check expected 1-minute continuity during active market hours | Missing > 10 consecutive M1 bars outside weekend closures | Log gap event; reject period for high-frequency testing |
| **Zero Volume Candles** | Check `tick_volume == 0` during active trading sessions | > 1.0% zero-volume bars during London/NY sessions | Log anomaly |

---

## 3. Audit Scoring & Dataset Certification

Every audited dataset is assigned a **Data Quality Score (0–100%)**:

$$\text{Quality Score} = 100\% - \left( \frac{\text{Corrupt Rows} + \text{Spread Anomalies} + \text{Unresolved Gaps}}{\text{Total Rows}} \times 100\% \right)$$

* **Score >= 99.5%:** Certified for canonical research pipelines (`data/processed/`).
* **Score < 99.5%:** Quarantined in `data/raw/` with audit warning report. Requires manual review or re-acquisition.

---

## 4. Output Audit Reports

The audit engine (`scripts/audit_data_quality.py`) outputs a structured JSON report to `reports/audit_<dataset_id>.json` containing row counts, anomaly counts, gap distributions, and final certification status.
