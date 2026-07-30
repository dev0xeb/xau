#!/usr/bin/env python3
"""
audit_today_with_trend_fix.py - Mathematical Audit of Today's Trades WITH Fixed M15 Trend Filter & 15s Cooldown

Replays today's 321 live trades under two conditions:
1. Exact actual live execution (with bug: -$1,227.47)
2. Counterfactual execution with M15 Trend Filter FIXED and 15-second Entry Cooldown ACTIVE.
"""

import sys
import os
sys.path.insert(0, os.path.abspath("."))
import pandas as pd
from datetime import datetime, timezone, timedelta
import MetaTrader5 as mt5

def audit_today_fixed():
    print("==========================================================================================")
    print("  COUNTERFACTUAL AUDIT: TODAY'S TRADES (JULY 30) WITH FIXED TREND FILTER & 15s COOLDOWN")
    print("==========================================================================================")

    if not mt5.initialize():
        print("[ERROR] MetaTrader 5 terminal not connected.")
        return

    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    deals = mt5.history_deals_get(today_start, datetime.now(timezone.utc) + timedelta(days=1)) or []

    bot_deals = [d for d in deals if (d.magic == 1001 or "CAND-LIVE" in str(d.comment)) and d.entry == 0]

    if not bot_deals:
        print("[INFO] No entry deals found for today in MT5 history.")
        return

    symbol = "XAUUSDz"

    # Fetch M15 rates for today
    m15_rates = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_M15, today_start - timedelta(days=2), datetime.now(timezone.utc))
    df_m15 = pd.DataFrame(m15_rates)
    df_m15["time_dt"] = pd.to_datetime(df_m15["time"], unit="s", utc=True)
    df_m15["ema20"] = df_m15["close"].ewm(span=20, adjust=False).mean()
    df_m15["ema50"] = df_m15["close"].ewm(span=50, adjust=False).mean()

    def get_m15_trend_at(t_dt):
        sub = df_m15[df_m15["time_dt"] <= t_dt]
        if sub.empty:
            return "FLAT"
        last = sub.iloc[-1]
        return "UPTREND" if last["ema20"] > last["ema50"] else "DOWNTREND"

    # 1. Evaluate Actual Live Deals
    actual_pnl = 0.0
    actual_tp = 0
    actual_sl = 0

    for deal in bot_deals:
        pos_id = deal.position_id
        pos_deals = [d for d in deals if d.position_id == pos_id and d.entry == 1]
        if pos_deals:
            pnl = pos_deals[0].profit
            actual_pnl += pnl
            if pnl > 0:
                actual_tp += 1
            else:
                actual_sl += 1

    # 2. Evaluate Counterfactual: ONLY Trend-Aligned Trades AND 15s Cooldown
    filtered_pnl = 0.0
    filtered_tp = 0
    filtered_sl = 0
    last_exec_time = 0

    filtered_trades = []

    for deal in sorted(bot_deals, key=lambda x: x.time):
        t_sec = deal.time
        t_dt = datetime.fromtimestamp(t_sec, tz=timezone.utc)
        direction = "BUY" if deal.type == 0 else "SELL"
        trend = get_m15_trend_at(t_dt)

        # M15 Trend Filter Check
        is_aligned = (direction == "BUY" and trend == "UPTREND") or (direction == "SELL" and trend == "DOWNTREND")
        if not is_aligned:
            continue  # REJECT COUNTER-TREND TRADE

        # 15s Cooldown Check
        if (t_sec - last_exec_time) < 15:
            continue  # REJECT DUPLICATE CLUSTER ENTRY

        last_exec_time = t_sec

        pos_id = deal.position_id
        pos_deals = [d for d in deals if d.position_id == pos_id and d.entry == 1]
        if pos_deals:
            pnl = pos_deals[0].profit
            filtered_pnl += pnl
            if pnl > 0:
                filtered_tp += 1
            else:
                filtered_sl += 1
            filtered_trades.append({
                "time": t_dt.strftime("%H:%M:%S"),
                "dir": direction,
                "pnl": pnl
            })

    print("==========================================================================================")
    print("  COMPARISON RESULTS FOR TODAY'S TRADES (JULY 30, 2026)")
    print("==========================================================================================")
    print(f"1. ACTUAL LIVE EXECUTION (WITH SYMBOL BUG & 0s COOLDOWN):")
    print(f"   Total Trades: {len(bot_deals)} | TP Hits: {actual_tp} | SL Hits: {actual_sl} | Net PnL: ${actual_pnl:+.2f}\n")

    print(f"2. COUNTERFACTUAL EXECUTION (WITH FIXED M15 TREND FILTER & 15s COOLDOWN):")
    print(f"   Total Trades: {len(filtered_trades)} | TP Hits: {filtered_tp} | SL Hits: {filtered_sl} | Net PnL: ${filtered_pnl:+.2f}")
    print("==========================================================================================")

if __name__ == "__main__":
    audit_today_fixed()
