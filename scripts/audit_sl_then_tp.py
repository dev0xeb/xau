#!/usr/bin/env python3
"""
audit_sl_then_tp.py - High-Precision Diagnostic Audit: Trades Hitting SL and THEN Hitting TP

Replays Option 3 (M15 Trend Alignment, 0.50 Conviction, excluding FOMC 18:00-20:00 UTC):
- Initial SL = -$2.00 ($20 risk), Initial TP = +$5.00 ($50 target)
- Audits every trade that hit SL (-$2.00):
  Tracks whether price subsequently reversed and reached the original TP price (+ $5.00) post-SL exit!
"""

import sys
import os
sys.path.insert(0, os.path.abspath("."))
import pandas as pd
from datetime import datetime, timezone, timedelta
import MetaTrader5 as mt5

def audit_sl_then_tp():
    print("==========================================================================================")
    print("  HIGH-PRECISION AUDIT: TRADES HITTING INITIAL SL (-$2.00) AND THEN HITTING TP (+$5.00)")
    print("  Dataset: Option 3 (M15 Trend-Aligned Signals, 0.50 Conviction, Excluding FOMC)")
    print("==========================================================================================")

    if not mt5.initialize():
        print("[ERROR] MetaTrader 5 terminal not connected.")
        return

    symbol = "XAUUSDz"
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

    # 1. Fetch M15 Trend (EMA 20 vs EMA 50)
    m15_rates = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_M15, today_start - timedelta(days=2), today_start + timedelta(days=1))
    df_m15 = pd.DataFrame(m15_rates)
    df_m15["time_dt"] = pd.to_datetime(df_m15["time"], unit="s", utc=True)
    df_m15["ema20"] = df_m15["close"].ewm(span=20, adjust=False).mean()
    df_m15["ema50"] = df_m15["close"].ewm(span=50, adjust=False).mean()

    def get_m15_trend(t_dt):
        sub = df_m15[df_m15["time_dt"] <= t_dt]
        if sub.empty:
            return "FLAT"
        last = sub.iloc[-1]
        return "UPTREND" if last["ema20"] > last["ema50"] else "DOWNTREND"

    # 2. Fetch raw deals outside FOMC
    deals = mt5.history_deals_get(today_start, datetime.now(timezone.utc) + timedelta(days=1)) or []
    bot_deals = [d._asdict() for d in deals if (d.magic == 1001 or "CAND-LIVE" in str(d.comment)) and d.entry == 0]

    filtered_deals = []
    for d in bot_deals:
        t_sec = d.get("time", 0)
        t_dt = datetime.fromtimestamp(t_sec, tz=timezone.utc)
        if 18 <= t_dt.hour < 20:
            continue
        trend = get_m15_trend(t_dt)
        direction = "BUY" if d.get("type") == 0 else "SELL"
        if (direction == "BUY" and trend == "UPTREND") or (direction == "SELL" and trend == "DOWNTREND"):
            filtered_deals.append(d)

    print(f"[DATA] Replaying {len(filtered_deals)} M15 trend-aligned trade signals...\n")

    if not filtered_deals:
        print("[INFO] No signals found.")
        return

    tp_direct_count = 0
    sl_count = 0
    sl_then_tp_count = 0
    sl_never_tp_count = 0

    sl_then_tp_details = []

    for deal in sorted(filtered_deals, key=lambda x: x["time"]):
        pos_id = deal.get("position_id", deal.get("order"))
        entry_p = deal.get("price", 0.0)
        entry_t_sec = deal.get("time", 0)
        direction = "BUY" if deal.get("type") == 0 else "SELL"

        init_sl = round(entry_p - 2.00, 2) if direction == "BUY" else round(entry_p + 2.00, 2)
        init_tp = round(entry_p + 5.00, 2) if direction == "BUY" else round(entry_p - 5.00, 2)

        # Copy 3 hours of M1 rates post-entry to track trajectory after SL hit
        rates = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_M1, entry_t_sec, entry_t_sec + 10800)
        if rates is None or len(rates) == 0:
            continue

        hit_sl = False
        sl_t_sec = None
        hit_tp_direct = False

        for r in rates:
            high = r["high"]
            low = r["low"]

            if direction == "BUY":
                if low <= init_sl:
                    hit_sl = True
                    sl_t_sec = r["time"]
                    break
                if high >= init_tp:
                    hit_tp_direct = True
                    break
            elif direction == "SELL":
                if high >= init_sl:
                    hit_sl = True
                    sl_t_sec = r["time"]
                    break
                if low <= init_tp:
                    hit_tp_direct = True
                    break

        if hit_tp_direct:
            tp_direct_count += 1

        elif hit_sl:
            sl_count += 1
            # Track price trajectory AFTER sl_t_sec up to 3 hours post-entry
            post_rates = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_M1, sl_t_sec, entry_t_sec + 10800)
            hit_tp_after_sl = False
            time_to_tp_min = 0

            if post_rates is not None and len(post_rates) > 0:
                for pr in post_rates:
                    p_high = pr["high"]
                    p_low = pr["low"]
                    if direction == "BUY" and p_high >= init_tp:
                        hit_tp_after_sl = True
                        time_to_tp_min = round((pr["time"] - sl_t_sec) / 60.0, 1)
                        break
                    elif direction == "SELL" and p_low <= init_tp:
                        hit_tp_after_sl = True
                        time_to_tp_min = round((pr["time"] - sl_t_sec) / 60.0, 1)
                        break

            if hit_tp_after_sl:
                sl_then_tp_count += 1
                sl_then_tp_details.append({
                    "ticket": pos_id,
                    "direction": direction,
                    "entry_p": entry_p,
                    "sl_p": init_sl,
                    "tp_p": init_tp,
                    "time_to_tp_min": time_to_tp_min
                })
            else:
                sl_never_tp_count += 1

    total_signals = len(filtered_deals)

    print("==========================================================================================")
    print("  EXACT SL-THEN-TP TRAJECTORY AUDIT RESULTS SUMMARY")
    print("==========================================================================================")
    print(f"Total Trend-Aligned Signals Replayed: {total_signals}")
    print(f"  1. Direct Take Profit Hits (+$50.00): {tp_direct_count} ({tp_direct_count/total_signals*100.0:.1f}%)")
    print(f"  2. Total Stop Loss Hits (-$20.00): {sl_count} ({sl_count/total_signals*100.0:.1f}%)\n")

    print("--- BREAKDOWN OF THE LOSING TRADES (STOP LOSS HITS) ---")
    print(f"  - Hit SL and THEN went on to hit original TP (+$50.00): {sl_then_tp_count} trades ({sl_then_tp_count/sl_count*100.0:.1f}% of losses)")
    print(f"  - Hit SL and NEVER hit original TP: {sl_never_tp_count} trades ({sl_never_tp_count/sl_count*100.0:.1f}% of losses)")
    print("==========================================================================================")

    if sl_then_tp_details:
        avg_time = sum(d["time_to_tp_min"] for d in sl_then_tp_details) / len(sl_then_tp_details)
        print(f"\nFor the {sl_then_tp_count} trades that hit SL then reached TP:")
        print(f"  - Average time from SL exit to reaching TP target: {avg_time:.1f} minutes")

if __name__ == "__main__":
    audit_sl_then_tp()
