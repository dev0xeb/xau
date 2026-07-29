#!/usr/bin/env python3
"""
calc_counterfactual_pnl.py - Counterfactual PnL Calculator for $20 Profit Lock

Calculates total net PnL under the scenario where every trade that touched $20 profit
locked in at least $20 profit instead of retracing into a loss.
"""

import sys
import os
sys.path.insert(0, os.path.abspath("."))
import pandas as pd
from datetime import datetime, timezone, timedelta
import MetaTrader5 as mt5

def calc_counterfactual_pnl():
    print("==========================================================================================")
    print("  COUNTERFACTUAL PnL ANALYSIS: IMPACT OF $20 PROFIT LOCK-IN")
    print("==========================================================================================")

    if not mt5.initialize():
        print("[ERROR] MetaTrader 5 terminal not connected.")
        return

    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    deals = mt5.history_deals_get(today_start, datetime.now(timezone.utc) + timedelta(days=1)) or []

    bot_deals = [d._asdict() for d in deals if d.magic == 1001 or "CAND-LIVE" in str(d.comment)]

    position_map = {}
    for d in bot_deals:
        pos_id = d.get("position_id", d.get("order"))
        if pos_id not in position_map:
            position_map[pos_id] = {"in": None, "out": None}

        if d.get("entry") == 0:
            position_map[pos_id]["in"] = d
        elif d.get("entry") == 1:
            position_map[pos_id]["out"] = d

    closed_positions = [p for p in position_map.values() if p["in"] and p["out"]]

    if not closed_positions:
        print("[INFO] No closed position records found today.")
        return

    actual_pnl = sum(p["out"].get("profit", 0.0) for p in closed_positions)

    lock20_pnl = 0.0
    lock20_tp50_pnl = 0.0

    hit20_count = 0
    hit50_count = 0
    miss20_count = 0

    for p in closed_positions:
        in_d = p["in"]
        out_d = p["out"]

        entry_p = in_d.get("price", 0.0)
        exit_p = out_d.get("price", 0.0)
        entry_t_sec = in_d.get("time", 0)
        exit_t_sec = out_d.get("time", 0)
        direction = "BUY" if in_d.get("type") == 0 else "SELL"
        profit = out_d.get("profit", 0.0)

        rates = mt5.copy_rates_range(in_d.get("symbol", "XAUUSDz"), mt5.TIMEFRAME_M1, max(0, entry_t_sec - 60), exit_t_sec + 60)

        if rates is not None and len(rates) > 0:
            df = pd.DataFrame(rates)
            if direction == "BUY":
                mfe_pts = round(df["high"].max() - entry_p, 2)
            else:
                mfe_pts = round(entry_p - df["low"].min(), 2)
        else:
            if direction == "BUY":
                mfe_pts = round(exit_p - entry_p, 2)
            else:
                mfe_pts = round(entry_p - exit_p, 2)

        # Scenario Evaluation
        if mfe_pts >= 5.00 or profit >= 45.0:
            hit50_count += 1
            hit20_count += 1
            lock20_pnl += 20.0
            lock20_tp50_pnl += 50.0
        elif mfe_pts >= 2.00 or profit >= 18.0:
            hit20_count += 1
            lock20_pnl += 20.0
            lock20_tp50_pnl += 20.0
        else:
            miss20_count += 1
            lock20_pnl -= 20.0
            lock20_tp50_pnl -= 20.0

    total_closed = len(closed_positions)

    print(f"Total Closed Bot Positions Today: {total_closed}")
    print(f"Actual Net PnL Today: ${actual_pnl:+.2f}\n")

    print("==========================================================================================")
    print("  COUNTERFACTUAL RESULTS")
    print("==========================================================================================")
    print(f"1. Scenario A: Pure $20 Profit Lock (Every trade hitting $20 locks +$20 profit)")
    print(f"   - Counterfactual Net PnL: ${lock20_pnl:+.2f}")
    print(f"   - Total PnL Gain over Actual: ${lock20_pnl - actual_pnl:+.2f}\n")

    print(f"2. Scenario B: $20 Lock + $50 TP Target ($20 locked, trades running to $50 hit TP)")
    print(f"   - Counterfactual Net PnL: ${lock20_tp50_pnl:+.2f}")
    print(f"   - Total PnL Gain over Actual: ${lock20_tp50_pnl - actual_pnl:+.2f}")
    print("==========================================================================================")

if __name__ == "__main__":
    calc_counterfactual_pnl()
