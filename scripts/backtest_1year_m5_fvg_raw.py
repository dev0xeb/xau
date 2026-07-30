#!/usr/bin/env python3
"""
backtest_1year_m5_fvg_raw.py - 1-Year Backtest Engine WITH 1-Minute Cooldown (cooldown_sec = 60s)

Queries MetaTrader 5 for 365 Days of historical M5 and M1 bars (~360,000 M1 candles):
Replays Raw M5 FVG strategy comparing:
- 300s Cooldown (5 Minutes)
- 60s Cooldown (1 Minute)
- 0s Cooldown (No Cooldown)

Across Option A (1.5:1 R:R | $2.25 TP / $1.50 SL) and Option B (1.2:1 R:R | $1.80 TP / $1.50 SL)
"""

import sys
import os
sys.path.insert(0, os.path.abspath("."))
import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta
import MetaTrader5 as mt5

def run_1year_cooldown_comparison():
    print("==========================================================================================")
    print("  1-YEAR BACKTEST ENGINE: 1-MINUTE COOLDOWN (60s) VS 5-MINUTE (300s) VS 0s")
    print("  Dataset: 365 Days of XAUUSD Historical Bars (~360,000 M1 Candles)")
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

    def replay_1year_cooldown(sl_usd=1.50, tp_usd=2.25, cooldown_sec=60):
        records = df_m1[df_m1["fvg_type"] != "NONE"].to_dict("records")
        executed = []
        last_t = 0

        for sig in records:
            t_sec = int(sig["time"])
            t_dt = sig["time_dt"]
            direction = sig["fvg_type"]

            if 18 <= t_dt.hour < 20:
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

            executed.append({
                "date": t_dt.strftime("%Y-%m-%d"),
                "pnl": pnl,
                "result": exit_reason
            })

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

        daily_df = df_exec.groupby("date").agg(
            trades=("result", "count"),
            wins=("result", lambda x: (x == "HIT_TP").sum()),
            losses=("result", lambda x: (x == "HIT_SL").sum()),
            pnl=("pnl", "sum")
        ).reset_index()

        daily_df["win_rate"] = (daily_df["wins"] / daily_df["trades"]) * 100.0

        worst_day = daily_df.sort_values("pnl").iloc[0]
        best_day = daily_df.sort_values("pnl", ascending=False).iloc[0]
        profitable_days = len(daily_df[daily_df["pnl"] > 0])
        losing_days = len(daily_df[daily_df["pnl"] < 0])

        unique_days = len(daily_df)
        avg_trades_day = round(total_trades / unique_days, 1)

        return {
            "total_trades": total_trades,
            "wins": wins,
            "losses": losses,
            "win_rate": win_rate,
            "profit_factor": pf,
            "net_pnl": total_pnl,
            "unique_days": unique_days,
            "avg_trades_day": avg_trades_day,
            "worst_day": worst_day,
            "best_day": best_day,
            "profitable_days": profitable_days,
            "losing_days": losing_days,
            "avg_daily_pnl": daily_df["pnl"].mean()
        }

    res_A_300 = replay_1year_cooldown(sl_usd=1.50, tp_usd=2.25, cooldown_sec=300)
    res_A_60 = replay_1year_cooldown(sl_usd=1.50, tp_usd=2.25, cooldown_sec=60)
    res_A_0 = replay_1year_cooldown(sl_usd=1.50, tp_usd=2.25, cooldown_sec=0)

    res_B_300 = replay_1year_cooldown(sl_usd=1.50, tp_usd=1.80, cooldown_sec=300)
    res_B_60 = replay_1year_cooldown(sl_usd=1.50, tp_usd=1.80, cooldown_sec=60)
    res_B_0 = replay_1year_cooldown(sl_usd=1.50, tp_usd=1.80, cooldown_sec=0)

    print("==========================================================================================")
    print("  1-YEAR COOLDOWN COMPARISON: 5-MIN (300s) VS 1-MIN (60s) VS NO COOLDOWN (0s)")
    print("==========================================================================================")
    print("1. OPTION A: 1.5:1 R:R ($2.25 TP / $1.50 SL)")
    print(f"   - 5-Min Cooldown (300s): Trades: {res_A_300['total_trades']:5d} | WinRate: {res_A_300['win_rate']:.1f}% | PF: {res_A_300['profit_factor']} | Net PnL: ${res_A_300['net_pnl']:+.2f} | Avg Trades/Day: {res_A_300['avg_trades_day']}")
    print(f"   - 1-Min Cooldown (60s):  Trades: {res_A_60['total_trades']:5d} | WinRate: {res_A_60['win_rate']:.1f}% | PF: {res_A_60['profit_factor']} | Net PnL: ${res_A_60['net_pnl']:+.2f} | Avg Trades/Day: {res_A_60['avg_trades_day']}")
    print(f"   - No Cooldown (0s):      Trades: {res_A_0['total_trades']:5d} | WinRate: {res_A_0['win_rate']:.1f}% | PF: {res_A_0['profit_factor']} | Net PnL: ${res_A_0['net_pnl']:+.2f} | Avg Trades/Day: {res_A_0['avg_trades_day']}\n")

    print("2. OPTION B: 1.2:1 R:R ($1.80 TP / $1.50 SL)")
    print(f"   - 5-Min Cooldown (300s): Trades: {res_B_300['total_trades']:5d} | WinRate: {res_B_300['win_rate']:.1f}% | PF: {res_B_300['profit_factor']} | Net PnL: ${res_B_300['net_pnl']:+.2f} | Avg Trades/Day: {res_B_300['avg_trades_day']}")
    print(f"   - 1-Min Cooldown (60s):  Trades: {res_B_60['total_trades']:5d} | WinRate: {res_B_60['win_rate']:.1f}% | PF: {res_B_60['profit_factor']} | Net PnL: ${res_B_60['net_pnl']:+.2f} | Avg Trades/Day: {res_B_60['avg_trades_day']}")
    print(f"   - No Cooldown (0s):      Trades: {res_B_0['total_trades']:5d} | WinRate: {res_B_0['win_rate']:.1f}% | PF: {res_B_0['profit_factor']} | Net PnL: ${res_B_0['net_pnl']:+.2f} | Avg Trades/Day: {res_B_0['avg_trades_day']}")
    print("==========================================================================================")

if __name__ == "__main__":
    run_1year_cooldown_comparison()
