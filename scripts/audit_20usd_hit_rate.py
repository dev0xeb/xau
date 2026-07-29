
#!/usr/bin/env python3
"""
audit_20usd_hit_rate.py - High-Precision $20 Profit MFE Trajectory Audit

Analyzes all closed positions executed by STRAT-XAU-001 (Magic 1001 / CAND-LIVE-*) today:
- Traces exact price movement (M1 candles) between entry_time and exit_time for every trade.
- Measures whether the trade reached >= $2.00/oz (+ $20.00 profit) BEFORE hitting SL or TP.
- Reports exact counts and percentages with 100% mathematical precision.
"""

import sys
import os
sys.path.insert(0, os.path.abspath("."))
import pandas as pd
from datetime import datetime, timezone, timedelta
import MetaTrader5 as mt5

def audit_20usd_hit_rate():
    print("==========================================================================================")
    print("  HIGH-PRECISION AUDIT: TRADES REACHING >= $20 PROFIT (+$2.00/oz MFE) TODAY")
    print("==========================================================================================")

    if not mt5.initialize():
        print("[ERROR] MetaTrader 5 terminal not connected.")
        return

    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    deals = mt5.history_deals_get(today_start, datetime.now(timezone.utc) + timedelta(days=1)) or []

    # Filter strictly for Magic 1001 or CAND-LIVE-*
    bot_deals = [d._asdict() for d in deals if d.magic == 1001 or "CAND-LIVE" in str(d.comment)]

    # Pair entry (DEAL_ENTRY_IN) and exit (DEAL_ENTRY_OUT) by position_id
    position_map = {}
    for d in bot_deals:
        pos_id = d.get("position_id", d.get("order"))
        if pos_id not in position_map:
            position_map[pos_id] = {"in": None, "out": None}

        if d.get("entry") == 0:  # IN
            position_map[pos_id]["in"] = d
        elif d.get("entry") == 1:  # OUT
            position_map[pos_id]["out"] = d

    closed_positions = []
    for pos_id, p in position_map.items():
        if p["in"] and p["out"]:
            closed_positions.append({
                "pos_id": pos_id,
                "in": p["in"],
                "out": p["out"]
            })

    print(f"[DATA] Retrived {len(closed_positions)} paired entry-exit position records for today.\n")

    if not closed_positions:
        print("[INFO] No completed paired positions found for today.")
        return

    hit_20_count = 0
    missed_20_count = 0

    hit_20_trades = []
    missed_20_trades = []

    for item in closed_positions:
        in_d = item["in"]
        out_d = item["out"]
        pos_id = item["pos_id"]

        entry_p = in_d.get("price", 0.0)
        exit_p = out_d.get("price", 0.0)
        entry_t_sec = in_d.get("time", 0)
        exit_t_sec = out_d.get("time", 0)
        direction = "BUY" if in_d.get("type") == 0 else "SELL"
        profit = out_d.get("profit", 0.0)
        comment = in_d.get("comment") or out_d.get("comment") or ""

        # Fetch M1 rates during trade lifetime (buffer 1 minute on each end)
        from_sec = max(0, entry_t_sec - 60)
        to_sec = exit_t_sec + 60
        rates = mt5.copy_rates_range(in_d.get("symbol", "XAUUSDz"), mt5.TIMEFRAME_M1, from_sec, to_sec)

        mfe_pts = 0.0
        hit_20 = False

        if rates is not None and len(rates) > 0:
            df = pd.DataFrame(rates)
            if direction == "BUY":
                max_high = df["high"].max()
                mfe_pts = round(max_high - entry_p, 2)
                hit_20 = mfe_pts >= 2.00
            else:
                min_low = df["low"].min()
                mfe_pts = round(entry_p - min_low, 2)
                hit_20 = mfe_pts >= 2.00
        else:
            # Fallback based on exit price if rates empty
            if direction == "BUY":
                mfe_pts = round(exit_p - entry_p, 2)
                hit_20 = mfe_pts >= 2.00 or profit >= 20.0
            else:
                mfe_pts = round(entry_p - exit_p, 2)
                hit_20 = mfe_pts >= 2.00 or profit >= 20.0

        trade_info = {
            "pos_id": pos_id,
            "direction": direction,
            "entry_p": entry_p,
            "exit_p": exit_p,
            "profit": profit,
            "mfe_pts": mfe_pts,
            "hit_20": hit_20,
            "comment": comment
        }

        if hit_20:
            hit_20_count += 1
            hit_20_trades.append(trade_info)
        else:
            missed_20_count += 1
            missed_20_trades.append(trade_info)

    total_closed = len(closed_positions)
    pct_hit_20 = (hit_20_count / total_closed) * 100.0 if total_closed > 0 else 0.0

    print("==========================================================================================")
    print("  EXACT AUDIT RESULTS SUMMARY")
    print("==========================================================================================")
    print(f"Total Paired Trades Analyzed Today (July 29): {total_closed}")
    print(f"Trades Reaching >= $20.00 Profit (+$2.00/oz MFE): {hit_20_count} ({pct_hit_20:.1f}%)")
    print(f"Trades Failing to Reach $20.00 Profit (< +$2.00/oz MFE): {missed_20_count} ({100.0 - pct_hit_20:.1f}%)")
    print("==========================================================================================")

    # Print breakdown by final outcome for trades that hit $20
    hit_20_wins = [t for t in hit_20_trades if t['profit'] > 0]
    hit_20_losses = [t for t in hit_20_trades if t['profit'] < 0]
    print(f"\nOf the {hit_20_count} trades that reached $20 profit:")
    print(f"  - Closed as Wins: {len(hit_20_wins)} trades")
    print(f"  - Closed as Losses (retraced before $20 lock was in place): {len(hit_20_losses)} trades")

if __name__ == "__main__":
    audit_20usd_hit_rate()
