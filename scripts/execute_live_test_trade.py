#!/usr/bin/env python3
"""
execute_live_test_trade.py - Execute Live Verification Test Trade on MT5 Terminal

Places a 0.01 lot test BUY deal on the connected broker MT5 terminal (XAUUSDz),
verifies fill confirmation, logs to trade_journal.db, and sends a Telegram notification.
"""

import sys
import os
sys.path.insert(0, os.path.abspath("."))
import uuid
from datetime import datetime, timezone

from execution_engine.adapters.mt5_adapter import MT5Adapter
from execution_engine.audit.trade_journal_db import TradeJournalDatabase
from execution_engine.notifications.telegram_bot import TelegramControlBot

def run_live_test_trade():
    print("======================================================================")
    print("  LIVE MT5 TERMINAL TEST TRADE ROUTER")
    print("======================================================================")

    adapter = MT5Adapter()
    if not adapter.connect():
        print("[ERROR] Could not connect to MetaTrader 5 Terminal.")
        return False

    symbol = adapter.symbol
    print(f"[SUCCESS] Connected to MT5 Terminal. Resolved Symbol: '{symbol}'")

    # Construct test order payload
    cand_id = f"TEST-{uuid.uuid4().hex[:6].upper()}"
    order_payload = {
        "candidate_id": cand_id,
        "direction": "BUY",
        "volume_lots": 0.01,
        "sl": 0.0,
        "tp": 0.0
    }

    # Fetch current quote for accurate SL/TP calculation
    import MetaTrader5 as mt5
    tick_info = mt5.symbol_info_tick(symbol)
    if tick_info:
        entry_price = float(tick_info.ask)
        order_payload["sl"] = round(entry_price - 5.0, 2)
        order_payload["tp"] = round(entry_price + 10.0, 2)
        print(f"[QUOTE] Current Quote: Bid ${tick_info.bid:.2f} | Ask ${tick_info.ask:.2f}")
        print(f"[TARGETS] Calculated Test Target: Entry ${entry_price:.2f} | SL ${order_payload['sl']:.2f} | TP ${order_payload['tp']:.2f}")

    print(f"\n[ROUTING] Routing 0.01 lot BUY order to MT5 for '{symbol}'...")
    res = adapter.place_order(order_payload)

    if res.get("success"):
        ticket = res.get("ticket")
        fill_price = res.get("fill_price")
        print(f"[SUCCESS] Order Executed & Filled! Ticket #{ticket} at ${fill_price:.2f}")

        # Journal trade in SQLite DB
        tj_db = TradeJournalDatabase()
        trade_record = {
            "trade_id": f"TR-{cand_id}",
            "candidate_id": cand_id,
            "symbol": symbol,
            "direction": "BUY",
            "volume_lots": 0.01,
            "entry_price": fill_price,
            "exit_price": fill_price,
            "actual_pnl_usd": 0.0,
            "execution_mode": "LIVE_DEMO",
            "entry_timestamp_utc": datetime.now(timezone.utc).isoformat()
        }
        tj_db.record_journal_trade(trade_record)
        print("  - Logged trade record into trade_journal.db")

        # Send Telegram notification
        bot = TelegramControlBot()
        msg = (
            "🧪 *LIVE TEST TRADE EXECUTED SUCCESSFULLY*\n\n"
            f"Symbol: `{symbol}`\n"
            f"Ticket: `#{ticket}`\n"
            f"Direction: `🟢 BUY 0.01 lots`\n"
            f"Fill Price: `${fill_price:.2f}`\n"
            f"Stop Loss: `${order_payload['sl']:.2f}`\n"
            f"Take Profit: `${order_payload['tp']:.2f}`\n"
            "Status: `FILLED on MT5 Terminal`"
        )
        bot.send_notification("MT5 Execution Verification", msg)
        print("  - Sent confirmation notification to Telegram")
        return True
    else:
        comment = res.get("comment", "Unknown Error")
        retcode = res.get("retcode", 10001)
        print(f"[FAILED] MT5 Order Rejected: {comment} (Retcode: {retcode})")
        return False

if __name__ == "__main__":
    run_live_test_trade()
