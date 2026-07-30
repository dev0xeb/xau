#!/usr/bin/env python3
"""
simulate_scalping_stacking.py - Scalping Stacking Simulation Engine

Tests 3 Scalping Stacking models across 365 Days of XAUUSD Data (~360,000 M1 Candles):

Model 1 (Instant 3-Order Burst):
  - Triggers 3 orders simultaneously at signal time.
  - Each order gets SL = -$1.50, TP = +$2.25.
  - 5-Minute Cooldown (300s) between bursts.

Model 2 (Progressive M1 Stacking - Max 3 Positions per FVG):
  - Order 1 enters at M1 candle 0 (when FVG detected).
  - Order 2 enters at M1 candle 1 (1 min later from new candle price).
  - Order 3 enters at M1 candle 2 (2 min later from new candle price).
  - Max 3 positions per 5-minute FVG cycle. Each gets SL = -$1.50, TP = +$2.25 from its own entry price.

Model 3 (Progressive M1 Stacking - Shared Anchor SL/TP):
  - Order 1, 2, 3 enter on consecutive M1 candles (0, 1, 2 min).
  - All 3 orders share the EXACT SAME fixed SL price and TP price anchored to Order 1's entry price.
"""

import sys
import os
sys.path.insert(0, os.path.abspath("."))
import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta
import MetaTrader5 as mt5

def run_stacking_simulation():
    print("==========================================================================================")
    print("  1-YEAR SCALPING STACKING SIMULATION ENGINE (XAUUSD / 365 DAYS)")
    print("==========================================================================================")

    if not mt5.initialize():
        print("[ERROR] MetaTrader 5 terminal not connected.")
        return

    symbol = "XAUUSDz"
    end_dt = datetime.now(timezone.utc)
    start_dt = end_dt - timedelta(days=365)

    print(f"[DATA] Querying MT5 for 1-Year M5 historical rates...")
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
    print("[DATA] Querying MT5 for 1-Year M1 historical candles (365 days)...")
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

    # Merge M5 FVG onto M1
    df_m1 = pd.merge_asof(df_m1.sort_values("time_dt"), df_m5[["time_dt", "fvg_type"]].sort_values("time_dt"), on="time_dt", direction="backward")

    m1_arr = df_m1[["time", "open", "high", "low", "close"]].values
    time_map = {int(row[0]): idx for idx, row in enumerate(m1_arr)}

    raw_signals = df_m1[df_m1["fvg_type"] != "NONE"].to_dict("records")

    # Helper: Replay 1 position forward
    def replay_single_pos(start_idx, entry_p, direction, init_sl, init_tp):
        exit_reason = None
        pnl = 0.0
        end_idx = min(start_idx + 120, len(m1_arr))

        for i in range(start_idx + 1, end_idx):
            high = m1_arr[i][2]
            low = m1_arr[i][3]

            if direction == "BUY":
                if low <= init_sl:
                    exit_reason = "HIT_SL"
                    pnl = - (abs(entry_p - init_sl) * 10.0)
                    break
                if high >= init_tp:
                    exit_reason = "HIT_TP"
                    pnl = (abs(init_tp - entry_p) * 10.0)
                    break
            elif direction == "SELL":
                if high >= init_sl:
                    exit_reason = "HIT_SL"
                    pnl = - (abs(init_sl - entry_p) * 10.0)
                    break
                if low <= init_tp:
                    exit_reason = "HIT_TP"
                    pnl = (abs(entry_p - init_tp) * 10.0)
                    break

        return exit_reason, pnl

    # Model 1: Instant 3-Order Burst (300s Cooldown)
    def replay_model_1():
        executed = []
        last_t = 0

        for sig in raw_signals:
            t_sec = int(sig["time"])
            t_dt = sig["time_dt"]
            direction = sig["fvg_type"]

            if 18 <= t_dt.hour < 20:
                continue
            if (t_sec - last_t) < 300:
                continue

            last_t = t_sec
            entry_p = sig["close"]
            init_sl = round(entry_p - 1.50, 2) if direction == "BUY" else round(entry_p + 1.50, 2)
            init_tp = round(entry_p + 2.25, 2) if direction == "BUY" else round(entry_p - 2.25, 2)

            start_idx = time_map.get(t_sec)
            if start_idx is None:
                continue

            res, pnl_per_pos = replay_single_pos(start_idx, entry_p, direction, init_sl, init_tp)

            for pos_num in range(1, 4):
                executed.append({"date": t_dt.strftime("%Y-%m-%d"), "result": res, "pnl": pnl_per_pos})

        df_e = pd.DataFrame(executed)
        wins = len(df_e[df_e["result"] == "HIT_TP"])
        losses = len(df_e[df_e["result"] == "HIT_SL"])
        wr = (wins / len(df_e)) * 100.0
        pnl = df_e["pnl"].sum()
        pf = round((wins * 22.50) / (losses * 15.0), 2)
        days = df_e["date"].nunique()

        return {"trades": len(df_e), "wins": wins, "losses": losses, "wr": wr, "pf": pf, "pnl": pnl, "daily_pnl": pnl/days}

    # Model 2: Progressive M1 Stacking (Max 3 Positions, Each 1 Min Apart, Individual SL/TP)
    def replay_model_2():
        executed = []
        last_t = 0

        for sig in raw_signals:
            t_sec = int(sig["time"])
            t_dt = sig["time_dt"]
            direction = sig["fvg_type"]

            if 18 <= t_dt.hour < 20:
                continue
            if (t_sec - last_t) < 300:
                continue

            last_t = t_sec
            start_idx = time_map.get(t_sec)
            if start_idx is None:
                continue

            # Stack up to 3 positions on 3 consecutive M1 candles (start_idx, start_idx+1, start_idx+2)
            for offset in range(3):
                idx = start_idx + offset
                if idx >= len(m1_arr):
                    break
                entry_p = m1_arr[idx][4] # close price of M1 candle
                init_sl = round(entry_p - 1.50, 2) if direction == "BUY" else round(entry_p + 1.50, 2)
                init_tp = round(entry_p + 2.25, 2) if direction == "BUY" else round(entry_p - 2.25, 2)

                res, pnl = replay_single_pos(idx, entry_p, direction, init_sl, init_tp)
                executed.append({"date": t_dt.strftime("%Y-%m-%d"), "result": res, "pnl": pnl})

        df_e = pd.DataFrame(executed)
        wins = len(df_e[df_e["result"] == "HIT_TP"])
        losses = len(df_e[df_e["result"] == "HIT_SL"])
        wr = (wins / len(df_e)) * 100.0
        pnl = df_e["pnl"].sum()
        pf = round((wins * 22.50) / (losses * 15.0), 2)
        days = df_e["date"].nunique()

        return {"trades": len(df_e), "wins": wins, "losses": losses, "wr": wr, "pf": pf, "pnl": pnl, "daily_pnl": pnl/days}

    # Model 3: Progressive M1 Stacking (Max 3 Positions, Each 1 Min Apart, Shared Anchor SL/TP)
    def replay_model_3():
        executed = []
        last_t = 0

        for sig in raw_signals:
            t_sec = int(sig["time"])
            t_dt = sig["time_dt"]
            direction = sig["fvg_type"]

            if 18 <= t_dt.hour < 20:
                continue
            if (t_sec - last_t) < 300:
                continue

            last_t = t_sec
            start_idx = time_map.get(t_sec)
            if start_idx is None:
                continue

            anchor_entry = sig["close"]
            anchor_sl = round(anchor_entry - 1.50, 2) if direction == "BUY" else round(anchor_entry + 1.50, 2)
            anchor_tp = round(anchor_entry + 2.25, 2) if direction == "BUY" else round(anchor_entry - 2.25, 2)

            for offset in range(3):
                idx = start_idx + offset
                if idx >= len(m1_arr):
                    break
                entry_p = m1_arr[idx][4]
                res, pnl = replay_single_pos(idx, entry_p, direction, anchor_sl, anchor_tp)
                executed.append({"date": t_dt.strftime("%Y-%m-%d"), "result": res, "pnl": pnl})

        df_e = pd.DataFrame(executed)
        wins = len(df_e[df_e["result"] == "HIT_TP"])
        losses = len(df_e[df_e["result"] == "HIT_SL"])
        wr = (wins / len(df_e)) * 100.0
        pnl = df_e["pnl"].sum()
        gross_p = df_e[df_e["result"] == "HIT_TP"]["pnl"].sum()
        gross_l = df_e[df_e["result"] == "HIT_SL"]["pnl"].abs().sum()
        pf = round(gross_p / gross_l, 2) if gross_l > 0 else 99.0
        days = df_e["date"].nunique()

        return {"trades": len(df_e), "wins": wins, "losses": losses, "wr": wr, "pf": pf, "pnl": pnl, "daily_pnl": pnl/days}

    m1 = replay_model_1()
    m2 = replay_model_2()
    m3 = replay_model_3()

    print("==========================================================================================")
    print("  SCALPING STACKING 1-YEAR SIMULATION RESULTS (365 DAYS / 312 SESSIONS)")
    print("==========================================================================================")
    print(f"1. Model 1 (Instant 3-Order Burst at Signal Time):")
    print(f"   Positions: {m1['trades']:5d} | Wins: {m1['wins']:5d} | Losses: {m1['losses']:5d} | Win Rate: {m1['wr']:.1f}% | PF: {m1['pf']} | Net PnL: ${m1['pnl']:+.2f} (${m1['daily_pnl']:+.2f}/day)\n")

    print(f"2. Model 2 (Progressive 1-Min Stacking - Individual SL/TP):")
    print(f"   Positions: {m2['trades']:5d} | Wins: {m2['wins']:5d} | Losses: {m2['losses']:5d} | Win Rate: {m2['wr']:.1f}% | PF: {m2['pf']} | Net PnL: ${m2['pnl']:+.2f} (${m2['daily_pnl']:+.2f}/day)\n")

    print(f"3. Model 3 (Progressive 1-Min Stacking - Shared Anchor SL/TP):")
    print(f"   Positions: {m3['trades']:5d} | Wins: {m3['wins']:5d} | Losses: {m3['losses']:5d} | Win Rate: {m3['wr']:.1f}% | PF: {m3['pf']} | Net PnL: ${m3['pnl']:+.2f} (${m3['daily_pnl']:+.2f}/day)")
    print("==========================================================================================")

if __name__ == "__main__":
    run_stacking_simulation()
