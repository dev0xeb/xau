#!/usr/bin/env python3
"""
deep_trade_trajectory_audit.py - Deep Trajectory Audit for Bot Trades

Analyzes every trade executed by STRAT-XAU-001 (Magic 1001 / CAND-LIVE-*):
- Trajectories 30 mins post-entry using M1 bar rates.
- Measures MFE (Max Favorable Excursion) and MAE (Max Adverse Excursion).
- Identifies trades choked by Break-Even SL that would have reached full +$5.00 TP.
"""

import sys
import os
sys.path.insert(0, os.path.abspath("."))
import json
import pandas as pd
from datetime import datetime, timezone, timedelta
import MetaTrader5 as mt5

def run_deep_trade_trajectory_audit():
    print("======================================================================")
    print("  DEEP BOT TRADE TRAJECTORY & TRAILING STOP AUDIT")
    print("======================================================================")

    if not mt5.initialize():
        print("[ERROR] MetaTrader 5 terminal not connected.")
        return

    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    deals = mt5.history_deals_get(today_start - timedelta(days=1), datetime.now(timezone.utc) + timedelta(days=1))

    if not deals:
        print("[INFO] No MT5 deals found.")
        return

    # Filter for deals belonging to this bot
    bot_deals = []
    for d in deals:
        dd = d._asdict()
        magic = dd.get("magic", 0)
        comment = str(dd.get("comment", ""))
        symbol = str(dd.get("symbol", ""))

        if magic == 1001 or "CAND-LIVE" in comment or "XAU_SCALP" in comment or "TEST" in comment or ("XAUUSD" in symbol and dd.get("entry") == 1):
            bot_deals.append(dd)

    print(f"[DATA] Retrived {len(bot_deals)} bot deal events from MT5 history.\n")

    # Group out deals (closures)
    closed_deals = [d for d in bot_deals if d.get("entry") == 1]  # DEAL_ENTRY_OUT

    if not closed_deals:
        print("[INFO] No closed bot positions found yet.")
        return

    audit_results = []
    choked_to_full_tp_count = 0

    for deal in closed_deals:
        ticket = deal.get("position_id", deal.get("order"))
        comment = deal.get("comment", "")
        exit_price = deal.get("price", 0.0)
        exit_time_sec = deal.get("time", 0)
        exit_time = datetime.fromtimestamp(exit_time_sec, tz=timezone.utc)
        profit = deal.get("profit", 0.0)
        volume = deal.get("volume", 0.01)

        # Find matching in deal (entry)
        in_deals = [d for d in bot_deals if d.get("position_id") == ticket and d.get("entry") == 0]
        if not in_deals:
            in_deals = [d for d in bot_deals if d.get("entry") == 0 and abs(d.get("time") - exit_time_sec) < 3600]

        if not in_deals:
            continue

        in_deal = in_deals[0]
        entry_price = in_deal.get("price", exit_price)
        entry_time_sec = in_deal.get("time", exit_time_sec)
        entry_time = datetime.fromtimestamp(entry_time_sec, tz=timezone.utc)
        direction = "BUY" if in_deal.get("type") == 0 else "SELL"

        # Fetch 30 mins M1 rates post-entry to track trajectory
        rates = mt5.copy_rates_from(deal.get("symbol", "XAUUSDz"), mt5.TIMEFRAME_M1, entry_time_sec, 30)
        if rates is None or len(rates) == 0:
            continue

        df_rates = pd.DataFrame(rates)
        max_high = df_rates["high"].max()
        min_low = df_rates["low"].min()

        if direction == "BUY":
            mfe_pts = round(max_high - entry_price, 2)
            mae_pts = round(entry_price - min_low, 2)
            reached_50_tp = max_high >= (entry_price + 4.90)
            would_avoid_sl = min_low > (entry_price - 2.00)
        else:
            mfe_pts = round(entry_price - min_low, 2)
            mae_pts = round(max_high - entry_price, 2)
            reached_50_tp = min_low <= (entry_price - 4.90)
            would_avoid_sl = max_high < (entry_price + 2.00)

        is_be_choked = (0.0 <= profit <= 1.50) and reached_50_tp and would_avoid_sl
        if is_be_choked:
            choked_to_full_tp_count += 1

        audit_results.append({
            "ticket": ticket,
            "direction": direction,
            "entry_price": entry_price,
            "exit_price": exit_price,
            "profit": profit,
            "comment": comment,
            "mfe_pts": mfe_pts,
            "mae_pts": mae_pts,
            "reached_50_tp": reached_50_tp,
            "would_avoid_sl": would_avoid_sl,
            "is_be_choked": is_be_choked
        })

    print("---------------------------------------------------------------------------------------------------------")
    print(f"{'TICKET':<12} | {'DIR':<4} | {'ENTRY':<8} | {'EXIT':<8} | {'PNL ($)':<8} | {'MFE ($)':<8} | {'MAE ($)':<8} | {'FULL TP?':<8} | {'STATUS'}")
    print("---------------------------------------------------------------------------------------------------------")

    for r in audit_results:
        tp_str = "YES [OK]" if r['reached_50_tp'] else "NO"
        if r['is_be_choked']:
            status_str = "[CHOKED BY BE] -> WOULD REACH FULL TP ($5.00)"
        elif r['reached_50_tp']:
            status_str = "[FULL TP] Hit Full Target ($5.00)"
        elif r['profit'] > 0:
            status_str = "[WIN] (Partial/BE)"
        else:
            status_str = "[LOSS] (SL)"

        print(f"#{r['ticket']:<11} | {r['direction']:<4} | ${r['entry_price']:<7.2f} | ${r['exit_price']:<7.2f} | ${r['profit']:<7.2f} | ${r['mfe_pts']:<7.2f} | ${r['mae_pts']:<7.2f} | {tp_str:<8} | {status_str}")

    print("---------------------------------------------------------------------------------------------------------")
    total_trades = len(audit_results)
    full_tp_possible = sum(1 for r in audit_results if r['reached_50_tp'] and r['would_avoid_sl'])
    pct_full_tp = (full_tp_possible / total_trades) * 100.0 if total_trades > 0 else 0.0

    print(f"\n======================================================================")
    print("  EXECUTIVE SUMMARY")
    print("======================================================================")
    print(f"Total Bot Positions Analyzed: {total_trades}")
    print(f"Trades Choked Prematurely by Break-Even SL: {choked_to_full_tp_count}")
    print(f"Trades Capable of Full +$5.00 TP (Fixed $2 SL / $5 TP): {full_tp_possible} / {total_trades} ({pct_full_tp:.1f}%)")

if __name__ == "__main__":
    run_deep_trade_trajectory_audit()
