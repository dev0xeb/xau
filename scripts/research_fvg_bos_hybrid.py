#!/usr/bin/env python3
"""
research_fvg_bos_hybrid.py - M5 FVG + CHOCH/BOS Hybrid Confluence Engine

Tests combining M5 Fair Value Gap (FVG) displacement with M5 Structure Alignment (BOS/CHOCH):
- BUY: Active M5 Bullish FVG + M5 Bullish BOS Structural Break.
- SELL: Active M5 Bearish FVG + M5 Bearish BOS Structural Break.

Replays 1 Year of XAUUSD Data (353,464 M1 Candles / 312 Days).
"""

import sys
import os
sys.path.insert(0, os.path.abspath("."))
import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta
import MetaTrader5 as mt5

def run_hybrid_research():
    print("==========================================================================================")
    print("  HYBRID RESEARCH: M5 FVG + M5 CHOCH/BOS CONFLUENCE ENGINE (1 YEAR)")
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

    # M5 FVG
    df_m5["fvg_bull"] = df_m5["low"] - df_m5["high"].shift(2)
    df_m5["fvg_bear"] = df_m5["low"].shift(2) - df_m5["high"]

    # M5 Swing Highs/Lows for CHOCH & BOS (5-bar fractal)
    df_m5["swing_high"] = np.where((df_m5["high"] > df_m5["high"].shift(1)) & 
                                   (df_m5["high"] > df_m5["high"].shift(2)) & 
                                   (df_m5["high"] > df_m5["high"].shift(-1)) & 
                                   (df_m5["high"] > df_m5["high"].shift(-2)), df_m5["high"], np.nan)

    df_m5["swing_low"] = np.where((df_m5["low"] < df_m5["low"].shift(1)) & 
                                  (df_m5["low"] < df_m5["low"].shift(2)) & 
                                  (df_m5["low"] < df_m5["low"].shift(-1)) & 
                                  (df_m5["low"] < df_m5["low"].shift(-2)), df_m5["low"], np.nan)

    df_m5["recent_sh"] = df_m5["swing_high"].ffill()
    df_m5["recent_sl"] = df_m5["swing_low"].ffill()

    # CHOCH / BOS alignment
    df_m5["m5_structure"] = np.where(df_m5["close"] > df_m5["recent_sh"].shift(1), "BULLISH",
                            np.where(df_m5["close"] < df_m5["recent_sl"].shift(1), "BEARISH", "NEUTRAL"))

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

    df_m1 = pd.merge_asof(df_m1.sort_values("time_dt"), df_m5[["time_dt", "fvg_bull", "fvg_bear", "m5_structure"]].sort_values("time_dt"), on="time_dt", direction="backward")

    m1_arr = df_m1[["time", "open", "high", "low", "close"]].values
    time_map = {int(row[0]): idx for idx, row in enumerate(m1_arr)}

    # Hybrid Signal: Active FVG + Matching Structure
    df_m1["hybrid_sig"] = np.where((df_m1["fvg_bull"] > 0.50) & (df_m1["m5_structure"] == "BULLISH"), "BUY",
                          np.where((df_m1["fvg_bear"] > 0.50) & (df_m1["m5_structure"] == "BEARISH"), "SELL", "NONE"))

    raw_signals = df_m1[df_m1["hybrid_sig"] != "NONE"].to_dict("records")

    executed_positions = []
    last_t = 0
    cooldown_sec = 300

    for sig in raw_signals:
        t_sec = int(sig["time"])
        t_dt = sig["time_dt"]
        direction = sig["hybrid_sig"]

        if 18 <= t_dt.hour < 20 or (t_sec - last_t) < cooldown_sec:
            continue

        last_t = t_sec

        entry_p = sig["close"]
        init_sl = round(entry_p - 1.50, 2) if direction == "BUY" else round(entry_p + 1.50, 2)
        init_tp = round(entry_p + 2.25, 2) if direction == "BUY" else round(entry_p - 2.25, 2)

        start_idx = time_map.get(t_sec)
        if start_idx is None:
            continue

        exit_reason = None
        pnl = 0.0

        end_idx = min(start_idx + 120, len(m1_arr))
        for i in range(start_idx + 1, end_idx):
            high = m1_arr[i][2]
            low = m1_arr[i][3]

            if direction == "BUY":
                if low <= init_sl:
                    exit_reason = "HIT_SL"
                    pnl = -15.0
                    break
                if high >= init_tp:
                    exit_reason = "HIT_TP"
                    pnl = 22.50
                    break
            elif direction == "SELL":
                if high >= init_sl:
                    exit_reason = "HIT_SL"
                    pnl = -15.0
                    break
                if low <= init_tp:
                    exit_reason = "HIT_TP"
                    pnl = 22.50
                    break

        for _ in range(3):
            executed_positions.append({
                "date": t_dt.strftime("%Y-%m-%d"),
                "result": exit_reason,
                "pnl": pnl
            })

    df_exec = pd.DataFrame(executed_positions)
    total_p = len(df_exec)
    wins = len(df_exec[df_exec["result"] == "HIT_TP"])
    losses = len(df_exec[df_exec["result"] == "HIT_SL"])
    win_rate = (wins / total_p) * 100.0 if total_p > 0 else 0.0
    total_pnl = df_exec["pnl"].sum()
    gross_p = wins * 22.50
    gross_l = losses * 15.0
    pf = round(gross_p / gross_l, 2) if gross_l > 0 else 99.0

    daily_df = df_exec.groupby("date")["pnl"].sum().reset_index()

    print("==========================================================================================")
    print("  HYBRID M5 FVG + M5 CHOCH/BOS CONFLUENCE RESULTS (1 YEAR / 312 SESSIONS)")
    print("==========================================================================================")
    print(f"Total Burst Positions Executed: {total_p:5d}")
    print(f"Total Won Positions: {wins:5d} | Total Lost Positions: {losses:5d}")
    print(f"HYBRID WIN RATE: {win_rate:.1f}%")
    print(f"HYBRID PROFIT FACTOR: {pf}")
    print(f"TOTAL 1-YEAR NET REALIZED PROFIT: ${total_pnl:+.2f}")
    print(f"AVERAGE DAILY PROFIT: ${daily_df['pnl'].mean():+.2f} / day")
    print(f"PROFITABLE SESSIONS: {len(daily_df[daily_df['pnl']>0])}/{len(daily_df)} ({len(daily_df[daily_df['pnl']>0])/len(daily_df)*100.0:.1f}%)")
    print("==========================================================================================")

if __name__ == "__main__":
    run_hybrid_research()
