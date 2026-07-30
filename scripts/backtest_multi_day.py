#!/usr/bin/env python3
"""
backtest_multi_day.py - 60-Day Institutional Historical Backtest Engine

Queries MetaTrader 5 for 60 trading days of historical M1 and M15 price bars (~60,000 M1 candles):
- Calculates real-time feature vectors (Volatility ATR, Momentum Velocity, Compression Ratio)
- Evaluates behavior scoring ensemble (BEH-001 to BEH-004)
- Replays trade executions across 3 strategies:
    1. Baseline Strategy (Unfiltered 2.5:1 R:R | $2.00 SL / $5.00 TP)
    2. Option 3 Strategy (M15 Trend Filter Alone)
    3. Master Strategy (M15 Trend Filter + 15s Entry Cooldown)
"""

import sys
import os
sys.path.insert(0, os.path.abspath("."))
import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta
import MetaTrader5 as mt5

def run_60day_backtest():
    print("==========================================================================================")
    print("  60-DAY INSTITUTIONAL HISTORICAL BACKTEST ENGINE (XAUUSD)")
    print("  Execution Rules: SL = -$2.00 ($20 risk), TP = +$5.00 ($50 target) | 2.5:1 R:R")
    print("==========================================================================================")

    if not mt5.initialize():
        print("[ERROR] MetaTrader 5 terminal not connected.")
        return

    symbol = "XAUUSDz"
    end_dt = datetime.now(timezone.utc)
    start_dt = end_dt - timedelta(days=60)

    # 1. Fetch M15 rates
    print(f"[DATA] Querying MT5 for 60-day M15 historical rates ({start_dt.strftime('%Y-%m-%d')} to {end_dt.strftime('%Y-%m-%d')})...")
    m15_rates = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_M15, start_dt - timedelta(days=3), end_dt)
    if m15_rates is None or len(m15_rates) == 0:
        symbol = "XAUUSD"
        m15_rates = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_M15, start_dt - timedelta(days=3), end_dt)

    df_m15 = pd.DataFrame(m15_rates)
    df_m15["time_dt"] = pd.to_datetime(df_m15["time"], unit="s", utc=True)
    df_m15["ema20"] = df_m15["close"].ewm(span=20, adjust=False).mean()
    df_m15["ema50"] = df_m15["close"].ewm(span=50, adjust=False).mean()

    # 2. Fetch M1 rates in 10-day chunks to prevent memory limits
    print(f"[DATA] Querying MT5 for 60-day M1 historical rates...")
    all_m1_chunks = []
    curr_start = start_dt

    while curr_start < end_dt:
        curr_end = min(curr_start + timedelta(days=10), end_dt)
        chunk = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_M1, curr_start, curr_end)
        if chunk is not None and len(chunk) > 0:
            all_m1_chunks.append(pd.DataFrame(chunk))
        curr_start = curr_end

    if not all_m1_chunks:
        print("[ERROR] Failed to fetch M1 rates from MT5.")
        return

    df_m1 = pd.concat(all_m1_chunks, ignore_index=True).drop_duplicates(subset=["time"]).sort_values("time")
    df_m1["time_dt"] = pd.to_datetime(df_m1["time"], unit="s", utc=True)

    print(f"[DATA] Retrived {len(df_m1)} M1 candles and {len(df_m15)} M15 candles across 60 days.\n")

    # Feature Engineering on M1
    df_m1["hl_range"] = df_m1["high"] - df_m1["low"]
    df_m1["volatility_atr"] = df_m1["hl_range"].rolling(14).mean().fillna(1.50)
    df_m1["momentum_velocity"] = df_m1["close"].diff(3).fillna(0.0)
    df_m1["compression_ratio"] = (df_m1["hl_range"] / df_m1["hl_range"].rolling(10).mean()).fillna(1.0)

    # Behavior Ensemble Scoring
    df_m1["score_b1"] = np.where((df_m1["momentum_velocity"].abs() > 1.2) & (df_m1["compression_ratio"] > 1.2), 0.85, 0.20)
    df_m1["score_b2"] = np.where(df_m1["momentum_velocity"].abs() > 1.8, 0.90, 0.15)
    df_m1["score_b3"] = np.where((df_m1["compression_ratio"] < 0.8) & (df_m1["momentum_velocity"].abs() > 0.8), 0.88, 0.10)
    df_m1["score_b4"] = np.where((df_m1["volatility_atr"] > 2.0) & (df_m1["momentum_velocity"].abs() > 1.0), 0.92, 0.25)

    df_m1["mean_conviction"] = (df_m1["score_b1"] + df_m1["score_b2"] + df_m1["score_b3"] + df_m1["score_b4"]) / 4.0

    df_m1["is_signal"] = df_m1["mean_conviction"] >= 0.50
    df_m1["direction"] = np.where(df_m1["momentum_velocity"] > 0, "BUY", "SELL")

    # Fast Merge M15 Trend (EMA20 vs EMA50)
    df_m15_sub = df_m15[["time_dt", "ema20", "ema50"]].sort_values("time_dt")
    df_m15_sub["m15_trend"] = np.where(df_m15_sub["ema20"] > df_m15_sub["ema50"], "UPTREND", "DOWNTREND")

    df_m1 = pd.merge_asof(df_m1.sort_values("time_dt"), df_m15_sub[["time_dt", "m15_trend"]], on="time_dt", direction="backward")
    df_m1["m15_trend"] = df_m1["m15_trend"].fillna("FLAT")

    signal_rows = df_m1[df_m1["is_signal"]].to_dict("records")
    print(f"[BACKTEST] Identified {len(signal_rows)} raw signal candidates across 60 trading days.\n")

    # Build fast array lookup for forward scanning
    m1_arr = df_m1[["time", "open", "high", "low", "close"]].values
    time_map = {int(row[0]): idx for idx, row in enumerate(m1_arr)}

    def replay_signals(signals, use_trend_filter=False, cooldown_sec=0):
        tp_count = 0
        sl_count = 0
        total_pnl = 0.0
        last_t = 0
        executed = []

        for sig in signals:
            t_sec = int(sig["time"])
            t_dt = sig["time_dt"]
            direction = sig["direction"]
            trend = sig["m15_trend"]

            # Exclude FOMC / High impact news window
            if 18 <= t_dt.hour < 20:
                continue

            if use_trend_filter:
                if (direction == "BUY" and trend != "UPTREND") or (direction == "SELL" and trend != "DOWNTREND"):
                    continue

            if cooldown_sec > 0:
                if (t_sec - last_t) < cooldown_sec:
                    continue

            last_t = t_sec
            executed.append(sig)

            entry_p = sig["close"]
            init_sl = round(entry_p - 2.00, 2) if direction == "BUY" else round(entry_p + 2.00, 2)
            init_tp = round(entry_p + 5.00, 2) if direction == "BUY" else round(entry_p - 5.00, 2)

            start_idx = time_map.get(t_sec)
            if start_idx is None:
                continue

            exit_reason = None
            pnl = 0.0

            # Scan up to 120 forward candles
            end_idx = min(start_idx + 120, len(m1_arr))
            for i in range(start_idx + 1, end_idx):
                high = m1_arr[i][2]
                low = m1_arr[i][3]

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

        total_trades = len(executed)
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

    r_base = replay_signals(signal_rows, use_trend_filter=False, cooldown_sec=0)
    r_opt3 = replay_signals(signal_rows, use_trend_filter=True, cooldown_sec=0)
    r_master = replay_signals(signal_rows, use_trend_filter=True, cooldown_sec=15)

    print("==========================================================================================")
    print("  60-DAY HISTORICAL BACKTEST RESULTS SUMMARY")
    print("==========================================================================================")
    print(f"0. Baseline Strategy (Unfiltered):")
    print(f"   Trades: {r_base['total_trades']:5d} | TP Hits: {r_base['tp']:4d} | SL Hits: {r_base['sl']:5d} | WinRate: {r_base['win_rate']:.1f}% | PF: {r_base['profit_factor']} | Net PnL: ${r_base['net_pnl']:+.2f}\n")

    print(f"1. Option 3 Strategy (M15 Trend Filter Alone):")
    print(f"   Trades: {r_opt3['total_trades']:5d} | TP Hits: {r_opt3['tp']:4d} | SL Hits: {r_opt3['sl']:5d} | WinRate: {r_opt3['win_rate']:.1f}% | PF: {r_opt3['profit_factor']} | Net PnL: ${r_opt3['net_pnl']:+.2f}\n")

    print(f"2. Master Strategy (M15 Trend Filter + 15s Cooldown):")
    print(f"   Trades: {r_master['total_trades']:5d} | TP Hits: {r_master['tp']:4d} | SL Hits: {r_master['sl']:5d} | WinRate: {r_master['win_rate']:.1f}% | PF: {r_master['profit_factor']} | Net PnL: ${r_master['net_pnl']:+.2f}")
    print("==========================================================================================")

if __name__ == "__main__":
    run_60day_backtest()
