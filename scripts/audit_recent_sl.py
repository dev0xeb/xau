#!/usr/bin/env python3
"""
audit_sl_hit.py - Urgent Live Trade SL Hit Diagnostic Audit

Queries MT5 deal history for the last 30 minutes (20:45 to 21:15 UTC) to examine:
- Magic Number
- Comment / Strategy ID
- Entry Price, Exit Price, SL Price, TP Price
- Retracement / Price movement details
"""

import sys
import os
sys.path.insert(0, os.path.abspath("."))
import pandas as pd
from datetime import datetime, timezone, timedelta
import MetaTrader5 as mt5

def audit_recent_sl():
    print("==========================================================================================")
    print("  URGENT SL HIT DIAGNOSTIC AUDIT (LAST 30 MINUTES)")
    print("==========================================================================================")

    if not mt5.initialize():
        print("[ERROR] MetaTrader 5 terminal not connected.")
        return

    now_dt = datetime.now(timezone.utc)
    from_dt = now_dt - timedelta(minutes=30)

    deals = mt5.history_deals_get(from_dt, now_dt)
    if deals is None or len(deals) == 0:
        print("[DEALS] No deals found in MT5 history in the last 30 minutes.")
        return

    deal_records = [d._asdict() for d in deals]
    df_deals = pd.DataFrame(deal_records)
    df_deals["time_dt"] = pd.to_datetime(df_deals["time"], unit="s", utc=True)

    print(f"Found {len(df_deals)} total deal events in MT5 in the last 30 minutes:\n")

    for idx, r in df_deals.iterrows():
        deal_type = "BUY" if r["type"] == 0 else "SELL"
        entry_type = "ENTRY" if r["entry"] == 0 else "EXIT"
        print(f"Ticket #{r['ticket']} | Time: {r['time_dt'].strftime('%H:%M:%S UTC')} | Magic: {r['magic']} | {entry_type} {deal_type} | Vol: {r['volume']} | Price: ${r['price']:.2f} | Profit: ${r['profit']:+.2f} | Comment: '{r['comment']}'")

    print("==========================================================================================")

if __name__ == "__main__":
    audit_recent_sl()
