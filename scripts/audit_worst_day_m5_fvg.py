#!/usr/bin/env python3
"""
audit_worst_day_m5_fvg.py - Worst Day & Daily Risk Audit (M5 FVG WITH M15 Trend Filter)

Analyzes daily PnL distributions across 76 trading sessions (May 1 to July 30, 2026):
- Worst single day PnL, win rate, and trades taken
- Best single day PnL
- Total profitable trading days vs losing trading days
"""

import sys
import os
sys.path.insert(0, os.path.abspath("."))
import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta
import MetaTrader5 as mt5

def audit_worst_days_with_trend():
    print("==========================================================================================")
    print("  RISK DIAGNOSTIC AUDIT: WORST DAY & DAILY PNL DISTRIBUTION (M5 FVG WITH M15 TREND FILTER)")
    print("==========================================================================================")

    if not mt5.initialize():
        print("[ERROR] MetaTrader 5 terminal not connected.")
        return

    symbol = "XAUUSDz"
    end_dt = datetime.now(timezone.utc)
    start_dt = end_dt - timedelta(days=90)

    # Fetch M15 Trend
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

    df_m1 = pd.merge_asof(df_m1.sort_values("time_dt"), df_m15[["time_dt", "m15_trend"]].sort_values("time_dt"), on="time_dt", direction="backward")
    df_m1 = pd.merge_asof(df_m1.sort_values("time_dt"), df_m5[["time_dt", "fvg_type"]].sort_values("time_dt"), on="time_dt", direction="backward")
    df_m1["m15_trend"] = df_m1["m15_trend"].fillna("FLAT")

    m1_arr = df_m1[["time", "open", "high", "low", "close"]].values
    time_map = {int(row[0]): idx for idx, row in enumerate(m1_arr)}

    def analyze_daily_distribution_with_trend(sl_usd=1.50, tp_usd=2.25, cooldown_sec=300):
        raw_signals = df_m1[df_m1["fvg_type"] != "NONE"].to_dict("records")
        executed = []
        last_t = 0

        for sig in raw_signals:
            t_sec = int(sig["time"])
            t_dt = sig["time_dt"]
            direction = sig["fvg_type"]
            trend = sig["m15_trend"]

            if 18 <= t_dt.hour < 20:
                continue

            # M15 Trend Filter Check
            if (direction == "BUY" and trend != "UPTREND") or (direction == "SELL" and trend != "DOWNTREND"):
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

            executed.append({
                "date": t_dt.strftime("%Y-%m-%d"),
                "pnl": pnl,
                "result": exit_reason
            })

        df_exec = pd.DataFrame(executed)
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
        flat_days = len(daily_df[daily_df["pnl"] == 0])

        return {
            "worst_day": worst_day,
            "best_day": best_day,
            "profitable_days": profitable_days,
            "losing_days": losing_days,
            "flat_days": flat_days,
            "total_days": len(daily_df),
            "avg_daily_pnl": daily_df["pnl"].mean()
        }

    res_A = analyze_daily_distribution_with_trend(sl_usd=1.50, tp_usd=2.25, cooldown_sec=300)
    res_B = analyze_daily_distribution_with_trend(sl_usd=1.50, tp_usd=1.80, cooldown_sec=300)

    print("==========================================================================================")
    print("  OPTION A: 1.5:1 R:R ($2.25 TP / $1.50 SL) WITH M15 TREND FILTER")
    print("==========================================================================================")
    wA = res_A["worst_day"]
    bA = res_A["best_day"]
    print(f"WORST SINGLE DAY PERFORMANCE:")
    print(f"  - Date: {wA['date']}")
    print(f"  - Trades Taken: {int(wA['trades'])}")
    print(f"  - Wins: {int(wA['wins'])} | Losses: {int(wA['losses'])}")
    print(f"  - Worst Day Win Rate: {wA['win_rate']:.1f}%")
    print(f"  - WORST SINGLE DAY PNL (Max Daily Loss): ${wA['pnl']:+.2f}\n")

    print(f"BEST SINGLE DAY PERFORMANCE:")
    print(f"  - Date: {bA['date']}")
    print(f"  - Trades Taken: {int(bA['trades'])} | Wins: {int(bA['wins'])} | Losses: {int(bA['losses'])}")
    print(f"  - BEST SINGLE DAY PNL: ${bA['pnl']:+.2f}\n")

    print(f"DAILY WIN RATIO & CONSISTENCY:")
    print(f"  - Total Active Trading Sessions: {res_A['total_days']} Days")
    print(f"  - Profitable Sessions: {res_A['profitable_days']} Days ({res_A['profitable_days']/res_A['total_days']*100.0:.1f}%)")
    print(f"  - Losing Sessions: {res_A['losing_days']} Days ({res_A['losing_days']/res_A['total_days']*100.0:.1f}%)")
    print(f"  - Average Daily PnL: ${res_A['avg_daily_pnl']:+.2f} / day")
    print("==========================================================================================\n")

    print("==========================================================================================")
    print("  OPTION B: 1.2:1 R:R ($1.80 TP / $1.50 SL) WITH M15 TREND FILTER")
    print("==========================================================================================")
    wB = res_B["worst_day"]
    bB = res_B["best_day"]
    print(f"WORST SINGLE DAY PERFORMANCE:")
    print(f"  - Date: {wB['date']}")
    print(f"  - Trades Taken: {int(wB['trades'])}")
    print(f"  - Wins: {int(wB['wins'])} | Losses: {int(wB['losses'])}")
    print(f"  - Worst Day Win Rate: {wB['win_rate']:.1f}%")
    print(f"  - WORST SINGLE DAY PNL (Max Daily Loss): ${wB['pnl']:+.2f}\n")

    print(f"BEST SINGLE DAY PERFORMANCE:")
    print(f"  - Date: {bB['date']}")
    print(f"  - Trades Taken: {int(bB['trades'])} | Wins: {int(bB['wins'])} | Losses: {int(bB['losses'])}")
    print(f"  - BEST SINGLE DAY PNL: ${bB['pnl']:+.2f}\n")

    print(f"DAILY WIN RATIO & CONSISTENCY:")
    print(f"  - Total Active Trading Sessions: {res_B['total_days']} Days")
    print(f"  - Profitable Sessions: {res_B['profitable_days']} Days ({res_B['profitable_days']/res_B['total_days']*100.0:.1f}%)")
    print(f"  - Losing Sessions: {res_B['losing_days']} Days ({res_B['losing_days']/res_B['total_days']*100.0:.1f}%)")
    print(f"  - Average Daily PnL: ${res_B['avg_daily_pnl']:+.2f} / day")
    print("==========================================================================================")

if __name__ == "__main__":
    audit_worst_days_with_trend()
