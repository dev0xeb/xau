#!/usr/bin/env python3
"""
clean_normalize_data.py - Data Cleaning & Standardization Engine

Normalizes raw XAUUSD data:
1. Converts timestamps to UTC ISO format.
2. Calculates mid-price and spread (if bid/ask present).
3. Removes duplicates and sorts chronologically.
4. Exports normalized dataset to Parquet / CSV in data/processed/.
"""

import os
import sys
import argparse
import pandas as pd

def clean_and_normalize(input_file: str, output_file: str) -> pd.DataFrame:
    if not os.path.exists(input_file):
        raise FileNotFoundError(f"Input file not found: {input_file}")

    print(f"[INFO] Cleaning and normalizing {input_file}...")
    
    # Read CSV
    df = pd.read_csv(input_file)
    
    if "timestamp" not in df.columns:
        raise ValueError("Dataset missing mandatory 'timestamp' column.")

    # 1. Parse and standardize timestamps to UTC
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)

    # 2. Sort chronologically
    df = df.sort_values(by="timestamp").reset_index(drop=True)

    # 3. Remove duplicate timestamps (keep first)
    initial_rows = len(df)
    df = df.drop_duplicates(subset=["timestamp"], keep="first").reset_index(drop=True)
    dedup_count = initial_rows - len(df)
    if dedup_count > 0:
        print(f"[INFO] Removed {dedup_count} duplicate timestamp records.")

    # 4. Calculate mid price and spread if bid & ask present
    if "bid" in df.columns and "ask" in df.columns:
        df["bid"] = df["bid"].astype(float)
        df["ask"] = df["ask"].astype(float)
        df["mid"] = (df["bid"] + df["ask"]) / 2.0
        df["spread"] = (df["ask"] - df["bid"]).round(4)
    elif "open" in df.columns and "close" in df.columns:
        for col in ["open", "high", "low", "close"]:
            df[col] = df[col].astype(float)
        df["mid"] = (df["open"] + df["close"]) / 2.0

    # Ensure output directory exists
    os.makedirs(os.path.dirname(os.path.abspath(output_file)), exist_ok=True)

    # Save to Parquet or CSV based on extension
    if output_file.endswith(".parquet"):
        df.to_parquet(output_file, index=False)
    else:
        df.to_csv(output_file, index=False)

    print(f"[SUCCESS] Normalized data saved to {output_file} (Rows: {len(df)})")
    return df

def main():
    parser = argparse.ArgumentParser(description="Clean and normalize raw XAUUSD data to UTC Parquet/CSV")
    parser.add_argument("--input", type=str, required=True, help="Input CSV/Parquet path")
    parser.add_argument("--output", type=str, required=True, help="Output destination path in data/processed/")

    args = parser.parse_args()
    clean_and_normalize(args.input, args.output)

if __name__ == "__main__":
    main()
