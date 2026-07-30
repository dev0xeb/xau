#!/usr/bin/env python3
"""
test_sustainability_break_even.py - Break-Even Profit Lock Guardrail Simulation

Tests adding a Break-Even Guardrail to Model 1 (Instant 3-Burst Strategy):
- Target 1: TP at +$2.25 ($22.50)
- Target 2: Initial SL at -$1.50 (-$15.00)
- Guardrail: When price reaches +$1.50 in profit (MFE >= $1.50), automatically move SL to Entry + $0.20 ($2.00 profit lock).

Replays 1 Year of XAUUSD Data (353,464 M1 Candles / 312 Days).
"""

import sys
import os
sys.path.insert(0, os.path.abspath("."))
import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta
import MetaTrader5 as mt5

def run_be_simulation():
    print("==========================================================================================")
    print("  SUSTAINABILITY RESEARCH: BREAK-EVEN PROFIT LOCK GUARDRAIL TEST (1 YEAR)")
    print("==========================================================================================")

    if not mt5.initialize():
        print("[ERROR] MetaTrader 5 terminal not connected.")
        return

    symbol = "XAUUSDz"
    end_dt = datetime.now(timezone.utc)
    start_dt = end_dt - timedelta(days=365)

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

    df_m1 = pd.merge_asof(df_m1.sort_values("time_dt"), df_m5[["time_dt", "fvg_type"]].sort_values("time_dt"), on="time_dt", direction="backward")

    m1_arr = df_m1[["time", "open", "high", "low", "close"]].values
    time_map = {int(row[0]): idx for idx, row in enumerate(m1_arr)}

    raw_signals = df_m1[df_m1["fvg_type"] != "NONE"].to_dict("records")

    def simulate_with_be_trigger(be_trigger_dist=1.50, be_lock_dist=0.20):
        executed = []
        last_t = 0
        cooldown_sec = 300

        for sig in raw_signals:
            t_sec = int(sig["time"])
            t_dt = sig["time_dt"]
            direction = sig["fvg_type"]

            if 18 <= t_dt.hour < 20:
                continue
            if (t_sec - last_t) < cooldown_sec:
                continue

            last_t = t_sec

            entry_p = sig["close"]
            init_sl = round(entry_p - 1.50, 2) if direction == "BUY" else round(entry_p + 1.50, 2)
            init_tp = round(entry_p + 2.25, 2) if direction == "BUY" else round(entry_p - 2.25, 2)

            start_idx = time_map.get(t_sec)
            if start_idx is None:
                continue

            curr_sl = init_sl
            exit_reason = None
            pnl = 0.0
            is_be_activated = False

            end_idx = min(start_idx + 120, len(m1_arr))
            for i in range(start_idx + 1, end_idx):
                high = m1_arr[i][2]
                low = m1_arr[i][3]

                if direction == "BUY":
                    # Check BE Trigger (+ $1.50 MFE -> move SL to entry + $0.20)
                    if (high - entry_p) >= be_trigger_dist and not is_be_activated:
                        curr_sl = round(entry_p + be_lock_dist, 2)
                        is_be_activated = True

                    if low <= curr_sl:
                        if is_be_activated:
                            exit_reason = "HIT_BE_PROFIT"
                            pnl = be_lock_dist * 10.0
                        else:
                            exit_reason = "HIT_SL"
                            pnl = -15.0
                        break
                    if high >= init_tp:
                        exit_reason = "HIT_TP"
                        pnl = 22.50
                        break
                elif direction == "SELL":
                    if (entry_p - low) >= be_trigger_dist and not is_be_activated:
                        curr_sl = round(entry_p - be_lock_dist, 2)
                        is_be_activated = True

                    if high >= curr_sl:
                        if is_be_activated:
                            exit_reason = "HIT_BE_PROFIT"
                            pnl = be_lock_dist * 10.0
                        else:
                            exit_reason = "HIT_SL"
                            pnl = -15.0
                        break
                    if low <= init_tp:
                        exit_reason = "HIT_TP"
                        pnl = 22.50
                        break

            for _ in range(3):
                executed.append({
                    "date": t_dt.strftime("%Y-%m-%d"),
                    "result": exit_reason,
                    "pnl": pnl
                })

        df_e = pd.DataFrame(executed)
        tp_wins = len(df_e[df_e["result"] == "HIT_TP"])
        be_saves = len(df_e[df_e["result"] == "HIT_BE_PROFIT"])
        losses = len(df_e[df_e["result"] == "HIT_SL"])
        total_p = len(df_e)

        pure_wr = (tp_wins / total_p) * 100.0
        combined_win_rate = ((tp_wins + be_saves) / total_p) * 100.0
        total_pnl = df_e["pnl"].sum()
        gross_p = df_e[df_e["pnl"] > 0]["pnl"].sum()
        gross_l = abs(df_e[df_e["pnl"] < 0]["pnl"].sum())
        pf = round(gross_p / gross_l, 2) if gross_l > 0 else 99.0

        daily_df = df_e.groupby("date")["pnl"].sum().reset_index()
        profitable_days = len(daily_df[daily_df["pnl"] > 0])

        return {
            "total_p": total_p,
            "tp_wins": tp_wins,
            "be_saves": be_saves,
            "losses": losses,
            "pure_wr": pure_wr,
            "combined_win_rate": combined_win_rate,
            "net_pnl": total_pnl,
            "pf": pf,
            "profitable_days": profitable_days,
            "total_days": len(daily_df),
            "daily_pnl": daily_df["pnl"].mean()
        }

    # Baseline Model 1 (No BE Guardrail)
    res_base = simulate_with_be_trigger(be_trigger_dist=99.0, be_lock_dist=0.0)

    # Model 1 + BE Trigger at +$1.50 MFE (Locks +$0.20 / $2.00 profit)
    res_be_150 = simulate_with_be_trigger(be_trigger_dist=1.50, be_lock_dist=0.20)

    # Model 1 + BE Trigger at +$1.20 MFE (Locks +$0.10 / $1.00 profit)
    res_be_120 = simulate_with_be_trigger(be_trigger_dist=1.20, be_lock_dist=0.10)

    print("==========================================================================================")
    print("  SUSTAINABILITY COMPARISON: BASELINE MODEL 1 VS BREAK-EVEN PROFIT GUARDRAILS")
    print("==========================================================================================")
    print("1. BASELINE MODEL 1 (Clean Exits | No BE Guardrail):")
    print("   - Total Positions:", res_base['total_p'], "| TP Wins:", res_base['tp_wins'], "| Losses:", res_base['losses'])
    print(f"   - PURE WIN RATE: {res_base['pure_wr']:.1f}% | Profit Factor: {res_base['pf']} | Net PnL: ${res_base['net_pnl']:+.2f}")
    print(f"   - Profitable Days: {res_base['profitable_days']}/{res_base['total_days']} ({res_base['profitable_days']/res_base['total_days']*100.0:.1f}%) | Avg Daily PnL: ${res_base['daily_pnl']:+.2f}/day\n")

    print("2. MODEL 1 + BE GUARDRAIL (Trigger at +$1.50 MFE -> Move SL to Entry+$0.20):")
    print("   - Total Positions:", res_be_150['total_p'], "| TP Wins:", res_be_150['tp_wins'], "| BE Saved:", res_be_150['be_saves'], "| Full Losses:", res_be_150['losses'])
    print(f"   - PURE WIN RATE: {res_be_150['pure_wr']:.1f}% | COMBINED WIN+BE RATE: {res_be_150['combined_win_rate']:.1f}%")
    print(f"   - Profit Factor: {res_be_150['pf']} | Net PnL: ${res_be_150['net_pnl']:+.2f}")
    print(f"   - Profitable Days: {res_be_150['profitable_days']}/{res_be_150['total_days']} ({res_be_150['profitable_days']/res_be_150['total_days']*100.0:.1f}%) | Avg Daily PnL: ${res_be_150['daily_pnl']:+.2f}/day\n")

    print("3. MODEL 1 + EARLY BE GUARDRAIL (Trigger at +$1.20 MFE -> Move SL to Entry+$0.10):")
    print("   - Total Positions:", res_be_120['total_p'], "| TP Wins:", res_be_120['tp_wins'], "| BE Saved:", res_be_120['be_saves'], "| Full Losses:", res_be_120['losses'])
    print(f"   - PURE WIN RATE: {res_be_120['pure_wr']:.1f}% | COMBINED WIN+BE RATE: {res_be_120['combined_win_rate']:.1f}%")
    print(f"   - Profit Factor: {res_be_120['pf']} | Net PnL: ${res_be_120['net_pnl']:+.2f}")
    print(f"   - Profitable Days: {res_be_120['profitable_days']}/{res_be_120['total_days']} ({res_be_120['profitable_days']/res_be_120['total_days']*100.0:.1f}%) | Avg Daily PnL: ${res_be_120['daily_pnl']:+.2f}/day")
    print("==========================================================================================")

if __name__ == "__main__":
    run_be_simulation()
