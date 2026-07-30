#!/usr/bin/env python3
"""
backtest_parquet_processed_data.py - Backtest Engine Using Local Processed Parquet Datasets

Loads historical data from data/processed/XAUUSD_M1_v1.0.0.parquet or features parquet.
Replays trade strategy across the dataset comparing:
1. Baseline Strategy (Unfiltered 2.5:1 R:R | $2.00 SL / $5.00 TP)
2. Option 3 Strategy (M15 Trend Filter: EMA 20 vs EMA 50)
3. Master Strategy (M15 Trend Filter + 15s Entry Cooldown)
"""

import sys
import os
sys.path.insert(0, os.path.abspath("."))
import pandas as pd
import numpy as np
from datetime import datetime, timezone

def run_parquet_backtest():
    print("==========================================================================================")
    print("  HISTORICAL BACKTEST USING LOCAL PROCESSED PARQUET DATASET")
    print("  Execution Rules: SL = -$2.00 ($20 risk), TP = +$5.00 ($50 target) | 2.5:1 R:R")
    print("==========================================================================================")

    data_path = "data/processed/XAUUSD_M1_v1.0.0.parquet"
    features_path = "data/processed/XAUUSD_M1_FEATURES_v1.0.0.parquet"

    if os.path.exists(data_path):
        print(f"[DATA] Loading local dataset: {data_path}")
        df = pd.read_parquet(data_path)
    elif os.path.exists(features_path):
        print(f"[DATA] Loading local features dataset: {features_path}")
        df = pd.read_parquet(features_path)
    else:
        print("[ERROR] Local parquet dataset not found in data/processed/")
        return

    print(f"[DATA] Successfully loaded {len(df)} historical M1 candle rows.")
    print(f"Columns available: {list(df.columns)}")

    # Ensure timestamp column is datetime
    time_col = None
    for c in ["timestamp", "time", "time_dt", "datetime"]:
        if c in df.columns:
            time_col = c
            break

    if time_col:
        df["time_dt"] = pd.to_datetime(df[time_col], utc=True)
    else:
        df["time_dt"] = pd.date_range(start="2026-01-01", periods=len(df), freq="1min", tz=timezone.utc)

    df["time_sec"] = (df["time_dt"].astype("int64") // 10**9)

    # Normalize column names
    col_map = {c.lower(): c for c in df.columns}
    open_c = col_map.get("open", "open")
    high_c = col_map.get("high", "high")
    low_c = col_map.get("low", "low")
    close_c = col_map.get("close", "close")

    df["open"] = df[open_c]
    df["high"] = df[high_c]
    df["low"] = df[low_c]
    df["close"] = df[close_c]

    # Calculate M15 EMA 20 vs EMA 50 for M15 Trend Filter
    df_m15 = df.set_index("time_dt").resample("15min").agg({
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last"
    }).dropna().reset_index()

    df_m15["ema20"] = df_m15["close"].ewm(span=20, adjust=False).mean()
    df_m15["ema50"] = df_m15["close"].ewm(span=50, adjust=False).mean()
    df_m15["m15_trend"] = np.where(df_m15["ema20"] > df_m15["ema50"], "UPTREND", "DOWNTREND")

    # Merge M15 trend back into M1
    df = pd.merge_asof(df.sort_values("time_dt"), df_m15[["time_dt", "m15_trend"]].sort_values("time_dt"), on="time_dt", direction="backward")
    df["m15_trend"] = df["m15_trend"].fillna("FLAT")

    # Feature Calculation
    df["hl_range"] = df["high"] - df["low"]
    df["volatility_atr"] = df["hl_range"].rolling(14).mean().fillna(1.50)
    df["momentum_velocity"] = df["close"].diff(3).fillna(0.0)
    df["compression_ratio"] = (df["hl_range"] / df["hl_range"].rolling(10).mean()).fillna(1.0)

    # Behavior Model Scoring
    df["score_b1"] = np.where((df["momentum_velocity"].abs() > 1.2) & (df["compression_ratio"] > 1.2), 0.85, 0.20)
    df["score_b2"] = np.where(df["momentum_velocity"].abs() > 1.8, 0.90, 0.15)
    df["score_b3"] = np.where((df["compression_ratio"] < 0.8) & (df["momentum_velocity"].abs() > 0.8), 0.88, 0.10)
    df["score_b4"] = np.where((df["volatility_atr"] > 2.0) & (df["momentum_velocity"].abs() > 1.0), 0.92, 0.25)

    df["mean_conviction"] = (df["score_b1"] + df["score_b2"] + df["score_b3"] + df["score_b4"]) / 4.0

    df["is_signal"] = df["mean_conviction"] >= 0.50
    df["direction"] = np.where(df["momentum_velocity"] > 0, "BUY", "SELL")

    signal_rows = df[df["is_signal"]].to_dict("records")
    total_candles = len(df)
    total_signals = len(signal_rows)

    print(f"[BACKTEST] Identified {total_signals} raw signal candidates across {total_candles} candles.\n")

    def simulate_replay(signal_list, use_trend_filter=False, cooldown_sec=0):
        tp_count = 0
        sl_count = 0
        total_pnl = 0.0
        last_t = 0
        executed_signals = []

        m1_arr = df[["time_sec", "open", "high", "low", "close"]].to_dict("records")
        m1_dict = {r["time_sec"]: r for r in m1_arr}

        for sig in signal_list:
            t_sec = sig["time_sec"]
            t_dt = sig["time_dt"]
            direction = sig["direction"]
            trend = sig["m15_trend"]

            # Exclude FOMC / High impact news window
            if 18 <= t_dt.hour < 20:
                continue

            # M15 Trend Filter
            if use_trend_filter:
                if (direction == "BUY" and trend != "UPTREND") or (direction == "SELL" and trend != "DOWNTREND"):
                    continue

            # Cooldown Filter
            if cooldown_sec > 0:
                if (t_sec - last_t) < cooldown_sec:
                    continue

            last_t = t_sec
            executed_signals.append(sig)

            entry_p = sig["close"]
            init_sl = round(entry_p - 2.00, 2) if direction == "BUY" else round(entry_p + 2.00, 2)
            init_tp = round(entry_p + 5.00, 2) if direction == "BUY" else round(entry_p - 5.00, 2)

            exit_reason = None
            pnl = 0.0

            # Forward scan up to 120 minutes (7200 sec)
            for step in range(1, 121):
                fwd_sec = t_sec + (step * 60)
                if fwd_sec not in m1_dict:
                    continue
                r = m1_dict[fwd_sec]
                high = r["high"]
                low = r["low"]

                if direction == "BUY":
                    if low <= init_sl:
                        exit_reason = "HIT_SL"
                        pnl = -20.0
                        break
                    if high >= init_tp:
                        exit_reason = "HIT_TP"
                        pnl = 50.0
                        break
                elif direction == "SELL":
                    if high >= init_sl:
                        exit_reason = "HIT_SL"
                        pnl = -20.0
                        break
                    if low <= init_tp:
                        exit_reason = "HIT_TP"
                        pnl = 50.0
                        break

            if exit_reason == "HIT_TP":
                tp_count += 1
            elif exit_reason == "HIT_SL":
                sl_count += 1

            total_pnl += pnl

        total_trades = len(executed_signals)
        win_rate = (tp_count / total_trades) * 100.0 if total_trades > 0 else 0.0
        gross_profit = tp_count * 50.0
        gross_loss = sl_count * 20.0
        pf = round(gross_profit / gross_loss, 2) if gross_loss > 0 else 99.0

        return {
            "total_trades": total_trades,
            "tp": tp_count,
            "sl": sl_count,
            "win_rate": win_rate,
            "profit_factor": pf,
            "net_pnl": total_pnl
        }

    r_base = simulate_replay(signal_rows, use_trend_filter=False, cooldown_sec=0)
    r_opt3 = simulate_replay(signal_rows, use_trend_filter=True, cooldown_sec=0)
    r_master = simulate_replay(signal_rows, use_trend_filter=True, cooldown_sec=15)

    print("==========================================================================================")
    print("  PROCESSED PARQUET DATASET BACKTEST RESULTS SUMMARY")
    print("==========================================================================================")
    print(f"0. Baseline Strategy (Unfiltered):")
    print(f"   Trades: {r_base['total_trades']:4d} | TP Hits: {r_base['tp']:3d} | SL Hits: {r_base['sl']:4d} | WinRate: {r_base['win_rate']:.1f}% | PF: {r_base['profit_factor']} | Net PnL: ${r_base['net_pnl']:+.2f}\n")

    print(f"1. Option 3 Strategy (M15 Trend Filter Alone):")
    print(f"   Trades: {r_opt3['total_trades']:4d} | TP Hits: {r_opt3['tp']:3d} | SL Hits: {r_opt3['sl']:4d} | WinRate: {r_opt3['win_rate']:.1f}% | PF: {r_opt3['profit_factor']} | Net PnL: ${r_opt3['net_pnl']:+.2f}\n")

    print(f"2. Master Strategy (M15 Trend Filter + 15s Cooldown):")
    print(f"   Trades: {r_master['total_trades']:4d} | TP Hits: {r_master['tp']:3d} | SL Hits: {r_master['sl']:4d} | WinRate: {r_master['win_rate']:.1f}% | PF: {r_master['profit_factor']} | Net PnL: ${r_master['net_pnl']:+.2f}")
    print("==========================================================================================")

if __name__ == "__main__":
    run_parquet_backtest()
