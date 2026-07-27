#!/usr/bin/env python3
"""
generate_catalog.py - Dataset Metadata Catalog Generator

Computes SHA256 checksums, dataset dimensions, schema definitions, and audit status,
saving structured JSON metadata to data/metadata/.
"""

import os
import sys
import json
import hashlib
import argparse
import pandas as pd
from datetime import datetime, timezone

def compute_sha256(filepath: str) -> str:
    sha256 = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            sha256.update(chunk)
    return sha256.hexdigest()

def generate_catalog_entry(input_file: str, dataset_id: str, version: str = "1.0.0", granularity: str = "M1") -> dict:
    if not os.path.exists(input_file):
        raise FileNotFoundError(f"Dataset file not found: {input_file}")

    print(f"[INFO] Generating catalog metadata for {input_file}...")

    # Load data for inspection
    if input_file.endswith(".parquet"):
        df = pd.read_parquet(input_file)
    else:
        df = pd.read_csv(input_file)

    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)

    sha256_hash = compute_sha256(input_file)
    schema_map = {col: str(df[col].dtype) for col in df.columns}

    # Basic quick audit metrics
    negative_time = int((df["timestamp"].diff().dt.total_seconds() < 0).sum())
    quality_score = float(max(0.0, round(100.0 - (negative_time / len(df) * 100.0), 4)))
    passed_audit = bool(quality_score >= 99.5)

    metadata = {
      "dataset_id": dataset_id,
      "version": version,
      "instrument": "XAUUSD",
      "granularity": granularity,
      "source": "REAL_HISTORICAL_DATA",
      "created_at_utc": datetime.now(timezone.utc).isoformat(),
      "sha256_checksum": sha256_hash,
      "file_path": input_file,
      "row_count": int(len(df)),
      "date_range": {
        "start_utc": str(df["timestamp"].min()),
        "end_utc": str(df["timestamp"].max())
      },
      "schema": schema_map,
      "audit_summary": {
        "quality_score": quality_score,
        "passed_audit": passed_audit,
        "anomalies_detected": int(negative_time)
      }
    }

    # Write catalog file to data/metadata/
    output_catalog_path = os.path.join("data", "metadata", f"{dataset_id}_v{version}_metadata.json")
    os.makedirs(os.path.dirname(output_catalog_path), exist_ok=True)
    with open(output_catalog_path, "w") as f:
        json.dump(metadata, f, indent=2)

    print(f"[SUCCESS] Catalog metadata written to {output_catalog_path}")
    print(f"SHA256: {sha256_hash}")
    return metadata

def main():
    parser = argparse.ArgumentParser(description="Generate dataset metadata catalog entry")
    parser.add_argument("--input", type=str, required=True, help="Input dataset path in data/processed/")
    parser.add_argument("--id", type=str, default="XAUUSD_M1_DATASET", help="Dataset ID")
    parser.add_argument("--version", type=str, default="1.0.0", help="Dataset version tag")
    parser.add_argument("--granularity", type=str, default="M1", choices=["TICK", "M1", "M5"], help="Granularity")

    args = parser.parse_args()
    generate_catalog_entry(args.input, args.id, args.version, args.granularity)

if __name__ == "__main__":
    main()
