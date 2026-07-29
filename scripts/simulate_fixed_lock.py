#!/usr/bin/env python3
"""
simulate_fixed_lock.py - Fixed Break-Even Simulation (NO Trailing Stop Offset)

Evaluates fixed Break-Even rules (NO trailing stop following price):
- Initial SL = $2.00/oz ($20 risk), Initial TP = $5.00/oz ($50 target)
- Option A ($20 Rule): When price hits +$2.00/oz ($20 profit), SL moves to Break-Even + $0.10 ($1 profit locked) and stays fixed.
- Option B ($15 Rule): When price hits +$1.50/oz ($15 profit), SL moves to Break-Even + $0.10 ($1 profit locked) and stays fixed.
- Replayed with 15s Cooldown & FOMC Filter (18:00 - 20:00 UTC Paused).
"""

import sys
import os
sys.path.insert(0, os.path.abspath("."))
import pandas as pd
from datetime import datetime, timezone, timedelta
import MetaTrader5 as mt5

def run_fixed_lock_simulation():
    print("==========================================================================================")
    print("  SIMULATION AUDIT: FIXED BREAK-EVEN ACTIVATION (NO TRAILING STOP OFFSET)")
    print("  Comparing Fixed $20 Trigger vs Fixed $15 Trigger with 15s Cooldown & FOMC Filter")
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

    # Apply 15s Cooldown & FOMC News Filter
    accepted_signals = []
    last_accepted_sec = 0

    for d in sorted_deals:
        time_sec = d.get("time", 0)
        time_dt = datetime.fromtimestamp(time_sec, tz=timezone.utc)
        hour_utc = time_dt.hour

        if 18 <= hour_utc < 20:
            continue

        if (time_sec - last_accepted_sec) < 15:
            continue

        last_accepted_sec = time_sec
        accepted_signals.append(d)

    def simulate_fixed_rule(trigger_usd):
        tp50_count = 0
        be_count = 0
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
            is_be_active = False
            exit_reason = None
            pnl = 0.0

            for r in rates:
                high = r["high"]
                low = r["low"]

                if direction == "BUY":
                    # Check initial SL hit before trigger
                    if not is_be_active and low <= current_sl:
                        exit_reason = "HIT_INITIAL_SL"
                        pnl = -20.0
                        break

                    # Check trigger ($15 or $20)
                    if not is_be_active and high >= (entry_p + trigger_usd):
                        is_be_active = True
                        current_sl = round(entry_p + 0.10, 2)  # Fixed Break-Even SL (+ $1 profit locked)

                    if is_be_active:
                        # Check TP hit ($50)
                        if high >= current_tp:
                            exit_reason = "HIT_TP_50USD"
                            pnl = 50.0
                            break

                        # Check BE hit (+ $1)
                        if low <= current_sl:
                            exit_reason = "HIT_BREAK_EVEN"
                            pnl = 1.00
                            break

                elif direction == "SELL":
                    if not is_be_active and high >= current_sl:
                        exit_reason = "HIT_INITIAL_SL"
                        pnl = -20.0
                        break

                    if not is_be_active and low <= (entry_p - trigger_usd):
                        is_be_active = True
                        current_sl = round(entry_p - 0.10, 2)  # Fixed Break-Even SL (+ $1 profit locked)

                    if is_be_active:
                        if low <= current_tp:
                            exit_reason = "HIT_TP_50USD"
                            pnl = 50.0
                            break

                        if high >= current_sl:
                            exit_reason = "HIT_BREAK_EVEN"
                            pnl = 1.00
                            break

            if exit_reason == "HIT_TP_50USD":
                tp50_count += 1
            elif exit_reason == "HIT_BREAK_EVEN":
                be_count += 1
            elif exit_reason == "HIT_INITIAL_SL":
                sl20_count += 1

            total_pnl += pnl

        win_count = tp50_count + be_count
        win_rate = (win_count / len(accepted_signals)) * 100.0 if accepted_signals else 0.0

        return {
            "tp50": tp50_count,
            "be": be_count,
            "sl20": sl20_count,
            "win_rate": win_rate,
            "net_pnl": total_pnl
        }

    # Option A: Fixed $20 Trigger ($2.00/oz -> Move SL to Break-Even + $0.10)
    res_A = simulate_fixed_rule(trigger_usd=2.00)

    # Option B: Fixed $15 Trigger ($1.50/oz -> Move SL to Break-Even + $0.10)
    res_B = simulate_fixed_rule(trigger_usd=1.50)

    print("==========================================================================================")
    print("  FIXED BREAK-EVEN SIMULATION RESULTS (NO TRAILING OFFSET)")
    print("==========================================================================================")
    print(f"Accepted Signals Replayed: {len(accepted_signals)}\n")

    print(f"OPTION A: Fixed $20 Profit Trigger ($2.00/oz -> Move SL to Break-Even)")
    print(f"  - Full Take Profit Hits (+$50.00): {res_A['tp50']} trades")
    print(f"  - Break-Even Exits (+$1.00 Risk-Free): {res_A['be']} trades")
    print(f"  - Initial SL Hits (-$20.00): {res_A['sl20']} trades")
    print(f"  - Effective Win Rate (BE or Better): {res_A['win_rate']:.1f}%")
    print(f"  - NET SIMULATED PnL: ${res_A['net_pnl']:+.2f}\n")

    print(f"OPTION B: Fixed $15 Profit Trigger ($1.50/oz -> Move SL to Break-Even)")
    print(f"  - Full Take Profit Hits (+$50.00): {res_B['tp50']} trades")
    print(f"  - Break-Even Exits (+$1.00 Risk-Free): {res_B['be']} trades")
    print(f"  - Initial SL Hits (-$20.00): {res_B['sl20']} trades")
    print(f"  - Effective Win Rate (BE or Better): {res_B['win_rate']:.1f}%")
    print(f"  - NET SIMULATED PnL: ${res_B['net_pnl']:+.2f}")
    print("==========================================================================================")

if __name__ == "__main__":
    run_fixed_lock_simulation()
