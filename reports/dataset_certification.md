# DATASET CERTIFICATION SEAL

> **Official Research Dataset Certification Report**

* **Dataset File:** `data/processed/features/XAUUSD_M1_features.parquet`
* **SHA256 Checksum:** `cb7c2bc2ab2c4d769d7b087f0b7e47f4c9a3f19debb185e344a3857a7b8d5842`
* **Certification Date (UTC):** 2026-07-27T08:45:17.174566+00:00
* **Coverage Window:** `2024-01-02 08:00:00+00:00` to `2024-01-02 08:09:00+00:00`
* **Total Rows:** `10` | **Total Features:** `56`

---

## Audit Checklist & Metrics

| Audit Criterion | Result Metric | Threshold | Status |
|---|---|---|---|
| **UTC Monotonicity** | 0 violations | 0 violations | PASS |
| **Duplicate Timestamps** | 0 duplicates | 0 duplicates | PASS |
| **Price Validity** | 0 invalid prices | 0 invalid prices | PASS |
| **Spread Integrity** | 0 zero/neg spreads | 0 violations | PASS |
| **Spread Spikes** | 0 spikes (> $3.00) | Logged | INFO |
| **NaN Price Values** | 0 NaNs | 0 NaNs | PASS |
| **Final Quality Score** | **100.00%** | **>= 95.0%** | **CERTIFIED** |

---

## Lineage Metadata Manifest
```json
{
  "dataset_file": "data/processed/features/XAUUSD_M1_features.parquet",
  "sha256_checksum": "cb7c2bc2ab2c4d769d7b087f0b7e47f4c9a3f19debb185e344a3857a7b8d5842",
  "validation_timestamp_utc": "2026-07-27T08:45:17.174566+00:00",
  "total_rows": 10,
  "total_columns": 56,
  "date_range": {
    "start_utc": "2024-01-02 08:00:00+00:00",
    "end_utc": "2024-01-02 08:09:00+00:00"
  },
  "metrics": {
    "monotonicity_violations": 0,
    "duplicate_timestamps": 0,
    "invalid_prices": 0,
    "spread_violations": 0,
    "extreme_spread_spikes": 0,
    "nan_price_values": 0,
    "total_corrupt_records": 0
  },
  "quality_score": 100.0,
  "is_certified": true
}
```
