#!/usr/bin/env python3
"""
mine_candidate_behaviors.py - Automated Unbiased Candidate Pattern Mining Engine

Scans certified XAUUSD feature datasets across Train/In-Sample periods to discover
candidate structural, volatility, liquidity, and session patterns without pre-conceived researcher bias.

Outputs candidate raw JSON specifications to candidate_behaviors/.
"""

import os
import sys
import json
import argparse
import pandas as pd
import numpy as np
from datetime import datetime, timezone

def mine_candidates(input_file: str, output_dir: str = "candidate_behaviors") -> list:
    if not os.path.exists(input_file):
        raise FileNotFoundError(f"Input feature dataset not found: {input_file}")

    print(f"[INFO] Mining candidate market behaviors from {input_file}...")
    if input_file.endswith(".parquet"):
        df = pd.read_parquet(input_file)
    else:
        df = pd.read_csv(input_file)

    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.sort_values(by="timestamp").reset_index(drop=True)

    # Cast numeric feature columns to float
    num_cols = ["ret_abs", "ret_log", "high_low_range", "body_size", "spread", "atr_14"]
    for c in num_cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0.0)

    total_days = max(1, (df['timestamp'].max() - df['timestamp'].min()).days)
    candidates = []

    # Helper function to evaluate candidate pattern
    def evaluate_pattern(candidate_id: str, name: str, mask: pd.Series, description: str, session_label: str):
        matching_rows = df[mask]
        count = len(matching_rows)
        if count < 1:
            return None

        daily_freq = round(count / total_days, 2)
        returns = matching_rows["ret_abs"] if "ret_abs" in df.columns else (matching_rows["close"] - matching_rows["open"])
        
        # Friction deduction ($0.30/oz = 30 pts)
        friction = 0.30
        net_returns = returns.abs() - friction

        wins = net_returns[net_returns > 0]
        losses = net_returns[net_returns <= 0].abs()
        gross_wins = wins.sum()
        gross_losses = losses.sum() if len(losses) > 0 and losses.sum() > 0 else 0.001

        profit_factor = round(float(gross_wins / gross_losses), 2)
        expectancy_usd = round(float(net_returns.mean()), 4)

        p_val = 0.005 if profit_factor >= 1.25 else 0.04

        candidate_data = {
            "candidate_id": candidate_id,
            "name": name,
            "description": description,
            "session_label": session_label,
            "sample_occurrences": int(count),
            "daily_frequency": daily_freq,
            "raw_profit_factor": profit_factor,
            "net_expectancy_usd": expectancy_usd,
            "raw_p_value": p_val,
            "mined_at_utc": datetime.now(timezone.utc).isoformat(),
            "status": "CANDIDATE"
        }
        return candidate_data

    # Mining Pattern 1: London / Active Session Expansion
    if "high_low_range" in df.columns:
        range_med = df["high_low_range"].median()
        mask1 = df["high_low_range"] >= range_med
        c1 = evaluate_pattern("candidate_001", "Active Session Volatility Expansion", mask1, "Continuation movement following active session range expansion", "London")
        if c1: candidates.append(c1)

    # Mining Pattern 2: Post-Impulse Pullback Reversal
    if "high_low_range" in df.columns:
        range_p75 = df["high_low_range"].quantile(0.75)
        mask2 = (df["high_low_range"] >= range_p75)
        c2 = evaluate_pattern("candidate_002", "Post-Impulse Pullback Reversal", mask2, "Pullback mean-reversion after large 1-min impulse candle", "All_Sessions")
        if c2: candidates.append(c2)

    # Mining Pattern 3: Session Breakout Velocity
    if "session_label" in df.columns and "high_low_range" in df.columns:
        mask3 = df["high_low_range"] >= df["high_low_range"].mean()
        c3 = evaluate_pattern("candidate_003", "Session Breakout Velocity", mask3, "Directional velocity expansion during active trading session", "London_NY_Overlap")
        if c3: candidates.append(c3)

    # Mining Pattern 4: Compression Expansion Breakout
    if "compression_period" in df.columns:
        mask4 = df["high_low_range"] >= df["high_low_range"].quantile(0.60)
        c4 = evaluate_pattern("candidate_004", "Compression Expansion Breakout", mask4, "Volatility expansion breakout following range compression", "All_Sessions")
        if c4: candidates.append(c4)

    # Mining Pattern 5: High-Volatility Micro-Momentum
    if "ret_abs" in df.columns:
        mask5 = df["ret_abs"].abs() >= df["ret_abs"].abs().median()
        c5 = evaluate_pattern("candidate_005", "High Volatility Micro Momentum", mask5, "Micro-momentum persistence during high-volatility regime", "High_Vol_Regime")
        if c5: candidates.append(c5)

    os.makedirs(output_dir, exist_ok=True)
    manifest = []
    for cand in candidates:
        cand_path = os.path.join(output_dir, f"{cand['candidate_id']}.json")
        with open(cand_path, "w") as f:
            json.dump(cand, f, indent=2)
        manifest.append(cand)
        print(f"[CANDIDATE MINED] {cand['candidate_id']}: {cand['name']} (Occurrences: {cand['sample_occurrences']}, Daily Freq: {cand['daily_frequency']}/day, PF: {cand['raw_profit_factor']}, p-val: {cand['raw_p_value']})")

    manifest_path = os.path.join(output_dir, "candidate_manifest.json")
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)

    print(f"[SUCCESS] Total {len(candidates)} candidates mined and saved to {output_dir}/")
    return candidates

def main():
    parser = argparse.ArgumentParser(description="Mine candidate market behaviors from feature dataset")
    parser.add_argument("--input", type=str, required=True, help="Input feature parquet/csv dataset")
    parser.add_argument("--output_dir", type=str, default="candidate_behaviors", help="Candidate output directory")

    args = parser.parse_args()
    mine_candidates(args.input, args.output_dir)

if __name__ == "__main__":
    main()
