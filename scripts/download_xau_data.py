#!/usr/bin/env python3
"""
download_xau_data.py - XAUUSD Real Data Ingestion Utility

Ingests real historical XAUUSD tick or M1 data into data/raw/.
Phase 1 establishes the ingestion interface and raw validation contract.
"""

import os
import sys
import argparse
import pandas as pd
from datetime import datetime

def download_or_import_xau(input_file: str, output_file: str, granularity: str = "M1"):
    """
    Ingests real historical XAUUSD data from a provided file into data/raw/.
    """
    if not os.path.exists(input_file):
        raise FileNotFoundError(f"Input historical data file not found: {input_file}")

    print(f"[INFO] Ingesting real XAUUSD {granularity} historical data from {input_file}...")
    df = pd.read_csv(input_file)

    # Basic structural check
    required_cols = ["timestamp"]
    for col in required_cols:
        if col not in df.columns:
            raise ValueError(f"Missing required column '{col}' in input data file.")

    os.makedirs(os.path.dirname(os.path.abspath(output_file)), exist_ok=True)
    df.to_csv(output_file, index=False)
    print(f"[SUCCESS] Real XAUUSD data saved to raw data storage: {output_file} (Rows: {len(df)})")

def main():
    parser = argparse.ArgumentParser(description="Ingest real historical XAUUSD data into data/raw/")
    parser.add_argument("--input", type=str, required=True, help="Path to real historical XAUUSD CSV file")
    parser.add_argument("--output", type=str, required=True, help="Destination path in data/raw/")
    parser.add_argument("--granularity", type=str, default="M1", choices=["TICK", "M1", "M5"], help="Data granularity")

    args = parser.parse_args()

    # Rule enforcement check: Ensure output path is inside data/raw/
    normalized_out = os.path.normpath(args.output)
    if not ("data" in normalized_out and "raw" in normalized_out):
        print("[WARNING] Output file path is outside data/raw/. Ingested research data must reside in data/raw/.")

    download_or_import_xau(args.input, args.output, args.granularity)

if __name__ == "__main__":
    main()
