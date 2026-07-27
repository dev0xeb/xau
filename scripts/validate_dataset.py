#!/usr/bin/env python3
"""
validate_dataset.py - Dataset Quality Validation & Certification Engine

Checks:
- Duplicate timestamps
- Invalid/negative prices
- Spread spikes & zero spreads
- UTC compliance & monotonicity
- NaN values & feature completeness
Outputs JSON reports in data/quality_reports/ and generates reports/dataset_certification.md.
"""

import os
import sys
import json
import hashlib
import argparse
import pandas as pd
from datetime import datetime, timezone

def validate_dataset(input_file: str, report_json: str = None, cert_md: str = None) -> dict:
    if not os.path.exists(input_file):
        raise FileNotFoundError(f"Input dataset file not found: {input_file}")

    print(f"[INFO] Running dataset quality validation on {input_file}...")

    if input_file.endswith(".parquet"):
        df = pd.read_parquet(input_file)
    else:
        df = pd.read_csv(input_file)

    total_rows = len(df)
    if total_rows == 0:
        raise ValueError("Cannot validate an empty dataset.")

    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)

    # 1. Monotonicity check
    ts_diffs = df["timestamp"].diff().dt.total_seconds()
    monotonicity_violations = int((ts_diffs < 0).sum())

    # 2. Duplicate timestamp check
    duplicate_rows = int(df.duplicated(subset=["timestamp"]).sum())

    # 3. Invalid prices (<= 0)
    price_cols = [c for c in ["open", "high", "low", "close", "bid", "ask", "mid"] if c in df.columns]
    invalid_prices = 0
    for col in price_cols:
        invalid_prices += int((df[col] <= 0).sum())

    # 4. Spread checks
    spread_violations = 0
    extreme_spread_spikes = 0
    if "spread" in df.columns:
        spread_violations = int((df["spread"] <= 0).sum())
        extreme_spread_spikes = int((df["spread"] > 3.0).sum())
    elif "bid" in df.columns and "ask" in df.columns:
        spreads = df["ask"] - df["bid"]
        spread_violations = int((spreads <= 0).sum())
        extreme_spread_spikes = int((spreads > 3.0).sum())

    # 5. NaN check
    nan_counts = int(df[price_cols].isna().sum().sum())

    # Total corrupt records & Quality score calculation
    corrupt_count = monotonicity_violations + duplicate_rows + invalid_prices + spread_violations + extreme_spread_spikes + nan_counts
    quality_score = float(max(0.0, round(100.0 - (corrupt_count / total_rows * 100.0), 4)))
    is_certified = bool(quality_score >= 95.0)

    # SHA256 Hash
    sha256 = hashlib.sha256()
    with open(input_file, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            sha256.update(chunk)
    sha256_hash = sha256.hexdigest()

    validation_result = {
        "dataset_file": input_file,
        "sha256_checksum": sha256_hash,
        "validation_timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "total_rows": int(total_rows),
        "total_columns": int(len(df.columns)),
        "date_range": {
            "start_utc": str(df["timestamp"].min()),
            "end_utc": str(df["timestamp"].max())
        },
        "metrics": {
            "monotonicity_violations": monotonicity_violations,
            "duplicate_timestamps": duplicate_rows,
            "invalid_prices": invalid_prices,
            "spread_violations": spread_violations,
            "extreme_spread_spikes": extreme_spread_spikes,
            "nan_price_values": nan_counts,
            "total_corrupt_records": corrupt_count
        },
        "quality_score": quality_score,
        "is_certified": is_certified
    }

    print(f"--- Quality Validation Summary ---")
    print(f"File:               {input_file}")
    print(f"Total Rows:         {total_rows}")
    print(f"Quality Score:      {quality_score}%")
    print(f"Certification:      {'[CERTIFIED >= 95%]' if is_certified else '[REJECTED < 95%]'}")

    # Write JSON report
    if report_json:
        os.makedirs(os.path.dirname(os.path.abspath(report_json)), exist_ok=True)
        with open(report_json, "w") as f:
            json.dump(validation_result, f, indent=2)
        print(f"[INFO] Validation JSON report saved to {report_json}")

    # Write Markdown certification report
    cert_path = cert_md or os.path.join("reports", "dataset_certification.md")
    os.makedirs(os.path.dirname(os.path.abspath(cert_path)), exist_ok=True)
    with open(cert_path, "w", encoding="utf-8") as f:
        f.write(f"""# DATASET CERTIFICATION SEAL

> **Official Research Dataset Certification Report**

* **Dataset File:** `{input_file}`
* **SHA256 Checksum:** `{sha256_hash}`
* **Certification Date (UTC):** {validation_result['validation_timestamp_utc']}
* **Coverage Window:** `{validation_result['date_range']['start_utc']}` to `{validation_result['date_range']['end_utc']}`
* **Total Rows:** `{total_rows:,}` | **Total Features:** `{len(df.columns)}`

---

## Audit Checklist & Metrics

| Audit Criterion | Result Metric | Threshold | Status |
|---|---|---|---|
| **UTC Monotonicity** | {monotonicity_violations} violations | 0 violations | {'PASS' if monotonicity_violations == 0 else 'FAIL'} |
| **Duplicate Timestamps** | {duplicate_rows} duplicates | 0 duplicates | {'PASS' if duplicate_rows == 0 else 'FAIL'} |
| **Price Validity** | {invalid_prices} invalid prices | 0 invalid prices | {'PASS' if invalid_prices == 0 else 'FAIL'} |
| **Spread Integrity** | {spread_violations} zero/neg spreads | 0 violations | {'PASS' if spread_violations == 0 else 'FAIL'} |
| **Spread Spikes** | {extreme_spread_spikes} spikes (> $3.00) | Logged | INFO |
| **NaN Price Values** | {nan_counts} NaNs | 0 NaNs | {'PASS' if nan_counts == 0 else 'FAIL'} |
| **Final Quality Score** | **{quality_score:.2f}%** | **>= 95.0%** | **{'CERTIFIED' if is_certified else 'REJECTED'}** |

---

## Lineage Metadata Manifest
```json
{json.dumps(validation_result, indent=2)}
```
""")
    print(f"[SUCCESS] Dataset Certification report saved to {cert_path}")
    return validation_result

def main():
    parser = argparse.ArgumentParser(description="Validate dataset quality and issue certification report")
    parser.add_argument("--input", type=str, required=True, help="Input dataset path")
    parser.add_argument("--report", type=str, default="data/quality_reports/latest_quality_report.json", help="Output JSON report path")
    parser.add_argument("--cert", type=str, default="reports/dataset_certification.md", help="Output Markdown certification path")

    args = parser.parse_args()
    validate_dataset(args.input, args.report, args.cert)

if __name__ == "__main__":
    main()
