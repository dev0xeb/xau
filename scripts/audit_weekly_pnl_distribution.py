#!/usr/bin/env python3
"""
audit_weekly_pnl_distribution.py - 1-Year Weekly PnL & Risk Distribution Audit

Groups Model 1 (Instant 3-Burst Scalping Strategy) simulation results into 52 calendar weeks:
- Best Trading Week PnL, Win Rate, and positions taken
- Worst Trading Week PnL, Win Rate, and positions taken
- Percentage of Profitable Trading Weeks vs Losing Trading Weeks
- Average Weekly Profit ($/week)
"""

import sys
import os
sys.path.insert(0, os.path.abspath("."))
import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta
import MetaTrader5 as mt5

def audit_weekly_pnl():
    print("==========================================================================================")
    print("  1-YEAR WEEKLY RISK AUDIT: MODEL 1 (M5 FVG INSTANT 3-BURST STRATEGY - OPTION A)")
    print("  Dataset: 365 Days of XAUUSD Historical Bars (~360,000 M1 Candles)")
    print("==========================================================================================")

    if not mt5.initialize():
        print("[ERROR] MetaTrader 5 terminal not connected.")
        return

    symbol = "XAUUSDz"
    end_dt = datetime.now(timezone.utc)
    start_dt = end_dt - timedelta(days=365)

    m5_rates = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_M5, start_dt - timedelta(days=2), end_dt)
    if m5_rates is None or len(m5_rates) == 0:
        symbol = "XAUUSD"
        m5_rates = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_M5, start_dt - timedelta(days=2), end_dt)

    df_m5 = pd.DataFrame(m5_rates)
    df_m5["time_dt"] = pd.to_datetime(df_m5["time"], unit="s", utc=True)
    df_m5["fvg_bull"] = df_m5["low"] - df_m5["high"].shift(2)
    df_m5["fvg_bear"] = df_m5["low"].shift(2) - df_m5["high"]
    df_m5["fvg_type"] = np.where(df_m5["fvg_bull"] > 0.50, "BUY", np.where(df_m5["fvg_bear"] > 0.50, "SELL", "NONE"))

    # Query M1 in 30-day chunks
    m1_chunks = []
    curr_start = start_dt
    while curr_start < end_dt:
        curr_end = min(curr_start + timedelta(days=30), end_dt)
        chunk = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_M1, curr_start, curr_end)
        if chunk is not None and len(chunk) > 0:
            m1_chunks.append(pd.DataFrame(chunk))
        curr_start = curr_end

    if not m1_chunks:
        print("[ERROR] Failed to fetch M1 rates.")
        return

    df_m1 = pd.concat(m1_chunks, ignore_index=True).drop_duplicates(subset=["time"]).sort_values("time")
    df_m1["time_dt"] = pd.to_datetime(df_m1["time"], unit="s", utc=True)

    df_m1 = pd.merge_asof(df_m1.sort_values("time_dt"), df_m5[["time_dt", "fvg_type"]].sort_values("time_dt"), on="time_dt", direction="backward")

    m1_arr = df_m1[["time", "open", "high", "low", "close"]].values
    time_map = {int(row[0]): idx for idx, row in enumerate(m1_arr)}

    raw_signals = df_m1[df_m1["fvg_type"] != "NONE"].to_dict("records")

    executed_positions = []
    last_t = 0
    cooldown_sec = 300

    for sig in raw_signals:
        t_sec = int(sig["time"])
        t_dt = sig["time_dt"]
        direction = sig["fvg_type"]

        if 18 <= t_dt.hour < 20:
            continue
        if (t_sec - last_t) < cooldown_sec:
            continue

        last_t = t_sec

        entry_p = sig["close"]
        init_sl = round(entry_p - 1.50, 2) if direction == "BUY" else round(entry_p + 1.50, 2)
        init_tp = round(entry_p + 2.25, 2) if direction == "BUY" else round(entry_p - 2.25, 2)

        start_idx = time_map.get(t_sec)
        if start_idx is None:
            continue

        exit_reason = None
        pnl_per_pos = 0.0

        end_idx = min(start_idx + 120, len(m1_arr))
        for i in range(start_idx + 1, end_idx):
            high = m1_arr[i][2]
            low = m1_arr[i][3]

            if direction == "BUY":
                if low <= init_sl:
                    exit_reason = "HIT_SL"
                    pnl_per_pos = -15.0
                    break
                if high >= init_tp:
                    exit_reason = "HIT_TP"
                    pnl_per_pos = 22.50
                    break
            elif direction == "SELL":
                if high >= init_sl:
                    exit_reason = "HIT_SL"
                    pnl_per_pos = -15.0
                    break
                if low <= init_tp:
                    exit_reason = "HIT_TP"
                    pnl_per_pos = 22.50
                    break

        # 3 Burst positions per signal
        iso_year, iso_week, _ = t_dt.isocalendar()
        week_key = f"{iso_year}-W{iso_week:02d}"

        for pos_num in range(1, 4):
            executed_positions.append({
                "date": t_dt.strftime("%Y-%m-%d"),
                "week_key": week_key,
                "result": exit_reason,
                "pnl": pnl_per_pos
            })

    df_exec = pd.DataFrame(executed_positions)
    
    weekly_df = df_exec.groupby("week_key").agg(
        positions=("result", "count"),
        wins=("result", lambda x: (x == "HIT_TP").sum()),
        losses=("result", lambda x: (x == "HIT_SL").sum()),
        pnl=("pnl", "sum"),
        start_date=("date", "min"),
        end_date=("date", "max")
    ).reset_index()

    weekly_df["win_rate"] = (weekly_df["wins"] / weekly_df["positions"]) * 100.0

    best_week = weekly_df.sort_values("pnl", ascending=False).iloc[0]
    worst_week = weekly_df.sort_values("pnl").iloc[0]
    profitable_weeks = len(weekly_df[weekly_df["pnl"] > 0])
    losing_weeks = len(weekly_df[weekly_df["pnl"] < 0])

    print("==========================================================================================")
    print("  1-YEAR WEEKLY PERFORMANCE SUMMARY")
    print("==========================================================================================")
    print(f"BEST TRADING WEEK IN 1 YEAR:")
    print(f"   - Week Period: {best_week['start_date']} to {best_week['end_date']} ({best_week['week_key']})")
    print(f"   - Total Burst Positions Fired: {int(best_week['positions'])} positions")
    print(f"   - Won Positions: {int(best_week['wins'])} | Lost Positions: {int(best_week['losses'])}")
    print(f"   - Best Week Win Rate: {best_week['win_rate']:.1f}%")
    print(f"   - BEST WEEKLY REALIZED PROFIT: ${best_week['pnl']:+.2f}\n")

    print(f"WORST TRADING WEEK IN 1 YEAR:")
    print(f"   - Week Period: {worst_week['start_date']} to {worst_week['end_date']} ({worst_week['week_key']})")
    print(f"   - Total Burst Positions Fired: {int(worst_week['positions'])} positions")
    print(f"   - Won Positions: {int(worst_week['wins'])} | Lost Positions: {int(worst_week['losses'])}")
    print(f"   - Worst Week Win Rate: {worst_week['win_rate']:.1f}%")
    print(f"   - WORST WEEKLY REALIZED PROFIT: ${worst_week['pnl']:+.2f}\n")

    print(f"WEEKLY CONSISTENCY & INCOME BREAKDOWN:")
    print(f"   - Total Active Trading Weeks: {len(weekly_df)} Weeks")
    print(f"   - PROFITABLE TRADING WEEKS: {profitable_weeks} Weeks ({profitable_weeks/len(weekly_df)*100.0:.1f}% of all weeks!)")
    print(f"   - LOSING TRADING WEEKS: {losing_weeks} Weeks ({losing_weeks/len(weekly_df)*100.0:.1f}%)")
    print(f"   - AVERAGE WEEKLY PROFIT: ${weekly_df['pnl'].mean():+.2f} / week")
    print("==========================================================================================")

if __name__ == "__main__":
    audit_weekly_pnl()
