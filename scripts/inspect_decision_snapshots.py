#!/usr/bin/env python3
"""
inspect_decision_snapshots.py - Detailed Inspection of Live Decision Snapshots Log

Parses decision_engine/decision_logs/decision_snapshots.jsonl to find all candidate
executions for both STRAT-001 and STRAT-002.
"""

import sys
import os
import json
import pandas as pd
from datetime import datetime, timezone

def inspect_decision_snapshots():
    print("==========================================================================================")
    print("  DECISION SNAPSHOTS LOG INSPECTOR (STRAT-001 VS STRAT-002)")
    print("==========================================================================================")

    log_file = "decision_engine/decision_logs/decision_snapshots.jsonl"
    if not os.path.exists(log_file):
        print(f"[ERROR] Snapshot file '{log_file}' not found.")
        return

    records = []
    with open(log_file, "r") as f:
        for line in f:
            if line.strip():
                try:
                    records.append(json.loads(line.strip()))
                except Exception:
                    pass

    print(f"Total decision snapshots recorded: {len(records)}")

    exec_records = []
    for r in records:
        dec = r.get("decision", r.get("candidate_snapshot", {}).get("decision"))
        cand = r.get("candidate_snapshot", {})
        if cand and cand.get("decision") == "EXECUTE":
            exec_records.append(cand)
        elif r.get("decision") == "EXECUTE":
            exec_records.append(r)

    print(f"Total EXECUTE decision snapshots recorded: {len(exec_records)}\n")

    if not exec_records:
        print("No EXECUTE snapshots found in log.")
        return

    df_exec = pd.DataFrame(exec_records)
    print("Breakdown by strategy_version:")
    if "strategy_version" in df_exec.columns:
        print(df_exec["strategy_version"].value_counts())
    else:
        print("strategy_version column not present in df_exec.")

    print("\nRecent 10 EXECUTE Decisions:")
    for idx, r in df_exec.tail(10).iterrows():
        cand_id = r.get("candidate_id", "N/A")
        strat = r.get("strategy_version", "N/A")
        direction = r.get("direction", "N/A")
        entry_p = float(r.get("entry_target") or 0.0)
        sl_p = float(r.get("sl") or 0.0)
        tp_p = float(r.get("tp") or 0.0)
        print(f"  * Candidate {cand_id} | Strategy: '{strat}' | {direction} @ ${entry_p:.2f} (SL: ${sl_p:.2f} | TP: ${tp_p:.2f})")

    print("==========================================================================================")

if __name__ == "__main__":
    inspect_decision_snapshots()
