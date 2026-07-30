#!/usr/bin/env python3
"""
inspect_exact_ticket_details.py - Detailed MT5 Order & Deal Inspector

Inspects all orders in MT5 history from the last 45 minutes.
"""

import sys
import os
sys.path.insert(0, os.path.abspath("."))
import pandas as pd
from datetime import datetime, timezone, timedelta
import MetaTrader5 as mt5

def inspect_all_recent_orders():
    print("==========================================================================================")
    print("  EXACT MT5 ORDER INSPECTOR (LAST 45 MINUTES)")
    print("==========================================================================================")

    if not mt5.initialize():
        print("[ERROR] MetaTrader 5 terminal not connected.")
        return

    now_dt = datetime.now(timezone.utc)
    from_dt = now_dt - timedelta(minutes=45)

    orders = mt5.history_orders_get(from_dt, now_dt)
    if orders is None or len(orders) == 0:
        print("[ORDERS] No history orders found.")
        return

    order_list = [o._asdict() for o in orders]
    print(f"Found {len(order_list)} total history orders in MT5 in the last 45 minutes:\n")

    for o in order_list:
        o_type = "BUY" if o["type"] == 0 else "SELL"
        t_dt = datetime.fromtimestamp(o["time_setup"], tz=timezone.utc)
        print(f"Ticket #{o['ticket']} | PositionID #{o['position_id']} | Time: {t_dt.strftime('%H:%M:%S UTC')} | Type: {o_type} | Vol: {o['volume_initial']} | OpenPrice: ${o['price_open']:.2f} | SL: ${o['sl']:.2f} | TP: ${o['tp']:.2f} | Magic: {o['magic']} | Comment: '{o['comment']}'")

    print("==========================================================================================")

if __name__ == "__main__":
    inspect_all_recent_orders()
