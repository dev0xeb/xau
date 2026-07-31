#!/usr/bin/env python3
"""
test_bar_close_and_trend_filter.py - Simulation of Bar-Close Triggering & H1 Trend Filter

Tests:
1. Exact M5 Bar-Close Triggering (1 signal max per M5 breakout event, identical to backtest).
2. H1 Trend Filter Integration (EMA 50 > EMA 200 for BUY / EMA 50 < EMA 200 for SELL).
"""

import sys
import os
sys.path.insert(0, os.path.abspath("."))
import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta
import MetaTrader5 as mt5

def run_simulation():
    print("==========================================================================================")
    print("  SIMULATION: BAR-CLOSE TRIGGERING & H1 TREND FILTER AUDIT (1-YEAR OOS DATA)")
    print("==========================================================================================")

    if not mt5.initialize():
        print("[ERROR] MetaTrader 5 terminal not connected.")
        return

    symbol = "XAUUSDz" if mt5.symbol_info("XAUUSDz") else "XAUUSD"
    end_dt = datetime.now(timezone.utc)
    start_dt = end_dt - timedelta(days=365)

    print(f"[DATA] Fetching 1-Year M5 rates for '{symbol}'...")
    m5_rates = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_M5, start_dt - timedelta(days=5), end_dt)
    df_m5 = pd.DataFrame(m5_rates)
    df_m5["time_dt"] = pd.to_datetime(df_m5["time"], unit="s", utc=True)

    # 1. Compute H1 EMAs for Trend Filter
    df_h1 = pd.DataFrame(mt5.copy_rates_range(symbol, mt5.TIMEFRAME_H1, start_dt - timedelta(days=30), end_dt))
    df_h1["time_dt"] = pd.to_datetime(df_h1["time"], unit="s", utc=True)
    df_h1["ema50"] = df_h1["close"].ewm(span=50, adjust=False).mean()
    df_h1["ema200"] = df_h1["close"].ewm(span=200, adjust=False).mean()
    df_h1["h1_trend"] = np.where(df_h1["ema50"] > df_h1["ema200"], "BULLISH", np.where(df_h1["ema50"] < df_h1["ema200"], "BEARISH", "NEUTRAL"))

    # Merge H1 Trend into M5
    df_m5 = pd.merge_asof(df_m5.sort_values("time_dt"), df_h1[["time_dt", "h1_trend"]].sort_values("time_dt"), on="time_dt", direction="backward")

    # 2. Causal M5 CHOCH / BOS
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

    # 3. Query M1 rates
    print("[DATA] Querying MT5 M1 rates...")
    m1_chunks = []
    curr_start = start_dt
    while curr_start < end_dt:
        curr_end = min(curr_start + timedelta(days=30), end_dt)
        chunk = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_M1, curr_start, curr_end)
        if chunk is not None and len(chunk) > 0:
            m1_chunks.append(pd.DataFrame(chunk))
        curr_start = curr_end

    df_m1 = pd.concat(m1_chunks, ignore_index=True).drop_duplicates(subset=["time"]).sort_values("time")
    df_m1["time_dt"] = pd.to_datetime(df_m1["time"], unit="s", utc=True)

    df_m1 = pd.merge_asof(df_m1.sort_values("time_dt"), 
                        df_m5[["time_dt", "causal_bos_bull", "causal_bos_bear", "h1_trend"]].sort_values("time_dt"), 
                        on="time_dt", direction="backward")

    m1_arr = df_m1[["time", "open", "high", "low", "close"]].values
    time_map = {int(row[0]): idx for idx, row in enumerate(m1_arr)}

    df_m1["bos_sig"] = np.where(df_m1["causal_bos_bull"] == 1, "BUY", np.where(df_m1["causal_bos_bear"] == 1, "SELL", "NONE"))

    def backtest_strat002(use_trend_filter=False, sl_usd=1.50, tp_usd=2.25, cooldown_sec=300):
        records = df_m1[df_m1["bos_sig"] != "NONE"].to_dict("records")
        executed = []
        last_t = 0

        for sig in records:
            t_sec = int(sig["time"])
            t_dt = sig["time_dt"]
            direction = sig["bos_sig"]
            trend = sig["h1_trend"]
            hour = t_dt.hour

            if 18 <= hour < 20:
                continue

            # Trend Filter Guardrail Check
            if use_trend_filter:
                if direction == "BUY" and trend != "BULLISH":
                    continue
                if direction == "SELL" and trend != "BEARISH":
                    continue

            # Strict 1 signal per M5 candle close breakout event
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

            for _ in range(3):
                executed.append({
                    "date": t_dt.strftime("%Y-%m-%d"),
                    "result": exit_reason,
                    "pnl": pnl
                })

        df_exec = pd.DataFrame(executed)
        if df_exec.empty:
            return None

        total_pos = len(df_exec)
        wins = len(df_exec[df_exec["result"] == "HIT_TP"])
        losses = len(df_exec[df_exec["result"] == "HIT_SL"])
        win_rate = (wins / total_pos) * 100.0 if total_pos > 0 else 0.0
        total_pnl = df_exec["pnl"].sum()
        gross_p = wins * (tp_usd * 10.0)
        gross_l = losses * (sl_usd * 10.0)
        pf = round(gross_p / gross_l, 2) if gross_l > 0 else 99.0

        daily_df = df_exec.groupby("date")["pnl"].sum().reset_index()
        profitable_days = len(daily_df[daily_df["pnl"] > 0])

        return {
            "total_pos": total_pos,
            "wins": wins,
            "losses": losses,
            "win_rate": win_rate,
            "profit_factor": pf,
            "net_pnl": total_pnl,
            "total_days": len(daily_df),
            "profitable_days": profitable_days,
            "avg_daily_pnl": daily_df["pnl"].mean()
        }

    res_no_trend = backtest_strat002(use_trend_filter=False)
    res_trend = backtest_strat002(use_trend_filter=True)

    print("\n[RESULTS COMPARISON]")
    print(f"1. STRAT-002 (M5 Bar-Close Trigger, No Trend Filter):")
    print(f"   - Total Burst Positions: {res_no_trend['total_pos']} ({res_no_trend['total_pos']//3} Signals)")
    print(f"   - Win Rate: {res_no_trend['win_rate']:.1f}% | Profit Factor: {res_no_trend['profit_factor']}")
    print(f"   - Net PnL: ${res_no_trend['net_pnl']:+.2f} (${res_no_trend['avg_daily_pnl']:+.2f}/day)")
    print(f"   - Profitable Trading Days: {res_no_trend['profitable_days']}/{res_no_trend['total_days']} ({res_no_trend['profitable_days']/res_no_trend['total_days']*100.0:.1f}%)\n")

    print(f"2. STRAT-002 + H1 Trend Filter (EMA 50/200 Alignment):")
    print(f"   - Total Burst Positions: {res_trend['total_pos']} ({res_trend['total_pos']//3} Signals)")
    print(f"   - Win Rate: {res_trend['win_rate']:.1f}% | Profit Factor: {res_trend['profit_factor']}")
    print(f"   - Net PnL: ${res_trend['net_pnl']:+.2f} (${res_trend['avg_daily_pnl']:+.2f}/day)")
    print(f"   - Profitable Trading Days: {res_trend['profitable_days']}/{res_trend['total_days']} ({res_trend['profitable_days']/res_trend['total_days']*100.0:.1f}%)")
    print("==========================================================================================")

if __name__ == "__main__":
    run_simulation()
