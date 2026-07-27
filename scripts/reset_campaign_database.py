#!/usr/bin/env python3
"""
reset_campaign_database.py - Reset Trade Journal & Audit DB for Campaign Start

Clears test artifacts recorded during unit tests and system audits:
- execution_engine/audit/trade_journal.db
- execution_engine/audit/trade_journal.jsonl
- decision_engine/decision_logs/decision_snapshots.jsonl
- execution_engine/queue/event_log.jsonl
- execution_engine/queue/dlq_candidates.jsonl
"""

import os
import sqlite3

def reset_campaign_database():
    print("[RESET] Wiping pre-campaign test artifacts...")

    # 1. Clear SQLite DB
    db_path = "execution_engine/audit/trade_journal.db"
    if os.path.exists(db_path):
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM trades")
        conn.commit()
        conn.close()
        print("  - Cleared SQLite trade_journal.db (0 records)")

    # 2. Truncate JSONL files
    files_to_reset = [
        "execution_engine/audit/trade_journal.jsonl",
        "decision_engine/decision_logs/decision_snapshots.jsonl",
        "execution_engine/queue/event_log.jsonl",
        "execution_engine/queue/dlq_candidates.jsonl"
    ]

    for fpath in files_to_reset:
        if os.path.exists(fpath):
            with open(fpath, "w") as f:
                f.write("")
            print(f"  - Truncated {fpath}")

    print("[SUCCESS] Campaign Database Reset Complete. 0 trades recorded.")

if __name__ == "__main__":
    reset_campaign_database()
