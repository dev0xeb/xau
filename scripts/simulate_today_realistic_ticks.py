#!/usr/bin/env python3
"""
simulate_today_realistic_ticks.py - Ultra-Realistic Micro-Trajectory Simulation

Evaluates realistic order execution mechanics:
1. When price reaches entry + $2.00 (+ $20 profit), SL is set EXACTLY to entry + $2.00.
2. Micro-pullback check: Once SL is placed at entry + $2.00, any price tick/low touching <= entry + $2.00 IMMEDIATELY closes the position at + $20.00.
3. Position CANNOT reach + $50.00 TP if it gets stopped out at + $20.00 on the first micro-retracement!
"""

import sys
import os
sys.path.insert(0, os.path.abspath("."))
import pandas as pd
from datetime import datetime, timezone, timedelta
import MetaTrader5 as mt5

def run_micro_realistic_simulation():
    print("==========================================================================================")
    print("  ULTRA-REALISTIC MICRO-TRAJECTORY AUDIT: ORDER EXECUTION RE-EVALUATION")
    print("  Rule: SL placed at exact $20 profit price level (Entry + $2.00) upon reaching $20")
    print("==========================================================================================")

    if not mt5.initialize():
        print("[ERROR] MetaTrader 5 terminal not connected.")
        return

    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    deals = mt5.history_deals_get(today_start, datetime.now(timezone.utc) + timedelta(days=1)) or []

    # Extract bot entry deals
    bot_deals = [d._asdict() for d in deals if (d.magic == 1001 or "CAND-LIVE" in str(d.comment)) and d.entry == 0]

    print(f"[DATA] Replaying {len(bot_deals)} raw entry signals with strict tick/candle sequence...\n")

    if not bot_deals:
        print("[INFO] No entry signals found today.")
        return

    tp50_count = 0
    lock20_count = 0
    sl20_count = 0
    total_sim_pnl = 0.0

    for deal in sorted(bot_deals, key=lambda x: x["time"]):
        pos_id = deal.get("position_id", deal.get("order"))
        entry_p = deal.get("price", 0.0)
        entry_t_sec = deal.get("time", 0)
        direction = "BUY" if deal.get("type") == 0 else "SELL"
        symbol = deal.get("symbol", "XAUUSDz")

        init_sl = round(entry_p - 2.00, 2) if direction == "BUY" else round(entry_p + 2.00, 2)
        init_tp = round(entry_p + 5.00, 2) if direction == "BUY" else round(entry_p - 5.00, 2)

        # Fetch M1 rates up to 2 hours post-entry
        from_sec = entry_t_sec
        to_sec = entry_t_sec + (2 * 3600)
        rates = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_M1, from_sec, to_sec)

        if rates is None or len(rates) == 0:
            continue

        current_sl = init_sl
        current_tp = init_tp
        is_locked_20 = False
        exit_price = None
        exit_reason = None
        pnl = 0.0

        for r in rates:
            high = r["high"]
            low = r["low"]
            open_bar = r["open"]
            close_bar = r["close"]

            if direction == "BUY":
                # State 1: Before $20 lock is active
                if not is_locked_20:
                    # Did price hit initial SL ($2.00 below entry)?
                    if low <= current_sl:
                        exit_price = current_sl
                        exit_reason = "HIT_INITIAL_SL_20USD"
                        pnl = -20.0
                        break

                    # Did price reach $20 profit ($2.00 above entry)?
                    if high >= (entry_p + 2.00):
                        is_locked_20 = True
                        current_sl = round(entry_p + 2.00, 2)  # SL is now AT entry + 2.00

                        # Check if within this same bar or next, low dips to or below current_sl (entry + 2.00)
                        if low <= current_sl:
                            exit_price = current_sl
                            exit_reason = "HIT_LOCKED_SL_20USD"
                            pnl = 20.0
                            break
                        elif high >= current_tp:
                            exit_price = current_tp
                            exit_reason = "HIT_TP_50USD"
                            pnl = 50.0
                            break

                # State 2: After $20 lock is active
                else:
                    # Check SL hit first (if low dips to entry + 2.00)
                    if low <= current_sl:
                        exit_price = current_sl
                        exit_reason = "HIT_LOCKED_SL_20USD"
                        pnl = 20.0
                        break

                    # Check TP hit ($5.00 above entry)
                    if high >= current_tp:
                        exit_price = current_tp
                        exit_reason = "HIT_TP_50USD"
                        pnl = 50.0
                        break

            elif direction == "SELL":
                # State 1: Before $20 lock is active
                if not is_locked_20:
                    # Did price hit initial SL ($2.00 above entry)?
                    if high >= current_sl:
                        exit_price = current_sl
                        exit_reason = "HIT_INITIAL_SL_20USD"
                        pnl = -20.0
                        break

                    # Did price reach $20 profit ($2.00 below entry)?
                    if low <= (entry_p - 2.00):
                        is_locked_20 = True
                        current_sl = round(entry_p - 2.00, 2)  # SL is now AT entry - 2.00

                        if high >= current_sl:
                            exit_price = current_sl
                            exit_reason = "HIT_LOCKED_SL_20USD"
                            pnl = 20.0
                            break
                        elif low <= current_tp:
                            exit_price = current_tp
                            exit_reason = "HIT_TP_50USD"
                            pnl = 50.0
                            break

                # State 2: After $20 lock is active
                else:
                    if high >= current_sl:
                        exit_price = current_sl
                        exit_reason = "HIT_LOCKED_SL_20USD"
                        pnl = 20.0
                        break

                    if low <= current_tp:
                        exit_price = current_tp
                        exit_reason = "HIT_TP_50USD"
                        pnl = 50.0
                        break

        if exit_reason is None:
            last_rate = rates[-1]
            last_close = last_rate["close"]
            m2m = (last_close - entry_p) * 10.0 if direction == "BUY" else (entry_p - last_close) * 10.0
            pnl = m2m
            exit_reason = "MARK_TO_MARKET"

        if exit_reason == "HIT_TP_50USD":
            tp50_count += 1
        elif exit_reason == "HIT_LOCKED_SL_20USD":
            lock20_count += 1
        elif exit_reason == "HIT_INITIAL_SL_20USD":
            sl20_count += 1

        total_sim_pnl += pnl

    total_sim = len(bot_deals)
    win_count = tp50_count + lock20_count
    win_rate = (win_count / total_sim) * 100.0 if total_sim > 0 else 0.0

    print("==========================================================================================")
    print("  STRICT MICRO-RETRACTED SIMULATION AUDIT RESULTS")
    print("==========================================================================================")
    print(f"Total Signals Replayed: {total_sim}")
    print(f"Trades Exiting at Full TP (+$50.00): {tp50_count} ({tp50_count/total_sim*100.0:.1f}%)")
    print(f"Trades Stopped at Locked $20 Profit (+$20.00): {lock20_count} ({lock20_count/total_sim*100.0:.1f}%)")
    print(f"Trades Exiting at Initial SL (-$20.00): {sl20_count} ({sl20_count/total_sim*100.0:.1f}%)")
    print(f"\nStrict Win Rate (Profit >= $20): {win_rate:.1f}%")
    print(f"Realized Net Simulated Profit: ${total_sim_pnl:+.2f}")
    print("==========================================================================================")

if __name__ == "__main__":
    run_micro_realistic_simulation()
