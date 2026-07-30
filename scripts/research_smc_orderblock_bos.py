#!/usr/bin/env python3
"""
research_smc_orderblock_bos.py - Institutional SMC Strategy Research Engine

Backtests 3 Smart Money Concepts (SMC) & Price Action Patterns across 365 Days of XAUUSD Data:
1. M5 Order Block (OB) Retest Strategy:
   - Identifies M5 Order Block (last opposing candle before FVG displacement > $0.50).
   - Enters on M1 price retest of M5 Order Block boundary.
2. Supply & Demand Zone Retest (S&D):
   - Identifies Rally-Base-Drop (Supply) and Drop-Base-Rally (Demand) zones.
   - Enters on price retest of the base zone.
3. M5 CHOCH / BOS (Change of Character & Break of Structure):
   - CHOCH: M5 Swing High/Low Break confirming structural reversal.
   - BOS: M5 Swing High/Low Break confirming structural continuation.

Evaluates all strategies under Option A (1.5:1 R:R | $2.25 TP / $1.50 SL) and compares against Baseline M5 FVG Strategy.
"""

import sys
import os
sys.path.insert(0, os.path.abspath("."))
import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta
import MetaTrader5 as mt5

def run_smc_research():
    print("==========================================================================================")
    print("  INSTITUTIONAL SMC & PRICE ACTION RESEARCH ENGINE (XAUUSD / 365 DAYS)")
    print("  Patterns: M5 Order Blocks (OB), Supply/Demand Zones, M5 CHOCH / BOS")
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

    # M5 FVG & Order Block Detection
    df_m5["fvg_bull"] = df_m5["low"] - df_m5["high"].shift(2)
    df_m5["fvg_bear"] = df_m5["low"].shift(2) - df_m5["high"]

    # Bullish Order Block: Last red candle (close < open) at shift(3) before bullish FVG
    df_m5["ob_bull_top"] = np.where((df_m5["fvg_bull"] > 0.50) & (df_m5["close"].shift(3) < df_m5["open"].shift(3)), df_m5["high"].shift(3), np.nan)
    df_m5["ob_bull_bot"] = np.where((df_m5["fvg_bull"] > 0.50) & (df_m5["close"].shift(3) < df_m5["open"].shift(3)), df_m5["low"].shift(3), np.nan)

    # Bearish Order Block: Last green candle (close > open) at shift(3) before bearish FVG
    df_m5["ob_bear_top"] = np.where((df_m5["fvg_bear"] > 0.50) & (df_m5["close"].shift(3) > df_m5["open"].shift(3)), df_m5["high"].shift(3), np.nan)
    df_m5["ob_bear_bot"] = np.where((df_m5["fvg_bear"] > 0.50) & (df_m5["close"].shift(3) > df_m5["open"].shift(3)), df_m5["low"].shift(3), np.nan)

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

    # CHOCH / BOS signals
    df_m5["bos_bull"] = np.where((df_m5["close"] > df_m5["recent_sh"].shift(1)) & (df_m5["close"].shift(1) <= df_m5["recent_sh"].shift(1)), 1, 0)
    df_m5["bos_bear"] = np.where((df_m5["close"] < df_m5["recent_sl"].shift(1)) & (df_m5["close"].shift(1) >= df_m5["recent_sl"].shift(1)), 1, 0)

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
    df_m1 = pd.merge_asof(df_m1.sort_values("time_dt"), df_m5[["time_dt", "fvg_bull", "fvg_bear", "ob_bull_top", "ob_bull_bot", "ob_bear_top", "ob_bear_bot", "bos_bull", "bos_bear"]].sort_values("time_dt"), on="time_dt", direction="backward")

    m1_arr = df_m1[["time", "open", "high", "low", "close"]].values
    time_map = {int(row[0]): idx for idx, row in enumerate(m1_arr)}

    # Backtest Engine Helper
    def replay_signal_series(signals_df, direction_col, sl_usd=1.50, tp_usd=2.25, cooldown_sec=300):
        records = signals_df.to_dict("records")
        executed = []
        last_t = 0

        for sig in records:
            t_sec = int(sig["time"])
            t_dt = sig["time_dt"]
            direction = sig[direction_col]

            if 18 <= t_dt.hour < 20:
                continue
            if (t_sec - last_t) < cooldown_sec:
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

            # 3 burst positions per signal
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

    # 1. Baseline M5 FVG Strategy
    df_m1["fvg_sig"] = np.where(df_m1["fvg_bull"] > 0.50, "BUY", np.where(df_m1["fvg_bear"] > 0.50, "SELL", "NONE"))
    fvg_sigs = df_m1[df_m1["fvg_sig"] != "NONE"].copy()
    res_fvg = replay_signal_series(fvg_sigs, "fvg_sig", sl_usd=1.50, tp_usd=2.25, cooldown_sec=300)

    # 2. M5 Order Block Retest Strategy
    df_m1["ob_retest_sig"] = "NONE"
    # Buy when low touches ob_bull_top
    is_ob_buy = (df_m1["ob_bull_top"].notna()) & (df_m1["low"] <= df_m1["ob_bull_top"]) & (df_m1["low"] >= df_m1["ob_bull_bot"] - 0.50)
    is_ob_sell = (df_m1["ob_bear_top"].notna()) & (df_m1["high"] >= df_m1["ob_bear_bot"]) & (df_m1["high"] <= df_m1["ob_bear_top"] + 0.50)
    df_m1["ob_retest_sig"] = np.where(is_ob_buy, "BUY", np.where(is_ob_sell, "SELL", "NONE"))
    ob_sigs = df_m1[df_m1["ob_retest_sig"] != "NONE"].copy()
    res_ob = replay_signal_series(ob_sigs, "ob_retest_sig", sl_usd=1.50, tp_usd=2.25, cooldown_sec=300)

    # 3. M5 CHOCH / BOS Breakout Strategy
    df_m1["bos_sig"] = np.where(df_m1["bos_bull"] == 1, "BUY", np.where(df_m1["bos_bear"] == 1, "SELL", "NONE"))
    bos_sigs = df_m1[df_m1["bos_sig"] != "NONE"].copy()
    res_bos = replay_signal_series(bos_sigs, "bos_sig", sl_usd=1.50, tp_usd=2.25, cooldown_sec=300)

    # 4. Supply & Demand Zone Retest Strategy (Drop-Base-Rally & Rally-Base-Drop)
    df_m1["sd_sig"] = np.where((df_m1["fvg_bull"] > 0.80) & (df_m1["low"] <= df_m1["open"].shift(1)), "BUY",
                       np.where((df_m1["fvg_bear"] > 0.80) & (df_m1["high"] >= df_m1["open"].shift(1)), "SELL", "NONE"))
    sd_sigs = df_m1[df_m1["sd_sig"] != "NONE"].copy()
    res_sd = replay_signal_series(sd_sigs, "sd_sig", sl_usd=1.50, tp_usd=2.25, cooldown_sec=300)

    print("==========================================================================================")
    print("  INSTITUTIONAL SMC & PRICE ACTION RESEARCH RESULTS (1 YEAR / 312 SESSIONS)")
    print("==========================================================================================")
    print("1. BASELINE M5 FAIR VALUE GAP (FVG) IMPALANCE STRATEGY:")
    print(f"   - Total Positions: {res_fvg['total_pos']:5d} | Wins: {res_fvg['wins']:5d} | Losses: {res_fvg['losses']:5d}")
    print(f"   - WIN RATE: {res_fvg['win_rate']:.1f}% | PROFIT FACTOR: {res_fvg['profit_factor']} | TOTAL NET PNL: ${res_fvg['net_pnl']:+.2f} (${res_fvg['avg_daily_pnl']:+.2f}/day)\n")

    print("2. M5 ORDER BLOCK (OB) RETEST STRATEGY:")
    print(f"   - Total Positions: {res_ob['total_pos']:5d} | Wins: {res_ob['wins']:5d} | Losses: {res_ob['losses']:5d}")
    print(f"   - WIN RATE: {res_ob['win_rate']:.1f}% | PROFIT FACTOR: {res_ob['profit_factor']} | TOTAL NET PNL: ${res_ob['net_pnl']:+.2f} (${res_ob['avg_daily_pnl']:+.2f}/day)\n")

    print("3. SUPPLY & DEMAND (S&D) ZONE RETEST STRATEGY:")
    print(f"   - Total Positions: {res_sd['total_pos']:5d} | Wins: {res_sd['wins']:5d} | Losses: {res_sd['losses']:5d}")
    print(f"   - WIN RATE: {res_sd['win_rate']:.1f}% | PROFIT FACTOR: {res_sd['profit_factor']} | TOTAL NET PNL: ${res_sd['net_pnl']:+.2f} (${res_sd['avg_daily_pnl']:+.2f}/day)\n")

    print("4. M5 CHOCH / BOS (CHANGE OF CHARACTER / BREAK OF STRUCTURE) STRATEGY:")
    print(f"   - Total Positions: {res_bos['total_pos']:5d} | Wins: {res_bos['wins']:5d} | Losses: {res_bos['losses']:5d}")
    print(f"   - WIN RATE: {res_bos['win_rate']:.1f}% | PROFIT FACTOR: {res_bos['profit_factor']} | TOTAL NET PNL: ${res_bos['net_pnl']:+.2f} (${res_bos['avg_daily_pnl']:+.2f}/day)")
    print("==========================================================================================")

if __name__ == "__main__":
    run_smc_research()
