

#!/usr/bin/env python3
"""
simulate_option_a_no_cooldown.py - Option A ($20 Profit Lock) without Cooldown + FOMC Filter

Evaluates Option A:
- Initial SL = $2.00/oz ($20 risk), Initial TP = $5.00/oz ($50 target)
- $20 Lock Rule: When price hits +$2.00/oz ($20 profit), SL moves directly to Entry + $2.00 ($20 profit locked)
- Cooldown: REMOVED (0s cooldown, all signals evaluated)
- FOMC Filter: Active (18:00 - 20:00 UTC Paused)
"""

import sys
import os
sys.path.insert(0, os.path.abspath("."))
import pandas as pd
from datetime import datetime, timezone, timedelta
import MetaTrader5 as mt5

def run_option_a_no_cooldown():
    print("==========================================================================================")
    print("  SIMULATION AUDIT: OPTION A ($20 PROFIT LOCK) WITHOUT COOLDOWN + FOMC FILTER")
    print("==========================================================================================")

    if not mt5.initialize():
        print("[ERROR] MetaTrader 5 terminal not connected.")
        return

    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    deals = mt5.history_deals_get(today_start, datetime.now(timezone.utc) + timedelta(days=1)) or []

    raw_deals = [d._asdict() for d in deals if (d.magic == 1001 or "CAND-LIVE" in str(d.comment)) and d.entry == 0]

    if not raw_deals:
        print("[INFO] No entry signals found today.")
        return

    sorted_deals = sorted(raw_deals, key=lambda x: x["time"])

    # Filter out only FOMC hours (18:00 - 20:00 UTC), NO Cooldown
    accepted_signals = []
    for d in sorted_deals:
        time_sec = d.get("time", 0)
        time_dt = datetime.fromtimestamp(time_sec, tz=timezone.utc)
        if 18 <= time_dt.hour < 20:
            continue
        accepted_signals.append(d)

    tp50_count = 0
    lock20_count = 0
    sl20_count = 0
    total_pnl = 0.0

    for deal in accepted_signals:
        entry_p = deal.get("price", 0.0)
        entry_t_sec = deal.get("time", 0)
        direction = "BUY" if deal.get("type") == 0 else "SELL"
        symbol = deal.get("symbol", "XAUUSDz")

        init_sl = round(entry_p - 2.00, 2) if direction == "BUY" else round(entry_p + 2.00, 2)
        init_tp = round(entry_p + 5.00, 2) if direction == "BUY" else round(entry_p - 5.00, 2)

        rates = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_M1, entry_t_sec, entry_t_sec + 7200)
        if rates is None or len(rates) == 0:
            continue

        current_sl = init_sl
        current_tp = init_tp
        is_locked = False
        exit_reason = None
        pnl = 0.0

        for r in rates:
            high = r["high"]
            low = r["low"]

            if direction == "BUY":
                if not is_locked and low <= current_sl:
                    exit_reason = "HIT_INITIAL_SL"
                    pnl = -20.0
                    break

                if not is_locked and high >= (entry_p + 2.00):
                    is_locked = True
                    current_sl = round(entry_p + 2.00, 2)  # Move SL to Entry + $2.00 ($20 profit locked)

                    if low <= current_sl:
                        exit_reason = "HIT_LOCKED_20USD"
                        pnl = 20.0
                        break
                    elif high >= current_tp:
                        exit_reason = "HIT_TP_50USD"
                        pnl = 50.0
                        break

                if is_locked:
                    if low <= current_sl:
                        exit_reason = "HIT_LOCKED_20USD"
                        pnl = 20.0
                        break
                    elif high >= current_tp:
                        exit_reason = "HIT_TP_50USD"
                        pnl = 50.0
                        break

            elif direction == "SELL":
                if not is_locked and high >= current_sl:
                    exit_reason = "HIT_INITIAL_SL"
                    pnl = -20.0
                    break

                if not is_locked and low <= (entry_p - 2.00):
                    is_locked = True
                    current_sl = round(entry_p - 2.00, 2)  # Move SL to Entry - $2.00 ($20 profit locked)

                    if high >= current_sl:
                        exit_reason = "HIT_LOCKED_20USD"
                        pnl = 20.0
                        break
                    elif low <= current_tp:
                        exit_reason = "HIT_TP_50USD"
                        pnl = 50.0
                        break

                if is_locked:
                    if high >= current_sl:
                        exit_reason = "HIT_LOCKED_20USD"
                        pnl = 20.0
                        break
                    elif low <= current_tp:
                        exit_reason = "HIT_TP_50USD"
                        pnl = 50.0
                        break

        if exit_reason == "HIT_TP_50USD":
            tp50_count += 1
        elif exit_reason == "HIT_LOCKED_20USD":
            lock20_count += 1
        elif exit_reason == "HIT_INITIAL_SL":
            sl20_count += 1

        total_pnl += pnl

    total_accepted = len(accepted_signals)
    win_count = tp50_count + lock20_count
    win_rate = (win_count / total_accepted) * 100.0 if total_accepted > 0 else 0.0

    print("==========================================================================================")
    print("  SIMULATION AUDIT RESULTS: OPTION A ($20 PROFIT LOCK) WITHOUT COOLDOWN")
    print("==========================================================================================")
    print(f"Total Signals Accepted (FOMC Paused, NO Cooldown): {total_accepted}")
    print(f"Full Take Profit Hits (+$50.00): {tp50_count} ({tp50_count/total_accepted*100.0:.1f}%)")
    print(f"Locked $20 Profit Exits (+$20.00): {lock20_count} ({lock20_count/total_accepted*100.0:.1f}%)")
    print(f"Initial Stop Loss Hits (-$20.00): {sl20_count} ({sl20_count/total_accepted*100.0:.1f}%)")
    print(f"\nOverall Effective Win Rate (Profit >= $20): {win_rate:.1f}% ({win_count} Wins / {sl20_count} Losses)")
    print(f"REALIZED NET SIMULATED PROFIT: ${total_pnl:+.2f}")
    print("==========================================================================================")

if __name__ == "__main__":
    run_option_a_no_cooldown()
