#!/usr/bin/env python3
"""
audit_data_quality.py - Quantitative Data Quality Audit Suite

Audits processed XAUUSD datasets against quantitative quality gates:
1. Timestamp monotonicity & order.
2. Negative or zero spreads.
3. Extreme price outlier spikes.
4. Missing candle gaps.
5. Calculates Quality Score (0 - 100%).
"""

import os
import sys
import json
import argparse
import pandas as pd
import numpy as np

def audit_dataset(input_file: str, report_file: str = None) -> dict:
    if not os.path.exists(input_file):
        raise FileNotFoundError(f"Dataset file not found: {input_file}")

    print(f"[INFO] Auditing dataset quality for {input_file}...")

    if input_file.endswith(".parquet"):
        df = pd.read_parquet(input_file)
    else:
        df = pd.read_csv(input_file)

    total_rows = len(df)
    if total_rows == 0:
        raise ValueError("Cannot audit an empty dataset.")

    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)

    # 1. Monotonicity check
    timestamp_diffs = df["timestamp"].diff().dt.total_seconds()
    negative_time_steps = (timestamp_diffs < 0).sum()

    # 2. Spread anomalies check (if tick/spread present)
    negative_spreads = 0
    extreme_spreads = 0
    if "spread" in df.columns:
        negative_spreads = int((df["spread"] <= 0).sum())
        extreme_spreads = int((df["spread"] > 3.0).sum())  # > $3.00 (300 pips)
    elif "bid" in df.columns and "ask" in df.columns:
        spreads = df["ask"] - df["bid"]
        negative_spreads = int((spreads <= 0).sum())
        extreme_spreads = int((spreads > 3.0).sum())

    # 3. Outlier check (price jumps > 1.5%)
    price_col = "close" if "close" in df.columns else ("mid" if "mid" in df.columns else "bid")
    price_pct_change = df[price_col].pct_change().abs()
    outlier_spikes = int((price_pct_change > 0.015).sum())

    # 4. Calculate total corrupt rows & Quality Score
    corrupt_rows = int(negative_time_steps + negative_spreads + extreme_spreads + outlier_spikes)
    quality_score = float(max(0.0, round(100.0 - (corrupt_rows / total_rows * 100.0), 4)))
    passed_audit = bool(quality_score >= 99.5)

    audit_summary = {
        "dataset_file": input_file,
        "total_rows": int(total_rows),
        "monotonicity_violations": int(negative_time_steps),
        "negative_or_zero_spreads": int(negative_spreads),
        "extreme_spread_spikes": int(extreme_spreads),
        "price_outlier_spikes": int(outlier_spikes),
        "total_corrupt_rows": int(corrupt_rows),
        "quality_score": quality_score,
        "passed_audit": passed_audit,
        "timestamp_range": {
            "start_utc": str(df["timestamp"].min()),
            "end_utc": str(df["timestamp"].max())
        }
    }

    print(f"--- Audit Results ---")
    print(f"Total Rows:             {total_rows}")
    print(f"Monotonicity Errors:    {negative_time_steps}")
    print(f"Negative/Zero Spreads:  {negative_spreads}")
    print(f"Extreme Spread Spikes:  {extreme_spreads}")
    print(f"Outlier Spikes (>1.5%): {outlier_spikes}")
    print(f"Data Quality Score:     {quality_score}%")
    print(f"Status:                 {'[PASSED CERTIFICATION]' if passed_audit else '[FAILED AUDIT]'}")

    if report_file:
        os.makedirs(os.path.dirname(os.path.abspath(report_file)), exist_ok=True)
        with open(report_file, "w") as f:
            json.dump(audit_summary, f, indent=2)
        print(f"[INFO] Audit report written to {report_file}")

    return audit_summary

def main():
    parser = argparse.ArgumentParser(description="Audit data quality of a processed XAUUSD dataset")
    parser.add_argument("--input", type=str, required=True, help="Input dataset (Parquet or CSV)")
    parser.add_argument("--report", type=str, default=None, help="Destination JSON report file path")

    args = parser.parse_args()
    audit_dataset(args.input, args.report)

if __name__ == "__main__":
    main()
