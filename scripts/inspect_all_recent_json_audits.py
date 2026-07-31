#!/usr/bin/env python3
"""
inspect_all_recent_json_audits.py - Full Audit of JSON Candidate Files and Strategy Versions

Reads every single JSON file in execution_engine/audit/ created in the last 12 hours.
"""

import sys
import os
import json
import glob
import pandas as pd
from datetime import datetime, timezone, timedelta

def inspect_json_audits():
    print("==========================================================================================")
    print("  EXACT CANDIDATE AUDIT FILE INSPECTOR (LAST 12 HOURS)")
    print("==========================================================================================")

    audit_files = glob.glob("execution_engine/audit/*.json")
    print(f"Found {len(audit_files)} total audit files in execution_engine/audit/\n")

    now_dt = datetime.now(timezone.utc)
    cutoff_dt = now_dt - timedelta(hours=12)

    records = []
    for af in audit_files:
        try:
            mtime = os.path.getmtime(af)
            file_dt = datetime.fromtimestamp(mtime, tz=timezone.utc)
            if file_dt < cutoff_dt:
                continue

            with open(af, "r") as f:
                data = json.load(f)
                data["file_dt"] = file_dt
                records.append(data)
        except Exception:
            pass

    print(f"Found {len(records)} audit records created in the last 12 hours ({cutoff_dt.strftime('%H:%M UTC')} to present):\n")

    df_rec = pd.DataFrame(records)
    if df_rec.empty:
        print("No audit records found in the last 12 hours.")
        return

    print(f"Available columns in JSON records: {list(df_rec.columns)}")
    df_rec = df_rec.sort_values("file_dt")
    
    print("\nRecent 15 Executed Positions:")
    for idx, r in df_rec.tail(15).iterrows():
        t_str = r['file_dt'].strftime('%H:%M:%S UTC')
        cand_id = r.get("candidate_id", r.get("execution_uuid", "N/A"))
        strat = r.get("strategy_version", r.get("strategy_id", r.get("version", "N/A")))
        direction = r.get("direction", r.get("order_type", "N/A"))
        entry_p = float(r.get("entry_target") or r.get("entry_price") or 0.0)
        sl_p = float(r.get("sl") or 0.0)
        tp_p = float(r.get("tp") or 0.0)
        print(f"  * [{t_str}] {cand_id} | Strat: '{strat}' | {direction} @ ${entry_p:.2f} (SL: ${sl_p:.2f} | TP: ${tp_p:.2f})")

    print("==========================================================================================")

if __name__ == "__main__":
    inspect_json_audits()
