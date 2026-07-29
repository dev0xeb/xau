#!/usr/bin/env python3
"""
simulate_today_optimized.py - Deep Rigorous Optimization Simulation Comparing $20 vs $15 Profit Lock

Compares side-by-side with 15s Cooldown and FOMC Filter:
- Option A: $2.00 Activation ($20 Profit Lock -> SL to Entry + $0.50, trailing $1.50)
- Option B: $1.50 Activation ($15 Profit Lock -> SL to Entry + $0.50, trailing $1.00)
"""

import sys
import os
sys.path.insert(0, os.path.abspath("."))
import pandas as pd
from datetime import datetime, timezone, timedelta
import MetaTrader5 as mt5

def run_comparative_simulation():
    print("==========================================================================================")
    print("  COMPARATIVE SIMULATION: $20 PROFIT LOCK vs $15 PROFIT LOCK")
    print("  With 15-Second Cooldown & FOMC News Filter (18:00 - 20:00 UTC Paused)")
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

    # Filter guardrails
    accepted_signals = []
    skipped_cooldown_count = 0
    skipped_fomc_count = 0
    last_accepted_sec = 0

    for d in sorted_deals:
        time_sec = d.get("time", 0)
        time_dt = datetime.fromtimestamp(time_sec, tz=timezone.utc)
        hour_utc = time_dt.hour

        if 18 <= hour_utc < 20:
            skipped_fomc_count += 1
            continue

        if (time_sec - last_accepted_sec) < 15:
            skipped_cooldown_count += 1
            continue

        last_accepted_sec = time_sec
        accepted_signals.append(d)

    print(f"[DATA] Replaying {len(accepted_signals)} accepted signals after guardrail filtering...\n")

    def simulate_strategy(activation_usd, lock_sl_usd, trailing_offset_usd):
        tp50_count = 0
        trailed_win_count = 0
        be_lock_count = 0
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
            exit_price = None
            exit_reason = None
            pnl = 0.0

            for r in rates:
                high = r["high"]
                low = r["low"]

                if direction == "BUY":
                    if not is_locked and low <= current_sl:
                        exit_price = current_sl
                        exit_reason = "HIT_INITIAL_SL"
                        pnl = -20.0
                        break

                    if not is_locked and high >= (entry_p + activation_usd):
                        is_locked = True
                        current_sl = round(entry_p + lock_sl_usd, 2)

                    if is_locked:
                        possible_sl = round(high - trailing_offset_usd, 2)
                        if possible_sl > current_sl:
                            current_sl = possible_sl

                        if high >= current_tp:
                            exit_price = current_tp
                            exit_reason = "HIT_TP_50USD"
                            pnl = 50.0
                            break

                        if low <= current_sl:
                            exit_price = current_sl
                            pnl = round((exit_price - entry_p) * 10.0, 2)
                            if pnl >= activation_usd * 10.0:
                                exit_reason = "HIT_TRAILED_WIN"
                            else:
                                exit_reason = "HIT_BE_LOCK"
                            break

                elif direction == "SELL":
                    if not is_locked and high >= current_sl:
                        exit_price = current_sl
                        exit_reason = "HIT_INITIAL_SL"
                        pnl = -20.0
                        break

                    if not is_locked and low <= (entry_p - activation_usd):
                        is_locked = True
                        current_sl = round(entry_p - lock_sl_usd, 2)

                    if is_locked:
                        possible_sl = round(low + trailing_offset_usd, 2)
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
                            if pnl >= activation_usd * 10.0:
                                exit_reason = "HIT_TRAILED_WIN"
                            else:
                                exit_reason = "HIT_BE_LOCK"
                            break

            if exit_reason == "HIT_TP_50USD":
                tp50_count += 1
            elif exit_reason == "HIT_TRAILED_WIN":
                trailed_win_count += 1
            elif exit_reason == "HIT_BE_LOCK":
                be_lock_count += 1
            elif exit_reason == "HIT_INITIAL_SL":
                sl20_count += 1

            total_pnl += pnl

        win_count = tp50_count + trailed_win_count + be_lock_count
        win_rate = (win_count / len(accepted_signals)) * 100.0 if accepted_signals else 0.0

        return {
            "tp50": tp50_count,
            "trailed_win": trailed_win_count,
            "be_lock": be_lock_count,
            "sl20": sl20_count,
            "win_rate": win_rate,
            "net_pnl": total_pnl
        }

    # Run Option A: $20 Profit Activation ($2.00/oz) with $1.50 trailing offset
    res_A = simulate_strategy(activation_usd=2.00, lock_sl_usd=0.50, trailing_offset_usd=1.50)

    # Run Option B: $15 Profit Activation ($1.50/oz) with $1.00 trailing offset
    res_B = simulate_strategy(activation_usd=1.50, lock_sl_usd=0.50, trailing_offset_usd=1.00)

    print("==========================================================================================")
    print("  SIDE-BY-SIDE COMPARISON: $20 ACTIVATION VS $15 ACTIVATION (WITH GUARDRAILS)")
    print("==========================================================================================")
    print(f"Accepted Signals Replayed: {len(accepted_signals)}\n")

    print(f"OPTION A: $20 Profit Activation ($2.00/oz) [SL -> Entry + $0.50, Trailing $1.50]")
    print(f"  - Full TP Hits (+$50.00): {res_A['tp50']}")
    print(f"  - Trailed Win Exits (+$20.00+): {res_A['trailed_win']}")
    print(f"  - Risk-Free Exits (+$5.00+): {res_A['be_lock']}")
    print(f"  - Initial SL Exits (-$20.00): {res_A['sl20']}")
    print(f"  - Effective Win Rate: {res_A['win_rate']:.1f}%")
    print(f"  - NET SIMULATED PnL: ${res_A['net_pnl']:+.2f}\n")

    print(f"OPTION B: $15 Profit Activation ($1.50/oz) [SL -> Entry + $0.50, Trailing $1.00]")
    print(f"  - Full TP Hits (+$50.00): {res_B['tp50']}")
    print(f"  - Trailed Win Exits (+$15.00+): {res_B['trailed_win']}")
    print(f"  - Risk-Free Exits (+$5.00+): {res_B['be_lock']}")
    print(f"  - Initial SL Exits (-$20.00): {res_B['sl20']}")
    print(f"  - Effective Win Rate: {res_B['win_rate']:.1f}%")
    print(f"  - NET SIMULATED PnL: ${res_B['net_pnl']:+.2f}")
    print("==========================================================================================")

if __name__ == "__main__":
    run_comparative_simulation()
