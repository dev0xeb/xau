#!/usr/bin/env python3
"""
merge_datasets.py - Historical Dataset Merger Engine

Merges tick or M1 historical datasets from multiple sources (e.g. MT5 + Dukascopy / CSV),
handles timezone normalization to UTC, deduplicates rows, sorts chronologically, and outputs merged files.
"""

import os
import sys
import argparse
import pandas as pd

def merge_datasets(input_files: list, output_file: str) -> pd.DataFrame:
    if not input_files:
        raise ValueError("At least one input file must be specified for merging.")

    dfs = []
    for filepath in input_files:
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"Input file not found: {filepath}")
        print(f"[INFO] Reading {filepath}...")
        if filepath.endswith(".parquet"):
            df = pd.read_parquet(filepath)
        else:
            df = pd.read_csv(filepath)
        dfs.append(df)

    merged_df = pd.concat(dfs, ignore_index=True)
    if "timestamp" not in merged_df.columns:
        raise ValueError("Merged dataset missing mandatory 'timestamp' column.")

    # Convert timestamps to UTC
    merged_df["timestamp"] = pd.to_datetime(merged_df["timestamp"], utc=True)

    # Sort chronologically
    merged_df = merged_df.sort_values(by="timestamp").reset_index(drop=True)

    # Deduplicate keeping first
    initial_len = len(merged_df)
    merged_df = merged_df.drop_duplicates(subset=["timestamp"], keep="first").reset_index(drop=True)
    print(f"[INFO] Merged total rows: {initial_len} -> {len(merged_df)} after deduplication.")

    # Calculate mid price if bid/ask or OHLC present
    if "bid" in merged_df.columns and "ask" in merged_df.columns:
        merged_df["bid"] = merged_df["bid"].astype(float)
        merged_df["ask"] = merged_df["ask"].astype(float)
        merged_df["mid"] = (merged_df["bid"] + merged_df["ask"]) / 2.0
        merged_df["spread"] = (merged_df["ask"] - merged_df["bid"]).round(4)
    elif "open" in merged_df.columns and "close" in merged_df.columns:
        for col in ["open", "high", "low", "close"]:
            merged_df[col] = merged_df[col].astype(float)
        merged_df["mid"] = (merged_df["open"] + merged_df["close"]) / 2.0

    os.makedirs(os.path.dirname(os.path.abspath(output_file)), exist_ok=True)
    if output_file.endswith(".parquet"):
        merged_df.to_parquet(output_file, index=False)
    else:
        merged_df.to_csv(output_file, index=False)

    print(f"[SUCCESS] Merged dataset saved to {output_file} (Rows: {len(merged_df)})")
    return merged_df

def main():
    parser = argparse.ArgumentParser(description="Merge multiple XAUUSD historical datasets into a single UTC file")
    parser.add_argument("--input", type=str, nargs="+", required=True, help="Input CSV/Parquet files to merge")
    parser.add_argument("--output", type=str, required=True, help="Destination output path in data/processed/")

    args = parser.parse_args()
    merge_datasets(args.input, args.output)

if __name__ == "__main__":
    main()
