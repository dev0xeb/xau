#!/usr/bin/env python3
"""
simulate_today_buffer_lock.py - Simulation with $1.50 Buffer Profit Lock

Evaluates order execution mechanics with buffer:
- Initial SL = $2.00/oz ($20 risk), Initial TP = $5.00/oz ($50 target)
- Activation: When price reaches +$2.00/oz (+$20 profit), SL moves to Entry + $0.50 (Risk-Free + $5 locked, with $1.50 buffer).
- Trailing: Trails $1.50 behind price as it expands toward +$5.00 ($50 TP).
"""

import sys
import os
sys.path.insert(0, os.path.abspath("."))
import pandas as pd
from datetime import datetime, timezone, timedelta
import MetaTrader5 as mt5

def run_buffer_lock_simulation():
    print("==========================================================================================")
    print("  SIMULATION AUDIT: $20 PROFIT ACTIVATION WITH $1.50 NOISE BUFFER")
    print("  Rule: At +$2.00 ($20 profit), SL moves to Entry + $0.50 ($5 profit locked), trailing $1.50 behind")
    print("==========================================================================================")

    if not mt5.initialize():
        print("[ERROR] MetaTrader 5 terminal not connected.")
        return

    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    deals = mt5.history_deals_get(today_start, datetime.now(timezone.utc) + timedelta(days=1)) or []

    bot_deals = [d._asdict() for d in deals if (d.magic == 1001 or "CAND-LIVE" in str(d.comment)) and d.entry == 0]

    print(f"[DATA] Replaying {len(bot_deals)} raw entry signals...\n")

    if not bot_deals:
        print("[INFO] No entry signals found today.")
        return

    tp50_count = 0
    trailed_win_count = 0
    be_lock_count = 0
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

        from_sec = entry_t_sec
        to_sec = entry_t_sec + (2 * 3600)
        rates = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_M1, from_sec, to_sec)

        if rates is None or len(rates) == 0:
            continue

        current_sl = init_sl
        current_tp = init_tp
        is_locked = False
        exit_price = None
        exit_reason = None
        pnl = 0.0

        for r in rates:
            high = r["high"]
            low = r["low"]

            if direction == "BUY":
                # Check initial SL
                if not is_locked and low <= current_sl:
                    exit_price = current_sl
                    exit_reason = "HIT_INITIAL_SL_20USD"
                    pnl = -20.0
                    break

                # Check activation at +$2.00 ($20 profit)
                if not is_locked and high >= (entry_p + 2.00):
                    is_locked = True
                    current_sl = round(entry_p + 0.50, 2)  # Move SL to Entry + $0.50 (Risk-Free + $5 locked)

                # If locked, evaluate trailing SL & TP
                if is_locked:
                    # Update trailing SL ($1.50 behind high)
                    possible_sl = round(high - 1.50, 2)
                    if possible_sl > current_sl:
                        current_sl = possible_sl

                    # Check TP ($5.00)
                    if high >= current_tp:
                        exit_price = current_tp
                        exit_reason = "HIT_TP_50USD"
                        pnl = 50.0
                        break

                    # Check SL hit
                    if low <= current_sl:
                        exit_price = current_sl
                        pnl = round((exit_price - entry_p) * 10.0, 2)
                        if pnl >= 20.0:
                            exit_reason = "HIT_TRAILED_WIN"
                        else:
                            exit_reason = "HIT_BE_LOCK_5USD"
                        break

            elif direction == "SELL":
                # Check initial SL
                if not is_locked and high >= current_sl:
                    exit_price = current_sl
                    exit_reason = "HIT_INITIAL_SL_20USD"
                    pnl = -20.0
                    break

                # Check activation at +$2.00 ($20 profit)
                if not is_locked and low <= (entry_p - 2.00):
                    is_locked = True
                    current_sl = round(entry_p - 0.50, 2)  # Move SL to Entry - $0.50

                # If locked, evaluate trailing SL & TP
                if is_locked:
                    possible_sl = round(low + 1.50, 2)
                    if possible_sl < current_sl:
                        current_sl = possible_sl

                    if low <= current_tp:
                        exit_price = current_tp
                        exit_reason = "HIT_TP_50USD"
                        pnl = 50.0
                        break

                    if high >= current_sl:
                        exit_price = current_sl
                        pnl = round((entry_p - exit_price) * 10.0, 2)
                        if pnl >= 20.0:
                            exit_reason = "HIT_TRAILED_WIN"
                        else:
                            exit_reason = "HIT_BE_LOCK_5USD"
                        break

        if exit_reason is None:
            last_rate = rates[-1]
            last_close = last_rate["close"]
            pnl = (last_close - entry_p) * 10.0 if direction == "BUY" else (entry_p - last_close) * 10.0
            exit_reason = "MARK_TO_MARKET"

        if exit_reason == "HIT_TP_50USD":
            tp50_count += 1
        elif exit_reason == "HIT_TRAILED_WIN":
            trailed_win_count += 1
        elif exit_reason == "HIT_BE_LOCK_5USD":
            be_lock_count += 1
        elif exit_reason == "HIT_INITIAL_SL_20USD":
            sl20_count += 1

        total_sim_pnl += pnl

    total_sim = len(bot_deals)
    win_count = tp50_count + trailed_win_count + be_lock_count
    win_rate = (win_count / total_sim) * 100.0 if total_sim > 0 else 0.0

    print("==========================================================================================")
    print("  SIMULATION AUDIT RESULTS ($1.50 NOISE BUFFER RULE)")
    print("==========================================================================================")
    print(f"Total Signals Replayed: {total_sim}")
    print(f"Trades Exiting at Full TP (+$50.00): {tp50_count} ({tp50_count/total_sim*100.0:.1f}%)")
    print(f"Trades Exiting at Trailed Win (+$20.00 to +$49.00): {trailed_win_count} ({trailed_win_count/total_sim*100.0:.1f}%)")
    print(f"Trades Exiting at Risk-Free Lock (+$5.00 to +$19.00): {be_lock_count} ({be_lock_count/total_sim*100.0:.1f}%)")
    print(f"Trades Exiting at Initial SL (-$20.00): {sl20_count} ({sl20_count/total_sim*100.0:.1f}%)")
    print(f"\nOverall Effective Win Rate (Risk-Free or Better): {win_rate:.1f}%")
    print(f"Realized Net Simulated Profit: ${total_sim_pnl:+.2f}")
    print("==========================================================================================")

if __name__ == "__main__":
    run_buffer_lock_simulation()
