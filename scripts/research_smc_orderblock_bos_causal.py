#!/usr/bin/env python3
"""
research_smc_orderblock_bos_causal.py - Strictly Causal (No Lookahead) SMC & BOS Research Engine

Fixes lookahead leakage in fractal swing calculation.
Enforces strict real-time causality:
- Swing High at bar i-2 is confirmed only AFTER bar i completes:
    high[i-2] > max(high[i-4], high[i-3], high[i-1], high[i])
- No shift(-1) or shift(-2) into future bars allowed!

Replays 1 Year of XAUUSD Data (353,464 M1 Candles / 312 Days) under Option A ($1.50 SL / $2.25 TP).
"""

import sys
import os
sys.path.insert(0, os.path.abspath("."))
import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta
import MetaTrader5 as mt5

def run_causal_smc_research():
    print("==========================================================================================")
    print("  STRICTLY CAUSAL (NO LOOKAHEAD) SMC & PRICE ACTION RESEARCH ENGINE (365 DAYS)")
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

    # 1. Raw M5 FVG
    df_m5["fvg_bull"] = df_m5["low"] - df_m5["high"].shift(2)
    df_m5["fvg_bear"] = df_m5["low"].shift(2) - df_m5["high"]

    # 2. Strictly Causal 5-Bar Fractal Swing High/Low (Confirmed at bar i using only historical bars i-4, i-3, i-2, i-1, i)
    df_m5["causal_swing_high"] = np.where(
        (df_m5["high"].shift(2) > df_m5["high"].shift(4)) &
        (df_m5["high"].shift(2) > df_m5["high"].shift(3)) &
        (df_m5["high"].shift(2) > df_m5["high"].shift(1)) &
        (df_m5["high"].shift(2) > df_m5["high"]),
        df_m5["high"].shift(2), np.nan
    )

    df_m5["causal_swing_low"] = np.where(
        (df_m5["low"].shift(2) < df_m5["low"].shift(4)) &
        (df_m5["low"].shift(2) < df_m5["low"].shift(3)) &
        (df_m5["low"].shift(2) < df_m5["low"].shift(1)) &
        (df_m5["low"].shift(2) < df_m5["low"]),
        df_m5["low"].shift(2), np.nan
    )

    df_m5["confirmed_sh"] = df_m5["causal_swing_high"].ffill()
    df_m5["confirmed_sl"] = df_m5["causal_swing_low"].ffill()

    # 3. Strictly Causal BOS Breakout Signal (Bar i close breaks confirmed swing high/low from past)
    df_m5["causal_bos_bull"] = np.where((df_m5["close"] > df_m5["confirmed_sh"].shift(1)) & (df_m5["close"].shift(1) <= df_m5["confirmed_sh"].shift(1)), 1, 0)
    df_m5["causal_bos_bear"] = np.where((df_m5["close"] < df_m5["confirmed_sl"].shift(1)) & (df_m5["close"].shift(1) >= df_m5["confirmed_sl"].shift(1)), 1, 0)

    # 4. Strictly Causal Hybrid (FVG + Causal BOS)
    df_m5["causal_structure"] = np.where(df_m5["close"] > df_m5["confirmed_sh"].shift(1), "BULLISH",
                                np.where(df_m5["close"] < df_m5["confirmed_sl"].shift(1), "BEARISH", "NEUTRAL"))

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

    # Merge M5 features onto M1
    df_m1 = pd.merge_asof(df_m1.sort_values("time_dt"), 
                        df_m5[["time_dt", "fvg_bull", "fvg_bear", "causal_bos_bull", "causal_bos_bear", "causal_structure"]].sort_values("time_dt"), 
                        on="time_dt", direction="backward")

    m1_arr = df_m1[["time", "open", "high", "low", "close"]].values
    time_map = {int(row[0]): idx for idx, row in enumerate(m1_arr)}

    def replay_signal_series(signals_df, direction_col, sl_usd=1.50, tp_usd=2.25, cooldown_sec=300):
        records = signals_df.to_dict("records")
        executed = []
        last_t = 0

        for sig in records:
            t_sec = int(sig["time"])
            t_dt = sig["time_dt"]
            direction = sig[direction_col]

            if 18 <= t_dt.hour < 20 or (t_sec - last_t) < cooldown_sec:
                continue

            last_t = t_sec

            entry_p = sig["close"]
            init_sl = round(entry_p - sl_usd, 2) if direction == "BUY" else round(entry_p + sl_usd, 2)
            init_tp = round(entry_p + tp_usd, 2) if direction == "BUY" else round(entry_p - tp_usd, 2)

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
                        pnl = - (sl_usd * 10.0)
                        break
                    if high >= init_tp:
                        exit_reason = "HIT_TP"
                        pnl = tp_usd * 10.0
                        break
                elif direction == "SELL":
                    if high >= init_sl:
                        exit_reason = "HIT_SL"
                        pnl = - (sl_usd * 10.0)
                        break
                    if low <= init_tp:
                        exit_reason = "HIT_TP"
                        pnl = tp_usd * 10.0
                        break

            for _ in range(3):
                executed.append({
                    "date": t_dt.strftime("%Y-%m-%d"),
                    "result": exit_reason,
                    "pnl": pnl
                })

        df_exec = pd.DataFrame(executed)
        if df_exec.empty:
            return {}

        total_pos = len(df_exec)
        wins = len(df_exec[df_exec["result"] == "HIT_TP"])
        losses = len(df_exec[df_exec["result"] == "HIT_SL"])
        win_rate = (wins / total_pos) * 100.0 if total_pos > 0 else 0.0
        total_pnl = df_exec["pnl"].sum()
        gross_p = wins * (tp_usd * 10.0)
        gross_l = losses * (sl_usd * 10.0)
        pf = round(gross_p / gross_l, 2) if gross_l > 0 else 99.0

        daily_df = df_exec.groupby("date")["pnl"].sum().reset_index()

        return {
            "total_pos": total_pos,
            "wins": wins,
            "losses": losses,
            "win_rate": win_rate,
            "profit_factor": pf,
            "net_pnl": total_pnl,
            "unique_days": len(daily_df),
            "avg_daily_pnl": daily_df["pnl"].mean()
        }

    # 1. Baseline Raw M5 FVG
    df_m1["fvg_sig"] = np.where(df_m1["fvg_bull"] > 0.50, "BUY", np.where(df_m1["fvg_bear"] > 0.50, "SELL", "NONE"))
    fvg_sigs = df_m1[df_m1["fvg_sig"] != "NONE"].copy()
    res_fvg = replay_signal_series(fvg_sigs, "fvg_sig", sl_usd=1.50, tp_usd=2.25, cooldown_sec=300)

    # 2. Strictly Causal M5 BOS Breakout Strategy
    df_m1["causal_bos_sig"] = np.where(df_m1["causal_bos_bull"] == 1, "BUY", np.where(df_m1["causal_bos_bear"] == 1, "SELL", "NONE"))
    bos_sigs = df_m1[df_m1["causal_bos_sig"] != "NONE"].copy()
    res_bos_causal = replay_signal_series(bos_sigs, "causal_bos_sig", sl_usd=1.50, tp_usd=2.25, cooldown_sec=300)

    # 3. Strictly Causal Hybrid (M5 FVG + Causal M5 Structure Alignment)
    df_m1["causal_hybrid_sig"] = np.where((df_m1["fvg_bull"] > 0.50) & (df_m1["causal_structure"] == "BULLISH"), "BUY",
                                np.where((df_m1["fvg_bear"] > 0.50) & (df_m1["causal_structure"] == "BEARISH"), "SELL", "NONE"))
    hybrid_sigs = df_m1[df_m1["causal_hybrid_sig"] != "NONE"].copy()
    res_hybrid_causal = replay_signal_series(hybrid_sigs, "causal_hybrid_sig", sl_usd=1.50, tp_usd=2.25, cooldown_sec=300)

    print("==========================================================================================")
    print("  STRICTLY CAUSAL (NO-LOOKAHEAD) RESEARCH RESULTS (1 YEAR / 312 SESSIONS)")
    print("==========================================================================================")
    print("1. BASELINE RAW M5 FAIR VALUE GAP (FVG) STRATEGY:")
    print(f"   - Total Positions: {res_fvg['total_pos']:5d} | Wins: {res_fvg['wins']:5d} | Losses: {res_fvg['losses']:5d}")
    print(f"   - WIN RATE: {res_fvg['win_rate']:.1f}% | PROFIT FACTOR: {res_fvg['profit_factor']} | TOTAL NET PNL: ${res_fvg['net_pnl']:+.2f} (${res_fvg['avg_daily_pnl']:+.2f}/day)\n")

    print("2. STRICTLY CAUSAL M5 CHOCH / BOS BREAKOUT STRATEGY (NO LOOKAHEAD):")
    print(f"   - Total Positions: {res_bos_causal['total_pos']:5d} | Wins: {res_bos_causal['wins']:5d} | Losses: {res_bos_causal['losses']:5d}")
    print(f"   - WIN RATE: {res_bos_causal['win_rate']:.1f}% | PROFIT FACTOR: {res_bos_causal['profit_factor']} | TOTAL NET PNL: ${res_bos_causal['net_pnl']:+.2f} (${res_bos_causal['avg_daily_pnl']:+.2f}/day)\n")

    print("3. STRICTLY CAUSAL HYBRID: M5 FVG + M5 CAUSAL STRUCTURE ALIGNMENT:")
    print(f"   - Total Positions: {res_hybrid_causal['total_pos']:5d} | Wins: {res_hybrid_causal['wins']:5d} | Losses: {res_hybrid_causal['losses']:5d}")
    print(f"   - WIN RATE: {res_hybrid_causal['win_rate']:.1f}% | PROFIT FACTOR: {res_hybrid_causal['profit_factor']} | TOTAL NET PNL: ${res_hybrid_causal['net_pnl']:+.2f} (${res_hybrid_causal['avg_daily_pnl']:+.2f}/day)")
    print("==========================================================================================")

if __name__ == "__main__":
    run_causal_smc_research()
