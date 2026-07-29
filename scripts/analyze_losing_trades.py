#!/usr/bin/env python3
"""
analyze_losing_trades.py - Comprehensive Diagnostic Attribution for Losing Trades

Audits all losing trades executed by STRAT-XAU-001 today:
1. Hourly / Session Distribution
2. Trade Clustering (rapid-fire entries during chop)
3. Maximum Favorable Excursion (MFE) prior to SL hit
4. Volatility (ATR) & Spread conditions at entry
"""

import sys
import os
sys.path.insert(0, os.path.abspath("."))
import json
import glob
import pandas as pd
from datetime import datetime, timezone, timedelta
import MetaTrader5 as mt5

def analyze_losing_trades():
    print("==========================================================================================")
    print("  COMPREHENSIVE DIAGNOSTIC ATTRIBUTION FOR LOSING TRADES (JULY 29, 2026)")
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

    losing_trades = []
    winning_trades = []

    for p in closed_positions:
        in_d = p["in"]
        out_d = p["out"]
        profit = out_d.get("profit", 0.0)

        entry_p = in_d.get("price", 0.0)
        exit_p = out_d.get("price", 0.0)
        entry_t_sec = in_d.get("time", 0)
        direction = "BUY" if in_d.get("type") == 0 else "SELL"
        comment = in_d.get("comment") or out_d.get("comment") or ""

        time_dt = datetime.fromtimestamp(entry_t_sec, tz=timezone.utc)
        hour_utc = time_dt.hour

        # Fetch M1 rates to measure MFE prior to loss
        rates = mt5.copy_rates_range(in_d.get("symbol", "XAUUSDz"), mt5.TIMEFRAME_M1, max(0, entry_t_sec - 60), out_d.get("time", entry_t_sec) + 60)

        mfe_pts = 0.0
        if rates is not None and len(rates) > 0:
            df = pd.DataFrame(rates)
            if direction == "BUY":
                mfe_pts = round(df["high"].max() - entry_p, 2)
            else:
                mfe_pts = round(entry_p - df["low"].min(), 2)

        trade_record = {
            "ticket": p["in"].get("order"),
            "entry_time": time_dt.strftime("%H:%M:%S"),
            "hour_utc": hour_utc,
            "direction": direction,
            "entry_p": entry_p,
            "exit_p": exit_p,
            "profit": profit,
            "mfe_pts": mfe_pts,
            "comment": comment,
            "timestamp_sec": entry_t_sec
        }

        if profit < 0:
            losing_trades.append(trade_record)
        else:
            winning_trades.append(trade_record)

    total_closed = len(closed_positions)
    total_losses = len(losing_trades)
    total_wins = len(winning_trades)

    print(f"Analyzed {total_closed} closed positions ({total_wins} Wins, {total_losses} Losses).\n")

    if not losing_trades:
        print("[INFO] No losing trade records found.")
        return

    df_losses = pd.DataFrame(losing_trades)

    # 1. Hourly Distribution of Losses
    print("==========================================================================================")
    print("  1. HOURLY LOSS DISTRIBUTION (UTC)")
    print("==========================================================================================")
    hourly_counts = df_losses.groupby("hour_utc").size()
    hourly_pnl = df_losses.groupby("hour_utc")["profit"].sum()
    for hr, count in hourly_counts.items():
        pnl = hourly_pnl[hr]
        print(f"  - Hour {hr:02d}:00 UTC: {count:3d} Losses | Total Loss: ${pnl:7.2f}")

    # 2. Trade Clustering Analysis (Entries within 10 seconds of previous entry)
    df_all = pd.DataFrame([t for p in closed_positions for t in [{
        "time": p["in"].get("time"),
        "profit": p["out"].get("profit", 0.0)
    }]]).sort_values("time")

    df_all["time_diff"] = df_all["time"].diff()
    clustered = df_all[df_all["time_diff"] <= 10]
    clustered_losses = clustered[clustered["profit"] < 0]

    print("\n==========================================================================================")
    print("  2. TRADE CLUSTERING & SIDEWAYS CHOP RE-ENTRY AUDIT")
    print("==========================================================================================")
    print(f"  - Total Clustered Entries (taken <= 10s after prior entry): {len(clustered)}")
    print(f"  - Clustered Entries resulting in Losses: {len(clustered_losses)} ({len(clustered_losses)/len(clustered)*100.0 if len(clustered)>0 else 0:.1f}%)")
    print(f"  - Total Money Lost in Duplicate Rapid Clustered Entries: ${clustered_losses['profit'].sum():.2f}")

    # 3. Maximum Favorable Excursion (MFE) Before Loss
    print("\n==========================================================================================")
    print("  3. MAXIMUM FAVORABLE EXCURSION (MFE) BEFORE LOSS")
    print("==========================================================================================")
    mfe_0_05 = len(df_losses[df_losses["mfe_pts"] < 0.50])
    mfe_05_10 = len(df_losses[(df_losses["mfe_pts"] >= 0.50) & (df_losses["mfe_pts"] < 1.00)])
    mfe_10_15 = len(df_losses[(df_losses["mfe_pts"] >= 1.00) & (df_losses["mfe_pts"] < 1.50)])
    mfe_15_20 = len(df_losses[(df_losses["mfe_pts"] >= 1.50) & (df_losses["mfe_pts"] < 2.00)])

    print(f"  - Instant Reversal (MFE < $0.50): {mfe_0_05} trades ({mfe_0_05/total_losses*100.0:.1f}%) -> Immediate False Breakouts")
    print(f"  - Minor Move ($0.50 <= MFE < $1.00): {mfe_05_10} trades ({mfe_05_10/total_losses*100.0:.1f}%)")
    print(f"  - Moderate Move ($1.00 <= MFE < $1.50): {mfe_10_15} trades ({mfe_10_15/total_losses*100.0:.1f}%)")
    print(f"  - Strong Near-Miss ($1.50 <= MFE < $2.00): {mfe_15_20} trades ({mfe_15_20/total_losses*100.0:.1f}%) -> Came within $0.50 of $20 lock!")
    print("==========================================================================================")

if __name__ == "__main__":
    analyze_losing_trades()
