#!/usr/bin/env python3
"""
investigate_sl_hits.py - Deep Diagnostic Investigation into Why Trades Hit SL

Analyzes the 66 losing trades in the M15 Trend-Aligned dataset:
1. Maximum Favorable Excursion (MFE): How far in profit did they go before reversing?
2. Entry Overextension: Distance between entry price and M15 EMA20 at entry time.
3. Holding Duration: How fast do losing trades hit SL vs winning trades hitting TP?
"""

import sys
import os
sys.path.insert(0, os.path.abspath("."))
import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta
import MetaTrader5 as mt5

def investigate_sl_hits():
    print("==========================================================================================")
    print("  DEEP DIAGNOSTIC INVESTIGATION: WHY DO TRADES HIT STOP LOSS?")
    print("  Auditing 107 Trend-Aligned Trades (38 TP Hits, 66 SL Hits)")
    print("==========================================================================================")

    if not mt5.initialize():
        print("[ERROR] MetaTrader 5 terminal not connected.")
        return

    symbol = "XAUUSDz"
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

    # 1. Fetch M15 EMA
    m15_rates = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_M15, today_start - timedelta(days=2), today_start + timedelta(days=1))
    df_m15 = pd.DataFrame(m15_rates)
    df_m15["time_dt"] = pd.to_datetime(df_m15["time"], unit="s", utc=True)
    df_m15["ema20"] = df_m15["close"].ewm(span=20, adjust=False).mean()
    df_m15["ema50"] = df_m15["close"].ewm(span=50, adjust=False).mean()

    def get_m15_data(t_dt):
        sub = df_m15[df_m15["time_dt"] <= t_dt]
        if sub.empty:
            return "FLAT", 0.0
        last = sub.iloc[-1]
        trend = "UPTREND" if last["ema20"] > last["ema50"] else "DOWNTREND"
        return trend, last["ema20"]

    # 2. Fetch raw deals outside FOMC
    deals = mt5.history_deals_get(today_start, datetime.now(timezone.utc) + timedelta(days=1)) or []
    bot_deals = [d._asdict() for d in deals if (d.magic == 1001 or "CAND-LIVE" in str(d.comment)) and d.entry == 0]

    filtered_deals = []
    for d in bot_deals:
        t_sec = d.get("time", 0)
        t_dt = datetime.fromtimestamp(t_sec, tz=timezone.utc)
        if 18 <= t_dt.hour < 20:
            continue
        trend, ema20 = get_m15_data(t_dt)
        direction = "BUY" if d.get("type") == 0 else "SELL"
        if (direction == "BUY" and trend == "UPTREND") or (direction == "SELL" and trend == "DOWNTREND"):
            d["m15_ema20"] = ema20
            filtered_deals.append(d)

    print(f"[DATA] Retrived {len(filtered_deals)} trend-aligned trade records for analysis.\n")

    sl_trades = []
    tp_trades = []

    for deal in filtered_deals:
        entry_p = deal.get("price", 0.0)
        entry_t_sec = deal.get("time", 0)
        direction = "BUY" if deal.get("type") == 0 else "SELL"
        ema20 = deal.get("m15_ema20", entry_p)

        init_sl = round(entry_p - 2.00, 2) if direction == "BUY" else round(entry_p + 2.00, 2)
        init_tp = round(entry_p + 5.00, 2) if direction == "BUY" else round(entry_p - 5.00, 2)

        rates = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_M1, entry_t_sec, entry_t_sec + 7200)

        if rates is None or len(rates) == 0:
            continue

        mfe_pts = 0.0
        exit_reason = None
        duration_sec = 0

        if direction == "BUY":
            overextension = round(entry_p - ema20, 2)
        else:
            overextension = round(ema20 - entry_p, 2)

        for r in rates:
            high = r["high"]
            low = r["low"]

            if direction == "BUY":
                mfe_pts = max(mfe_pts, round(high - entry_p, 2))
                if low <= init_sl:
                    exit_reason = "HIT_SL"
                    duration_sec = r["time"] - entry_t_sec
                    break
                if high >= init_tp:
                    exit_reason = "HIT_TP"
                    duration_sec = r["time"] - entry_t_sec
                    break
            elif direction == "SELL":
                mfe_pts = max(mfe_pts, round(entry_p - low, 2))
                if high >= init_sl:
                    exit_reason = "HIT_SL"
                    duration_sec = r["time"] - entry_t_sec
                    break
                if low <= init_tp:
                    exit_reason = "HIT_TP"
                    duration_sec = r["time"] - entry_t_sec
                    break

        record = {
            "ticket": deal.get("position_id", deal.get("order")),
            "direction": direction,
            "entry_p": entry_p,
            "mfe_pts": mfe_pts,
            "overextension": overextension,
            "duration_min": duration_sec / 60.0
        }

        if exit_reason == "HIT_SL":
            sl_trades.append(record)
        elif exit_reason == "HIT_TP":
            tp_trades.append(record)

    df_sl = pd.DataFrame(sl_trades)
    df_tp = pd.DataFrame(tp_trades)

    print("==========================================================================================")
    print("  DIAGNOSTIC FINDING 1: MAXIMUM FAVORABLE EXCURSION (MFE) OF LOSING TRADES")
    print("==========================================================================================")
    print(f"Total Losing Trades Analyzed: {len(df_sl)}")
    mfe_lt_05 = len(df_sl[df_sl["mfe_pts"] < 0.50])
    mfe_05_10 = len(df_sl[(df_sl["mfe_pts"] >= 0.50) & (df_sl["mfe_pts"] < 1.00)])
    mfe_10_20 = len(df_sl[(df_sl["mfe_pts"] >= 1.00) & (df_sl["mfe_pts"] < 2.00)])
    mfe_20_30 = len(df_sl[(df_sl["mfe_pts"] >= 2.00) & (df_sl["mfe_pts"] < 3.00)])
    mfe_gt_30 = len(df_sl[df_sl["mfe_pts"] >= 3.00])

    print(f"  - Instant Reversal (MFE < $0.50): {mfe_lt_05} trades ({mfe_lt_05/len(df_sl)*100.0:.1f}%) -> True False Breakouts")
    print(f"  - Small Profit Move ($0.50 <= MFE < $1.00): {mfe_05_10} trades ({mfe_05_10/len(df_sl)*100.0:.1f}%)")
    print(f"  - $10 Profit Move ($1.00 <= MFE < $2.00): {mfe_10_20} trades ({mfe_10_20/len(df_sl)*100.0:.1f}%)")
    print(f"  - $20 Profit Move ($2.00 <= MFE < $3.00): {mfe_20_30} trades ({mfe_20_30/len(df_sl)*100.0:.1f}%) -> Reached $20 profit!")
    print(f"  - Deep Target Expansion ($3.00 <= MFE < $4.99): {mfe_gt_30} trades ({mfe_gt_30/len(df_sl)*100.0:.1f}%) -> Reached $30+ profit!")

    print("\n==========================================================================================")
    print("  DIAGNOSTIC FINDING 2: OVEREXTENSION FROM M15 EMA 20 AT ENTRY")
    print("==========================================================================================")
    avg_over_sl = df_sl["overextension"].mean()
    avg_over_tp = df_tp["overextension"].mean()
    print(f"  - Average Price Overextension for LOSING Trades: ${avg_over_sl:.2f} above/below M15 EMA20")
    print(f"  - Average Price Overextension for WINNING Trades: ${avg_over_tp:.2f} above/below M15 EMA20")

    print("\n==========================================================================================")
    print("  DIAGNOSTIC FINDING 3: HOLDING DURATION COMPARISON")
    print("==========================================================================================")
    print(f"  - Average Duration to Hit Stop Loss: {df_sl['duration_min'].mean():.1f} minutes")
    print(f"  - Average Duration to Hit Take Profit: {df_tp['duration_min'].mean():.1f} minutes")
    print("==========================================================================================")

if __name__ == "__main__":
    investigate_sl_hits()
