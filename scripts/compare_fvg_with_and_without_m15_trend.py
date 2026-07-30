#!/usr/bin/env python3
"""
compare_fvg_with_and_without_m15_trend.py - M5 FVG Strategy Comparison (With vs Without M15 Trend Filter)

Evaluates 90 Days of Data (May 1 to July 30, 2026) across:
1. M5 FVG WITHOUT M15 Trend Filter (Raw M5 FVG Signals)
2. M5 FVG WITH M15 Trend Filter (EMA 20 vs EMA 50)
3. M5 FVG WITH M15 Trend Filter + 15s Cooldown

Under:
  - Option A: 1.5:1 R:R ($2.25 TP / $1.50 SL)
  - Option B: 1.2:1 R:R ($1.80 TP / $1.50 SL)
"""

import sys
import os
sys.path.insert(0, os.path.abspath("."))
import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta
import MetaTrader5 as mt5

def run_fvg_trend_comparison():
    print("==========================================================================================")
    print("  M5 FAIR VALUE GAP (FVG) COMPARISON: WITH VS WITHOUT M15 TREND FILTER (90 DAYS)")
    print("==========================================================================================")

    if not mt5.initialize():
        print("[ERROR] MetaTrader 5 terminal not connected.")
        return

    symbol = "XAUUSDz"
    end_dt = datetime.now(timezone.utc)
    start_dt = end_dt - timedelta(days=90)

    # Fetch M15
    m15_rates = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_M15, start_dt - timedelta(days=3), end_dt)
    if m15_rates is None or len(m15_rates) == 0:
        symbol = "XAUUSD"
        m15_rates = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_M15, start_dt - timedelta(days=3), end_dt)

    df_m15 = pd.DataFrame(m15_rates)
    df_m15["time_dt"] = pd.to_datetime(df_m15["time"], unit="s", utc=True)
    df_m15["ema20"] = df_m15["close"].ewm(span=20, adjust=False).mean()
    df_m15["ema50"] = df_m15["close"].ewm(span=50, adjust=False).mean()
    df_m15["m15_trend"] = np.where(df_m15["ema20"] > df_m15["ema50"], "UPTREND", "DOWNTREND")

    # Fetch M5 FVG
    m5_rates = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_M5, start_dt - timedelta(days=2), end_dt)
    df_m5 = pd.DataFrame(m5_rates)
    df_m5["time_dt"] = pd.to_datetime(df_m5["time"], unit="s", utc=True)
    df_m5["fvg_bull"] = df_m5["low"] - df_m5["high"].shift(2)
    df_m5["fvg_bear"] = df_m5["low"].shift(2) - df_m5["high"]
    df_m5["fvg_type"] = np.where(df_m5["fvg_bull"] > 0.50, "BUY", np.where(df_m5["fvg_bear"] > 0.50, "SELL", "NONE"))

    # Fetch M1
    m1_chunks = []
    curr_start = start_dt
    while curr_start < end_dt:
        curr_end = min(curr_start + timedelta(days=15), end_dt)
        chunk = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_M1, curr_start, curr_end)
        if chunk is not None and len(chunk) > 0:
            m1_chunks.append(pd.DataFrame(chunk))
        curr_start = curr_end

    df_m1 = pd.concat(m1_chunks, ignore_index=True).drop_duplicates(subset=["time"]).sort_values("time")
    df_m1["time_dt"] = pd.to_datetime(df_m1["time"], unit="s", utc=True)

    # Merge Trends onto M1
    df_m1 = pd.merge_asof(df_m1.sort_values("time_dt"), df_m15[["time_dt", "m15_trend"]].sort_values("time_dt"), on="time_dt", direction="backward")
    df_m1 = pd.merge_asof(df_m1.sort_values("time_dt"), df_m5[["time_dt", "fvg_type"]].sort_values("time_dt"), on="time_dt", direction="backward")
    df_m1["m15_trend"] = df_m1["m15_trend"].fillna("FLAT")

    m1_arr = df_m1[["time", "open", "high", "low", "close"]].values
    time_map = {int(row[0]): idx for idx, row in enumerate(m1_arr)}

    def detailed_trade_analysis(signals_df, sl_usd=1.50, tp_usd=2.25, use_trend_filter=False, cooldown_sec=300):
        records = signals_df.to_dict("records")
        executed = []
        last_t = 0

        for sig in records:
            t_sec = int(sig["time"])
            t_dt = sig["time_dt"]
            direction = sig["fvg_type"]
            trend = sig["m15_trend"]

            if 18 <= t_dt.hour < 20:
                continue

            if use_trend_filter:
                if (direction == "BUY" and trend != "UPTREND") or (direction == "SELL" and trend != "DOWNTREND"):
                    continue

            if cooldown_sec > 0:
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
            mfe_pts = 0.0

            end_idx = min(start_idx + 120, len(m1_arr))
            for i in range(start_idx + 1, end_idx):
                high = m1_arr[i][2]
                low = m1_arr[i][3]

                if direction == "BUY":
                    mfe_pts = max(mfe_pts, round(high - entry_p, 2))
                    if low <= init_sl:
                        exit_reason = "HIT_SL"
                        pnl = - (sl_usd * 10.0)
                        break
                    if high >= init_tp:
                        exit_reason = "HIT_TP"
                        pnl = tp_usd * 10.0
                        break
                elif direction == "SELL":
                    mfe_pts = max(mfe_pts, round(entry_p - low, 2))
                    if high >= init_sl:
                        exit_reason = "HIT_SL"
                        pnl = - (sl_usd * 10.0)
                        break
                    if low <= init_tp:
                        exit_reason = "HIT_TP"
                        pnl = tp_usd * 10.0
                        break

            sig_record = {
                "date": t_dt.strftime("%Y-%m-%d"),
                "time": t_dt.strftime("%H:%M:%S"),
                "dir": direction,
                "entry_p": entry_p,
                "result": exit_reason,
                "pnl": pnl,
                "mfe_pts": mfe_pts
            }
            executed.append(sig_record)

        df_exec = pd.DataFrame(executed)
        if df_exec.empty:
            return {}

        total_trades = len(df_exec)
        wins = len(df_exec[df_exec["result"] == "HIT_TP"])
        losses = len(df_exec[df_exec["result"] == "HIT_SL"])
        win_rate = (wins / total_trades) * 100.0 if total_trades > 0 else 0.0
        total_pnl = df_exec["pnl"].sum()
        gross_profit = wins * (tp_usd * 10.0)
        gross_loss = losses * (sl_usd * 10.0)
        pf = round(gross_profit / gross_loss, 2) if gross_loss > 0 else 99.0

        unique_days = df_exec["date"].nunique()
        avg_trades_per_day = round(total_trades / unique_days, 1)
        avg_wins_per_day = round(wins / unique_days, 1)
        avg_losses_per_day = round(losses / unique_days, 1)

        return {
            "total_trades": total_trades,
            "wins": wins,
            "losses": losses,
            "win_rate": win_rate,
            "profit_factor": pf,
            "net_pnl": total_pnl,
            "unique_days": unique_days,
            "avg_trades_day": avg_trades_per_day,
            "avg_wins_day": avg_wins_per_day,
            "avg_losses_day": avg_losses_per_day
        }

    raw_fvg_signals = df_m1[df_m1["fvg_type"] != "NONE"].copy()

    # Option A: 1.5:1 R:R ($2.25 TP / $1.50 SL)
    res_A_no_trend = detailed_trade_analysis(raw_fvg_signals, sl_usd=1.50, tp_usd=2.25, use_trend_filter=False, cooldown_sec=300)
    res_A_with_trend = detailed_trade_analysis(raw_fvg_signals, sl_usd=1.50, tp_usd=2.25, use_trend_filter=True, cooldown_sec=300)

    # Option B: 1.2:1 R:R ($1.80 TP / $1.50 SL)
    res_B_no_trend = detailed_trade_analysis(raw_fvg_signals, sl_usd=1.50, tp_usd=1.80, use_trend_filter=False, cooldown_sec=300)
    res_B_with_trend = detailed_trade_analysis(raw_fvg_signals, sl_usd=1.50, tp_usd=1.80, use_trend_filter=True, cooldown_sec=300)

    print("==========================================================================================")
    print("  OPTION A: 1.5:1 R:R ($2.25 TP / $1.50 SL) - M15 TREND FILTER IMPACT")
    print("==========================================================================================")
    print(f"1. WITHOUT M15 Trend Filter (Raw M5 FVG):")
    print(f"   Trades: {res_A_no_trend['total_trades']:4d} | Wins: {res_A_no_trend['wins']:3d} | Losses: {res_A_no_trend['losses']:4d} | Win Rate: {res_A_no_trend['win_rate']:.1f}% | PF: {res_A_no_trend['profit_factor']} | Net PnL: ${res_A_no_trend['net_pnl']:+.2f}")
    print(f"   Avg Trades/Day: {res_A_no_trend['avg_trades_day']} ({res_A_no_trend['avg_wins_day']} Wins / {res_A_no_trend['avg_losses_day']} Losses)\n")

    print(f"2. WITH M15 Trend Filter (EMA 20 vs EMA 50):")
    print(f"   Trades: {res_A_with_trend['total_trades']:4d} | Wins: {res_A_with_trend['wins']:3d} | Losses: {res_A_with_trend['losses']:4d} | Win Rate: {res_A_with_trend['win_rate']:.1f}% | PF: {res_A_with_trend['profit_factor']} | Net PnL: ${res_A_with_trend['net_pnl']:+.2f}")
    print(f"   Avg Trades/Day: {res_A_with_trend['avg_trades_day']} ({res_A_with_trend['avg_wins_day']} Wins / {res_A_with_trend['avg_losses_day']} Losses)")
    print("==========================================================================================\n")

    print("==========================================================================================")
    print("  OPTION B: 1.2:1 R:R ($1.80 TP / $1.50 SL) - M15 TREND FILTER IMPACT")
    print("==========================================================================================")
    print(f"1. WITHOUT M15 Trend Filter (Raw M5 FVG):")
    print(f"   Trades: {res_B_no_trend['total_trades']:4d} | Wins: {res_B_no_trend['wins']:3d} | Losses: {res_B_no_trend['losses']:4d} | Win Rate: {res_B_no_trend['win_rate']:.1f}% | PF: {res_B_no_trend['profit_factor']} | Net PnL: ${res_B_no_trend['net_pnl']:+.2f}")
    print(f"   Avg Trades/Day: {res_B_no_trend['avg_trades_day']} ({res_B_no_trend['avg_wins_day']} Wins / {res_B_no_trend['avg_losses_day']} Losses)\n")

    print(f"2. WITH M15 Trend Filter (EMA 20 vs EMA 50):")
    print(f"   Trades: {res_B_with_trend['total_trades']:4d} | Wins: {res_B_with_trend['wins']:3d} | Losses: {res_B_with_trend['losses']:4d} | Win Rate: {res_B_with_trend['win_rate']:.1f}% | PF: {res_B_with_trend['profit_factor']} | Net PnL: ${res_B_with_trend['net_pnl']:+.2f}")
    print(f"   Avg Trades/Day: {res_B_with_trend['avg_trades_day']} ({res_B_with_trend['avg_wins_day']} Wins / {res_B_with_trend['avg_losses_day']} Losses)")
    print("==========================================================================================")

if __name__ == "__main__":
    run_fvg_trend_comparison()
