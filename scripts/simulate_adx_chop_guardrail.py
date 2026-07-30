#!/usr/bin/env python3
"""
simulate_adx_chop_guardrail.py - ADX Trend-Strength & Chop Guardrail Simulation

Calculates M15 ADX (14-period) and replays trades across July 29 & July 30, 2026:
- ADX >= 20: Permitted (Active Trending Market)
- ADX < 20: Blocked (Sideways Chop / Consolidation)
"""

import sys
import os
sys.path.insert(0, os.path.abspath("."))
import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta
import MetaTrader5 as mt5

def calculate_adx(df, period=14):
    df = df.copy()
    df["high_diff"] = df["high"].diff()
    df["low_diff"] = -df["low"].diff()

    df["plus_dm"] = np.where((df["high_diff"] > df["low_diff"]) & (df["high_diff"] > 0), df["high_diff"], 0.0)
    df["minus_dm"] = np.where((df["low_diff"] > df["high_diff"]) & (df["low_diff"] > 0), df["low_diff"], 0.0)

    df["tr1"] = df["high"] - df["low"]
    df["tr2"] = (df["high"] - df["close"].shift(1)).abs()
    df["tr3"] = (df["low"] - df["close"].shift(1)).abs()
    df["tr"] = df[["tr1", "tr2", "tr3"]].max(axis=1)

    df["tr_smoothed"] = df["tr"].ewm(alpha=1/period, adjust=False).mean()
    df["plus_di"] = 100 * (df["plus_dm"].ewm(alpha=1/period, adjust=False).mean() / df["tr_smoothed"])
    df["minus_di"] = 100 * (df["minus_dm"].ewm(alpha=1/period, adjust=False).mean() / df["tr_smoothed"])

    df["dx"] = 100 * ((df["plus_di"] - df["minus_di"]).abs() / (df["plus_di"] + df["minus_di"]).replace(0, 1))
    df["adx"] = df["dx"].ewm(alpha=1/period, adjust=False).mean()
    return df

def run_adx_simulation():
    print("==========================================================================================")
    print("  SIMULATION AUDIT: ADX TREND-STRENGTH GUARDRAIL (ADX >= 20)")
    print("  Testing ADX Chop Detection on July 29 (FOMC Trend Day) and July 30 (Chop Day)")
    print("==========================================================================================")

    if not mt5.initialize():
        print("[ERROR] MetaTrader 5 terminal not connected.")
        return

    symbol = "XAUUSDz"
    from_dt = datetime.now(timezone.utc) - timedelta(days=3)
    to_dt = datetime.now(timezone.utc) + timedelta(days=1)

    # 1. Fetch M15 rates and calculate EMA 20, EMA 50, and ADX 14
    m15_rates = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_M15, from_dt, to_dt)
    df_m15 = pd.DataFrame(m15_rates)
    df_m15["time_dt"] = pd.to_datetime(df_m15["time"], unit="s", utc=True)
    df_m15["ema20"] = df_m15["close"].ewm(span=20, adjust=False).mean()
    df_m15["ema50"] = df_m15["close"].ewm(span=50, adjust=False).mean()
    df_m15 = calculate_adx(df_m15, period=14)

    def get_m15_indicators(t_dt):
        sub = df_m15[df_m15["time_dt"] <= t_dt]
        if sub.empty:
            return "FLAT", 0.0, 0.0
        last = sub.iloc[-1]
        trend = "UPTREND" if last["ema20"] > last["ema50"] else "DOWNTREND"
        adx_val = float(last["adx"])
        return trend, adx_val

    # 2. Fetch raw deals across July 29 and July 30
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=1)
    deals = mt5.history_deals_get(today_start, to_dt) or []
    bot_deals = [d._asdict() for d in deals if (d.magic == 1001 or "CAND-LIVE" in str(d.comment)) and d.entry == 0]

    # Exclude FOMC window (18:00 - 20:00 UTC)
    filtered_deals = []
    for d in bot_deals:
        t_sec = d.get("time", 0)
        t_dt = datetime.fromtimestamp(t_sec, tz=timezone.utc)
        if 18 <= t_dt.hour < 20:
            continue
        filtered_deals.append(d)

    def simulate_trade_outcomes(signal_list):
        tp50_count = 0
        sl20_count = 0
        total_pnl = 0.0

        for deal in signal_list:
            entry_p = deal.get("price", 0.0)
            entry_t_sec = deal.get("time", 0)
            direction = "BUY" if deal.get("type") == 0 else "SELL"

            init_sl = round(entry_p - 2.00, 2) if direction == "BUY" else round(entry_p + 2.00, 2)
            init_tp = round(entry_p + 5.00, 2) if direction == "BUY" else round(entry_p - 5.00, 2)

            rates = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_M1, entry_t_sec, entry_t_sec + 7200)
            if rates is None or len(rates) == 0:
                continue

            exit_reason = None
            pnl = 0.0

            for r in rates:
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
                tp50_count += 1
            elif exit_reason == "HIT_SL":
                sl20_count += 1

            total_pnl += pnl

        total_trades = len(signal_list)
        win_rate = (tp50_count / total_trades) * 100.0 if total_trades > 0 else 0.0
        gross_profit = tp50_count * 50.0
        gross_loss = sl20_count * 20.0
        pf = round(gross_profit / gross_loss, 2) if gross_loss > 0 else 99.0

        return {
            "total_trades": total_trades,
            "tp50": tp50_count,
            "sl20": sl20_count,
            "win_rate": win_rate,
            "profit_factor": pf,
            "net_pnl": total_pnl
        }

    # Filter Sets:
    # A. M15 Trend Filter
    def filter_trend(signals):
        res = []
        for s in signals:
            t_sec = s.get("time", 0)
            t_dt = datetime.fromtimestamp(t_sec, tz=timezone.utc)
            direction = "BUY" if s.get("type") == 0 else "SELL"
            trend, adx = get_m15_indicators(t_dt)
            if (direction == "BUY" and trend == "UPTREND") or (direction == "SELL" and trend == "DOWNTREND"):
                res.append(s)
        return res

    # B. ADX Filter (ADX >= 20)
    def filter_adx(signals, min_adx=20.0):
        res = []
        for s in signals:
            t_sec = s.get("time", 0)
            t_dt = datetime.fromtimestamp(t_sec, tz=timezone.utc)
            trend, adx = get_m15_indicators(t_dt)
            if adx >= min_adx:
                res.append(s)
        return res

    # C. Trend + ADX Filter + 15s Cooldown
    def filter_trend_adx_cooldown(signals, min_adx=20.0, cooldown_sec=15):
        res = []
        last_t = 0
        for s in signals:
            t_sec = s.get("time", 0)
            t_dt = datetime.fromtimestamp(t_sec, tz=timezone.utc)
            direction = "BUY" if s.get("type") == 0 else "SELL"
            trend, adx = get_m15_indicators(t_dt)

            if (t_sec - last_t) < cooldown_sec:
                continue

            if (direction == "BUY" and trend == "UPTREND") or (direction == "SELL" and trend == "DOWNTREND"):
                if adx >= min_adx:
                    last_t = t_sec
                    res.append(s)
        return res

    # Separate deals into July 29 (Yesterday) and July 30 (Today)
    july29_deals = [s for s in filtered_deals if datetime.fromtimestamp(s["time"], tz=timezone.utc).day == 29]
    july30_deals = [s for s in filtered_deals if datetime.fromtimestamp(s["time"], tz=timezone.utc).day == 30]

    def run_suite_for_deals(deal_list, label_name):
        print(f"\n==========================================================================================")
        print(f"  SIMULATION RESULTS FOR {label_name} ({len(deal_list)} RAW SIGNALS)")
        print(f"==========================================================================================")

        b = simulate_trade_outcomes(deal_list)
        t = simulate_trade_outcomes(filter_trend(deal_list))
        a = simulate_trade_outcomes(filter_adx(deal_list, min_adx=20.0))
        tac = simulate_trade_outcomes(filter_trend_adx_cooldown(deal_list, min_adx=20.0, cooldown_sec=15))

        print(f"0. Baseline (Unfiltered):                      Trades: {b['total_trades']:3d} | TP: {b['tp50']:2d} | SL: {b['sl20']:3d} | WinRate: {b['win_rate']:.1f}% | PF: {b['profit_factor']} | Net PnL: ${b['net_pnl']:+.2f}")
        print(f"1. Option 3 Alone (M15 Trend):                  Trades: {t['total_trades']:3d} | TP: {t['tp50']:2d} | SL: {t['sl20']:3d} | WinRate: {t['win_rate']:.1f}% | PF: {t['profit_factor']} | Net PnL: ${t['net_pnl']:+.2f}")
        print(f"2. ADX Filter Alone (ADX >= 20):               Trades: {a['total_trades']:3d} | TP: {a['tp50']:2d} | SL: {a['sl20']:3d} | WinRate: {a['win_rate']:.1f}% | PF: {a['profit_factor']} | Net PnL: ${a['net_pnl']:+.2f}")
        print(f"3. Master Combo (Trend + ADX >= 20 + 15s Cool): Trades: {tac['total_trades']:3d} | TP: {tac['tp50']:2d} | SL: {tac['sl20']:3d} | WinRate: {tac['win_rate']:.1f}% | PF: {tac['profit_factor']} | Net PnL: ${tac['net_pnl']:+.2f}")

    run_suite_for_deals(july29_deals, "JULY 29 (TREND DAY)")
    run_suite_for_deals(july30_deals, "JULY 30 (CHOP DAY)")
    run_suite_for_deals(filtered_deals, "2-DAY COMBINED TOTAL (JULY 29 & JULY 30)")

if __name__ == "__main__":
    run_adx_simulation()
