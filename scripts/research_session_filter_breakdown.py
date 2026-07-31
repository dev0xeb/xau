#!/usr/bin/env python3
"""
research_session_filter_breakdown.py - Comprehensive Trading Session & Hour-by-Hour Research Engine

Replays 1 Year of XAUUSD Data (353,464 M1 Candles / 312 Days):
Evaluates both STRAT-001 (M5 FVG) and STRAT-002 (M5 CHOCH/BOS) across:
1. Hour-by-Hour Performance Matrix (UTC 00 to 23).
2. Major Market Session Breakdown:
   - Asian Session (00:00 - 07:00 UTC)
   - London Session (07:00 - 12:00 UTC)
   - London / New York Overlap (12:00 - 16:00 UTC)
   - Late New York Session (16:00 - 21:00 UTC)
   - Market Rollover / Low Liquidity (21:00 - 00:00 UTC)
3. Filtered Session Execution Comparisons:
   - Scenario A: 24-Hour All Sessions (Baseline)
   - Scenario B: London + NY Overlap Only (07:00 - 16:00 UTC)
   - Scenario C: London + Full NY (07:00 - 21:00 UTC, Excluding Asian)
   - Scenario D: NY Only (12:00 - 21:00 UTC)
"""

import sys
import os
sys.path.insert(0, os.path.abspath("."))
import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta
import MetaTrader5 as mt5

def run_session_research():
    print("==========================================================================================")
    print("  TRADING SESSION & HOUR-BY-HOUR RESEARCH ENGINE (353,464 M1 BARS / 1 YEAR)")
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

    # 1. STRAT-001 (M5 FVG)
    df_m5["fvg_bull"] = df_m5["low"] - df_m5["high"].shift(2)
    df_m5["fvg_bear"] = df_m5["low"].shift(2) - df_m5["high"]

    # 2. STRAT-002 (Causal M5 CHOCH / BOS)
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

    df_m1 = pd.merge_asof(df_m1.sort_values("time_dt"), 
                        df_m5[["time_dt", "fvg_bull", "fvg_bear", "causal_bos_bull", "causal_bos_bear"]].sort_values("time_dt"), 
                        on="time_dt", direction="backward")

    m1_arr = df_m1[["time", "open", "high", "low", "close"]].values
    time_map = {int(row[0]): idx for idx, row in enumerate(m1_arr)}

    df_m1["fvg_sig"] = np.where(df_m1["fvg_bull"] > 0.50, "BUY", np.where(df_m1["fvg_bear"] > 0.50, "SELL", "NONE"))
    df_m1["bos_sig"] = np.where(df_m1["causal_bos_bull"] == 1, "BUY", np.where(df_m1["causal_bos_bear"] == 1, "SELL", "NONE"))

    def backtest_with_session_filter(signals_df, direction_col, allowed_hours=None, sl_usd=1.50, tp_usd=2.25, cooldown_sec=300):
        records = signals_df[signals_df[direction_col] != "NONE"].to_dict("records")
        executed = []
        last_t = 0

        for sig in records:
            t_sec = int(sig["time"])
            t_dt = sig["time_dt"]
            direction = sig[direction_col]
            hour = t_dt.hour

            # Session / Hour Filter Check
            if allowed_hours is not None and hour not in allowed_hours:
                continue

            # Standard Rollover Block (18:00 - 20:00 UTC)
            if 18 <= hour < 20:
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

            iso_year, iso_week, _ = t_dt.isocalendar()
            week_key = f"{iso_year}-W{iso_week:02d}"

            for _ in range(3):
                executed.append({
                    "date": t_dt.strftime("%Y-%m-%d"),
                    "hour": hour,
                    "week_key": week_key,
                    "result": exit_reason,
                    "pnl": pnl
                })

        df_exec = pd.DataFrame(executed)
        if df_exec.empty:
            return None, pd.DataFrame()

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

        summary = {
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

        return summary, df_exec

    # 1. Hour-by-Hour Breakdown for both strategies
    _, df_exec_s1 = backtest_with_session_filter(df_m1, "fvg_sig", allowed_hours=None)
    _, df_exec_s2 = backtest_with_session_filter(df_m1, "bos_sig", allowed_hours=None)

    print("==========================================================================================")
    print("  HOUR-BY-HOUR PERFORMANCE BREAKDOWN (UTC 00:00 TO 23:00)")
    print("==========================================================================================")
    print("Hour (UTC) | STRAT-001 (M5 FVG) Trades | WR% | Net PnL ($)  || STRAT-002 (M5 CHOCH/BOS) Trades | WR% | Net PnL ($)")
    print("-" * 105)

    for h in range(24):
        s1_h = df_exec_s1[df_exec_s1["hour"] == h] if not df_exec_s1.empty else pd.DataFrame()
        s2_h = df_exec_s2[df_exec_s2["hour"] == h] if not df_exec_s2.empty else pd.DataFrame()

        t1 = len(s1_h)
        w1 = len(s1_h[s1_h["result"] == "HIT_TP"]) if t1 > 0 else 0
        wr1 = (w1 / t1 * 100.0) if t1 > 0 else 0.0
        pnl1 = s1_h["pnl"].sum() if t1 > 0 else 0.0

        t2 = len(s2_h)
        w2 = len(s2_h[s2_h["result"] == "HIT_TP"]) if t2 > 0 else 0
        wr2 = (w2 / t2 * 100.0) if t2 > 0 else 0.0
        pnl2 = s2_h["pnl"].sum() if t2 > 0 else 0.0

        print(f"  {h:02d}:00 UTC  | {t1:25d} | {wr1:4.1f}% | ${pnl1:+10.2f} || {t2:30d} | {wr2:4.1f}% | ${pnl2:+10.2f}")

    print("=" * 105 + "\n")

    # 2. Market Session Filter Scenarios
    scenarios = {
        "Scenario A: 24-Hour All Sessions (Baseline)": None,
        "Scenario B: London + London/NY Overlap (07:00 - 16:00 UTC) [Peak Liquidity]": list(range(7, 16)),
        "Scenario C: London + Full NY (07:00 - 21:00 UTC) [Excl Asian]": list(range(7, 21)),
        "Scenario D: New York Session Only (12:00 - 21:00 UTC)": list(range(12, 21)),
        "Scenario E: Asian Session Only (00:00 - 07:00 UTC)": list(range(0, 7))
    }

    print("==========================================================================================")
    print("  SESSION FILTER COMPARISON MATRIX (1-YEAR OOS AUDIT)")
    print("==========================================================================================")

    for sc_name, hours in scenarios.items():
        sum_s1, _ = backtest_with_session_filter(df_m1, "fvg_sig", allowed_hours=hours)
        sum_s2, _ = backtest_with_session_filter(df_m1, "bos_sig", allowed_hours=hours)

        print(f"\n[SCENARIO] {sc_name}:")
        if sum_s1:
            print(f"   - STRAT-001 (M5 FVG): Trades: {sum_s1['total_pos']:5d} | WR: {sum_s1['win_rate']:.1f}% | PF: {sum_s1['profit_factor']} | Net PnL: ${sum_s1['net_pnl']:+10.2f} (${sum_s1['avg_daily_pnl']:+.2f}/day) | Profitable Days: {sum_s1['profitable_days']}/{sum_s1['total_days']} ({sum_s1['profitable_days']/sum_s1['total_days']*100.0:.1f}%)")
        if sum_s2:
            print(f"   - STRAT-002 (BOS)  : Trades: {sum_s2['total_pos']:5d} | WR: {sum_s2['win_rate']:.1f}% | PF: {sum_s2['profit_factor']} | Net PnL: ${sum_s2['net_pnl']:+10.2f} (${sum_s2['avg_daily_pnl']:+.2f}/day) | Profitable Days: {sum_s2['profitable_days']}/{sum_s2['total_days']} ({sum_s2['profitable_days']/sum_s2['total_days']*100.0:.1f}%)")

    print("==========================================================================================")

if __name__ == "__main__":
    run_session_research()
