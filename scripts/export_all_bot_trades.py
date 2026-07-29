#!/usr/bin/env python3
"""
export_all_bot_trades.py - Complete Bot Trade History Exporter

Queries all sources for this bot (STRAT-XAU-001 / Magic 1001 / CAND-LIVE-*):
- SQLite trade_journal.db
- JSONL execution_journal.jsonl
- MT5 Deal History for Magic 1001 / CAND-LIVE-*
"""

import sys
import os
sys.path.insert(0, os.path.abspath("."))
import json
import glob
import sqlite3
from datetime import datetime, timezone
import MetaTrader5 as mt5

def export_all_bot_trades():
    print("==========================================================================================")
    print("  COMPLETE RECORDED TRADE HISTORY FOR THIS BOT (STRAT-XAU-001 / Magic 1001)")
    print("==========================================================================================")

    # 1. Query SQLite trade_journal.db
    db_path = os.path.join("execution_engine", "audit", "trade_journal.db")
    db_trades = []
    if os.path.exists(db_path):
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT trade_id, timestamp_utc, entry_price, exit_price, sl, tp, actual_pnl_usd FROM trades")
        rows = cursor.fetchall()
        for r in rows:
            db_trades.append({
                "trade_id": r[0],
                "timestamp_utc": r[1],
                "entry_price": r[2],
                "exit_price": r[3],
                "sl": r[4],
                "tp": r[5],
                "pnl": r[6]
            })
        conn.close()

    # 2. Query MT5 Broker Deal History for Magic 1001 or CAND-LIVE-*
    mt5_bot_trades = []
    if mt5.initialize():
        from datetime import timedelta
        start_date = datetime.now(timezone.utc) - timedelta(days=7)
        deals = mt5.history_deals_get(start_date, datetime.now(timezone.utc) + timedelta(days=1)) or []

        # Filter strictly for this bot
        bot_deals = [d._asdict() for d in deals if d.magic == 1001 or "CAND-LIVE" in str(d.comment)]

        position_map = {}
        for d in bot_deals:
            pos_id = d.get("position_id", d.get("order"))
            if pos_id not in position_map:
                position_map[pos_id] = {"in": None, "out": None}

            if d.get("entry") == 0:  # ENTRY
                position_map[pos_id]["in"] = d
            elif d.get("entry") == 1:  # EXIT
                position_map[pos_id]["out"] = d

        for pos_id, p in position_map.items():
            in_d = p["in"]
            out_d = p["out"]
            if in_d or out_d:
                ref_d = in_d or out_d
                time_sec = ref_d.get("time", 0)
                time_str = datetime.fromtimestamp(time_sec, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
                direction = "BUY" if (in_d and in_d.get("type") == 0) or (out_d and out_d.get("type") == 1) else "SELL"
                entry_p = in_d.get("price", 0.0) if in_d else 0.0
                exit_p = out_d.get("price", 0.0) if out_d else 0.0
                pnl = out_d.get("profit", 0.0) if out_d else 0.0
                comment = (in_d.get("comment") if in_d else "") or (out_d.get("comment") if out_d else "")

                mt5_bot_trades.append({
                    "ticket": pos_id,
                    "timestamp": time_str,
                    "direction": direction,
                    "entry_price": entry_p,
                    "exit_price": exit_p,
                    "pnl": pnl,
                    "comment": comment
                })

    print(f"[DATA] Found {len(db_trades)} trades in SQLite Journal DB.")
    print(f"[DATA] Found {len(mt5_bot_trades)} matching position records in MT5 Broker History.\n")

    if mt5_bot_trades:
        print("---------------------------------------------------------------------------------------------------------")
        print(f"{'TIMESTAMP (UTC)':<20} | {'TICKET':<10} | {'DIR':<4} | {'ENTRY':<8} | {'EXIT':<8} | {'PNL ($)':<8} | {'COMMENT'}")
        print("---------------------------------------------------------------------------------------------------------")
        total_pnl = 0.0
        wins = 0
        losses = 0

        for t in sorted(mt5_bot_trades, key=lambda x: x["timestamp"]):
            pnl = t["pnl"]
            total_pnl += pnl
            if pnl > 0:
                wins += 1
                status = "[WIN]"
            elif pnl < 0:
                losses += 1
                status = "[LOSS]"
            else:
                status = "[EVEN]"

            print(f"{t['timestamp']:<20} | #{t['ticket']:<9} | {t['direction']:<4} | ${t['entry_price']:<7.2f} | ${t['exit_price']:<7.2f} | ${pnl:<7.2f} | {status} {t['comment']}")

        print("---------------------------------------------------------------------------------------------------------")
        win_rate = (wins / len(mt5_bot_trades)) * 100.0 if mt5_bot_trades else 0.0
        print(f"\n==========================================================================================")
        print("  SUMMARY PERFORMANCE METRICS")
        print("==========================================================================================")
        print(f"Total Bot Trades Recorded: {len(mt5_bot_trades)}")
        print(f"Wins: {wins} | Losses: {losses} | Win Rate: {win_rate:.1f}%")
        print(f"Cumulative Net PnL: ${total_pnl:+.2f}")
        print("==========================================================================================")

if __name__ == "__main__":
    export_all_bot_trades()
