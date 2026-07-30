#!/usr/bin/env python3
"""
backtest_2024_strat001_vs_strat002.py - Full Year 2024 Out-of-Sample Backtest Engine

Queries MetaTrader 5 for 2024 Full Year Historical Rates (Jan 1, 2024 to Dec 31, 2024):
Replays both strategies across 365 Days of 2024:
1. STRAT-001: M5 Fair Value Gap (FVG) 3-Burst Strategy
2. STRAT-002: M5 CHOCH / BOS (Change of Character / Break of Structure) 3-Burst Strategy

Outputs 2024 Stats: Total Trades, Win Rate, Profit Factor, Net PnL, Daily Avg, Worst Day, Best Day, Worst Week, Best Week, Profitable Days %, Profitable Weeks %
"""

import sys
import os
sys.path.insert(0, os.path.abspath("."))
import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta
import MetaTrader5 as mt5

def run_2024_full_year_backtest():
    print("==========================================================================================")
    print("  FULL YEAR 2024 OUT-OF-SAMPLE BACKTEST: STRAT-001 (M5 FVG) VS STRAT-002 (M5 CHOCH/BOS)")
    print("  Dataset: 2024 Full Year (Jan 1, 2024 to Dec 31, 2024 ~ 350,000 M1 Candles)")
    print("==========================================================================================")

    if not mt5.initialize():
        print("[ERROR] MetaTrader 5 terminal not connected.")
        return

    symbol = "XAUUSDz"
    start_2024 = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    end_2024 = datetime(2024, 12, 31, 23, 59, 59, tzinfo=timezone.utc)

    print(f"[DATA] Querying MT5 for 2024 M5 historical rates...")
    m5_rates = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_M5, start_2024 - timedelta(days=2), end_2024)
    if m5_rates is None or len(m5_rates) == 0:
        symbol = "XAUUSD"
        m5_rates = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_M5, start_2024 - timedelta(days=2), end_2024)

    if m5_rates is None or len(m5_rates) == 0:
        print("[ERROR] Failed to fetch 2024 M5 rates from MT5. Checking local cache...")
        return

    df_m5 = pd.DataFrame(m5_rates)
    df_m5["time_dt"] = pd.to_datetime(df_m5["time"], unit="s", utc=True)

    # Signal 1: STRAT-001 (M5 FVG)
    df_m5["fvg_bull"] = df_m5["low"] - df_m5["high"].shift(2)
    df_m5["fvg_bear"] = df_m5["low"].shift(2) - df_m5["high"]

    # Signal 2: STRAT-002 (Strictly Causal M5 CHOCH / BOS Breakout)
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

    df_m5["causal_bos_bull"] = np.where((df_m5["close"] > df_m5["confirmed_sh"].shift(1)) & (df_m5["close"].shift(1) <= df_m5["confirmed_sh"].shift(1)), 1, 0)
    df_m5["causal_bos_bear"] = np.where((df_m5["close"] < df_m5["confirmed_sl"].shift(1)) & (df_m5["close"].shift(1) >= df_m5["confirmed_sl"].shift(1)), 1, 0)

    # Query 2024 M1 in 30-day chunks
    print("[DATA] Querying MT5 for 2024 M1 historical candles (365 days)...")
    m1_chunks = []
    curr_start = start_2024
    while curr_start < end_2024:
        curr_end = min(curr_start + timedelta(days=30), end_2024)
        chunk = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_M1, curr_start, curr_end)
        if chunk is not None and len(chunk) > 0:
            m1_chunks.append(pd.DataFrame(chunk))
        curr_start = curr_end

    if not m1_chunks:
        print("[ERROR] Failed to fetch 2024 M1 rates from MT5.")
        return

    df_m1 = pd.concat(m1_chunks, ignore_index=True).drop_duplicates(subset=["time"]).sort_values("time")
    df_m1["time_dt"] = pd.to_datetime(df_m1["time"], unit="s", utc=True)

    print(f"[DATA] Successfully loaded {len(df_m1)} M1 bars and {len(df_m5)} M5 bars for 2024.\n")

    # Merge M5 features onto M1
    df_m1 = pd.merge_asof(df_m1.sort_values("time_dt"), 
                        df_m5[["time_dt", "fvg_bull", "fvg_bear", "causal_bos_bull", "causal_bos_bear"]].sort_values("time_dt"), 
                        on="time_dt", direction="backward")

    m1_arr = df_m1[["time", "open", "high", "low", "close"]].values
    time_map = {int(row[0]): idx for idx, row in enumerate(m1_arr)}

    def replay_2024_strategy(signals_df, direction_col, sl_usd=1.50, tp_usd=2.25, cooldown_sec=300):
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

            iso_year, iso_week, _ = t_dt.isocalendar()
            week_key = f"{iso_year}-W{iso_week:02d}"

            # 3 burst positions per signal
            for _ in range(3):
                executed.append({
                    "date": t_dt.strftime("%Y-%m-%d"),
                    "week_key": week_key,
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

        # Daily breakdown
        daily_df = df_exec.groupby("date").agg(
            trades=("result", "count"),
            wins=("result", lambda x: (x == "HIT_TP").sum()),
            losses=("result", lambda x: (x == "HIT_SL").sum()),
            pnl=("pnl", "sum")
        ).reset_index()

        worst_day = daily_df.sort_values("pnl").iloc[0]
        best_day = daily_df.sort_values("pnl", ascending=False).iloc[0]
        profitable_days = len(daily_df[daily_df["pnl"] > 0])

        # Weekly breakdown
        weekly_df = df_exec.groupby("week_key").agg(
            trades=("result", "count"),
            wins=("result", lambda x: (x == "HIT_TP").sum()),
            losses=("result", lambda x: (x == "HIT_SL").sum()),
            pnl=("pnl", "sum"),
            start_date=("date", "min"),
            end_date=("date", "max")
        ).reset_index()

        worst_week = weekly_df.sort_values("pnl").iloc[0]
        best_week = weekly_df.sort_values("pnl", ascending=False).iloc[0]
        profitable_weeks = len(weekly_df[weekly_df["pnl"] > 0])

        return {
            "total_pos": total_pos,
            "wins": wins,
            "losses": losses,
            "win_rate": win_rate,
            "profit_factor": pf,
            "net_pnl": total_pnl,
            "total_days": len(daily_df),
            "avg_daily_pnl": daily_df["pnl"].mean(),
            "profitable_days": profitable_days,
            "worst_day": worst_day,
            "best_day": best_day,
            "total_weeks": len(weekly_df),
            "profitable_weeks": profitable_weeks,
            "worst_week": worst_week,
            "best_week": best_week
        }

    # 1. Replay STRAT-001 (M5 FVG)
    df_m1["fvg_sig"] = np.where(df_m1["fvg_bull"] > 0.50, "BUY", np.where(df_m1["fvg_bear"] > 0.50, "SELL", "NONE"))
    fvg_sigs = df_m1[df_m1["fvg_sig"] != "NONE"].copy()
    res_s1 = replay_2024_strategy(fvg_sigs, "fvg_sig", sl_usd=1.50, tp_usd=2.25, cooldown_sec=300)

    # 2. Replay STRAT-002 (Strictly Causal M5 CHOCH / BOS)
    df_m1["bos_sig"] = np.where(df_m1["causal_bos_bull"] == 1, "BUY", np.where(df_m1["causal_bos_bear"] == 1, "SELL", "NONE"))
    bos_sigs = df_m1[df_m1["bos_sig"] != "NONE"].copy()
    res_s2 = replay_2024_strategy(bos_sigs, "bos_sig", sl_usd=1.50, tp_usd=2.25, cooldown_sec=300)

    print("==========================================================================================")
    print("  FULL YEAR 2024 OUT-OF-SAMPLE BACKTEST STATS SUMMARY")
    print("==========================================================================================")

    def print_strategy_report(name, res):
        w_d = res["worst_day"]
        b_d = res["best_day"]
        w_w = res["worst_week"]
        b_w = res["best_week"]

        print(f"[{name}] OVERALL 2024 PERFORMANCE:")
        print(f"  - Total Positions Fired (2024): {res['total_pos']:5d}")
        print(f"  - Total Won Positions: {res['wins']:5d} | Total Lost Positions: {res['losses']:5d}")
        print(f"  - 2024 OVERALL WIN RATE: {res['win_rate']:.1f}%")
        print(f"  - PROFIT FACTOR: {res['profit_factor']}")
        print(f"  - TOTAL 2024 NET REALIZED PROFIT: ${res['net_pnl']:+.2f}")
        print(f"  - AVERAGE DAILY PROFIT: ${res['avg_daily_pnl']:+.2f} / day\n")

        print(f"[{name}] DAILY CONSISTENCY & EXTREME BOUNDS:")
        print(f"  - Total Trading Sessions: {res['total_days']} Days")
        print(f"  - PROFITABLE SESSIONS: {res['profitable_days']} Days ({res['profitable_days']/res['total_days']*100.0:.1f}% of 2024 days)")
        print(f"  - WORST SINGLE DAY: {w_d['date']} -> ${w_d['pnl']:+.2f} ({int(w_d['wins'])}W / {int(w_d['losses'])}L)")
        print(f"  - BEST SINGLE DAY:  {b_d['date']} -> ${b_d['pnl']:+.2f} ({int(b_d['wins'])}W / {int(b_d['losses'])}L)\n")

        print(f"[{name}] WEEKLY CONSISTENCY & EXTREME BOUNDS:")
        print(f"  - Total Calendar Weeks: {res['total_weeks']} Weeks")
        print(f"  - PROFITABLE WEEKS: {res['profitable_weeks']} Weeks ({res['profitable_weeks']/res['total_weeks']*100.0:.1f}% of 2024 weeks)")
        print(f"  - WORST SINGLE WEEK: {w_w['start_date']} to {w_w['end_date']} ({w_w['week_key']}) -> ${w_w['pnl']:+.2f}")
        print(f"  - BEST SINGLE WEEK:  {b_w['start_date']} to {b_w['end_date']} ({b_w['week_key']}) -> ${b_w['pnl']:+.2f}")
        print("------------------------------------------------------------------------------------------\n")

    print_strategy_report("STRAT-001 (M5 FVG 3-BURST)", res_s1)
    print_strategy_report("STRAT-002 (M5 CHOCH/BOS 3-BURST)", res_s2)
    print("==========================================================================================")

if __name__ == "__main__":
    run_2024_full_year_backtest()
