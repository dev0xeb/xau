#!/usr/bin/env python3
"""
audit_exact_live_ensemble_breakdown_correct.py - Correct Live Ensemble Trade Breakdown

Parses decision_snapshots.jsonl to audit every candidate payload generated for
STRAT-001 (STRAT-XAU-FVG-BURST) and STRAT-002 (STRAT-XAU-BOS-BURST) since deployment.
"""

import sys
import os
import json
import pandas as pd
from datetime import datetime, timezone, timedelta
import MetaTrader5 as mt5

def audit_exact_ensemble():
    print("==========================================================================================")
    print("  EXACT LIVE TRADE BREAKDOWN SINCE ENSEMBLE DEPLOYMENT (JULY 30 17:30 UTC TO PRESENT)")
    print("==========================================================================================")

    log_file = "decision_engine/decision_logs/decision_snapshots.jsonl"
    if not os.path.exists(log_file):
        print(f"[ERROR] Snapshot file '{log_file}' not found.")
        return

    deploy_ts = 1785432600.0  # July 30 17:30 UTC

    exec_records = []
    with open(log_file, "r") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                data = json.loads(line.strip())
                cand = data.get("candidate_snapshot", data)
                if cand.get("decision") == "EXECUTE":
                    t_sec = cand.get("timestamp_sec", data.get("timestamp_sec", 0))
                    if t_sec >= deploy_ts or "BURST" in str(cand.get("strategy_version", "")):
                        exec_records.append(cand)
            except Exception:
                pass

    if not exec_records:
        print("No execution records found since deployment.")
        return

    df_exec = pd.DataFrame(exec_records)
    
    # Separate by Strategy Version
    s1_df = df_exec[df_exec["strategy_version"].str.contains("FVG", na=False)].copy()
    s2_df = df_exec[df_exec["strategy_version"].str.contains("BOS", na=False)].copy()

    def print_strat_summary(name, df_s):
        print(f"[BREAKDOWN] {name}:")
        if df_s.empty:
            print("   - 0 Candidates Executed.\n")
            return

        cand_count = len(df_s)
        total_positions = cand_count * 3
        buy_cands = len(df_s[df_s["direction"] == "BUY"])
        sell_cands = len(df_s[df_s["direction"] == "SELL"])

        print(f"   - Total Candidate Signals: {cand_count} Signals ({total_positions} Burst Positions)")
        print(f"   - Directional Split: {buy_cands} BUY Signals ({buy_cands*3} Positions) / {sell_cands} SELL Signals ({sell_cands*3} Positions)")
        
        print("\n   - Full Executed Candidate Log:")
        for idx, r in df_s.iterrows():
            cand_id = r.get("candidate_id", "N/A")
            direction = r.get("direction", "BUY")
            entry_p = float(r.get("entry_target") or 0.0)
            sl_p = float(r.get("sl") or 0.0)
            tp_p = float(r.get("tp") or 0.0)
            print(f"     * {cand_id} | {direction} (3 Burst Orders) @ ${entry_p:.2f} | SL: ${sl_p:.2f} | TP: ${tp_p:.2f}")

        print("\n" + "-" * 90 + "\n")

    print_strat_summary("STRAT-001 (M5 Fair Value Gap Imbalance - STRAT-XAU-FVG-BURST)", s1_df)
    print_strat_summary("STRAT-002 (M5 CHOCH / BOS Breakout - STRAT-XAU-BOS-BURST)", s2_df)

    print("==========================================================================================")

if __name__ == "__main__":
    audit_exact_ensemble()
