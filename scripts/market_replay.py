#!/usr/bin/env python3
"""
market_replay.py - Historical Market Replay Engine

Streams historical tick or M1 dataset rows sequentially at configurable speeds (1x, 5x, 20x, or step-by-step),
enabling visual inspection and real-time behavior replay verification.
"""

import os
import sys
import time
import argparse
import pandas as pd

def replay_dataset(input_file: str, speed_multiplier: float = 5.0, max_rows: int = 100):
    if not os.path.exists(input_file):
        raise FileNotFoundError(f"Dataset file not found: {input_file}")

    print(f"[INFO] Initializing Market Replay Engine for {input_file} (Speed: {speed_multiplier}x)...")
    if input_file.endswith(".parquet"):
        df = pd.read_parquet(input_file)
    else:
        df = pd.read_csv(input_file)

    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.sort_values(by="timestamp").reset_index(drop=True)

    rows_to_replay = min(len(df), max_rows)
    print(f"[START] Replaying first {rows_to_replay} ticks/bars...")

    start_time = time.time()
    for idx in range(rows_to_replay):
        row = df.iloc[idx]
        ts_str = str(row["timestamp"])
        if "close" in row:
            price = f"Close: {row['close']:.2f} | High: {row['high']:.2f} | Low: {row['low']:.2f}"
        else:
            price = f"Bid: {row['bid']:.2f} | Ask: {row['ask']:.2f}"

        session = row.get("session_label", "N/A")
        print(f"[{idx+1:04d}/{rows_to_replay}] {ts_str} | Session: {session:<18} | {price}")

        if idx > 0 and speed_multiplier > 0:
            delta_sec = (df.iloc[idx]["timestamp"] - df.iloc[idx-1]["timestamp"]).total_seconds()
            sleep_time = min(0.5, max(0.01, delta_sec / speed_multiplier))
            time.sleep(sleep_time)

    total_time = time.time() - start_time
    print(f"[SUCCESS] Market Replay finished in {total_time:.2f} seconds.")

def main():
    parser = argparse.ArgumentParser(description="Replay historical market dataset sequentially")
    parser.add_argument("--input", type=str, required=True, help="Input dataset path")
    parser.add_argument("--speed", type=float, default=5.0, help="Speed multiplier (e.g. 1.0, 5.0, 20.0)")
    parser.add_argument("--max_rows", type=int, default=50, help="Maximum rows to replay")

    args = parser.parse_args()
    replay_dataset(args.input, args.speed, args.max_rows)

if __name__ == "__main__":
    main()
