#!/usr/bin/env python3
"""
prepare_versioned_dataset.py - Semantic Versioning & Lock Utility

Tags a verified dataset with a semantic version string (e.g. XAUUSD_M1_v1.0.0.parquet),
moves it to canonical storage, and generates catalog lock entries.
"""

import os
import sys
import shutil
import argparse

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
from generate_catalog import generate_catalog_entry

def version_dataset(input_file: str, version: str, dataset_name: str = "XAUUSD_M1"):
    if not os.path.exists(input_file):
        raise FileNotFoundError(f"Source dataset not found: {input_file}")

    ext = ".parquet" if input_file.endswith(".parquet") else ".csv"
    canonical_filename = f"{dataset_name}_v{version}{ext}"
    target_path = os.path.join("data", "processed", canonical_filename)

    os.makedirs(os.path.dirname(target_path), exist_ok=True)
    shutil.copy2(input_file, target_path)
    print(f"[INFO] Dataset copied to canonical location: {target_path}")

    # Generate metadata entry
    granularity = "TICK" if "TICK" in dataset_name.upper() else "M1"
    metadata = generate_catalog_entry(target_path, dataset_id=f"{dataset_name}_v{version}", version=version, granularity=granularity)
    return target_path, metadata

def main():
    parser = argparse.ArgumentParser(description="Create immutable versioned dataset snapshot")
    parser.add_argument("--input", type=str, required=True, help="Input dataset path")
    parser.add_argument("--version", type=str, required=True, help="Semantic version tag (e.g. 1.0.0)")
    parser.add_argument("--name", type=str, default="XAUUSD_M1", help="Dataset base name")

    args = parser.parse_args()
    version_dataset(args.input, args.version, args.name)

if __name__ == "__main__":
    main()
