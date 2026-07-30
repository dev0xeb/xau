#!/usr/bin/env python3
"""
audit_today_live_performance.py - Audit Today's Live Execution Performance (July 30, 2026)

Queries MT5 deal history for today (July 30, 2026) to diagnose live paper trading performance:
- Total trades taken today
- Wins (+$50 TP) vs Losses (-$20 SL)
- Net PnL incurred today
- Detailed breakdown of each trade entry time, direction, entry price, M15 trend at entry, and exit reason.
"""

import sys
import os
sys.path.insert(0, os.path.abspath("."))
import pandas as pd
from datetime import datetime, timezone, timedelta
import MetaTrader5 as mt5

def audit_today_live():
    print("==========================================================================================")
    print("  LIVE EXECUTION DIAGNOSTIC AUDIT: TODAY'S TRADES (JULY 30, 2026)")
    print("==========================================================================================")

    if not mt5.initialize():
        print("[ERROR] MetaTrader 5 terminal not connected.")
        return

    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    deals = mt5.history_deals_get(today_start, datetime.now(timezone.utc) + timedelta(days=1)) or []

    bot_deals = [d._asdict() for d in deals if (d.magic == 1001 or "CAND-LIVE" in str(d.comment)) and d.entry == 0]

    print(f"[DATA] Retrived {len(bot_deals)} entry deals executed today.\n")

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
            return "FLAT", 0.0, 0.0
        last = sub.iloc[-1]
        t = "UPTREND" if last["ema20"] > last["ema50"] else "DOWNTREND"
        return t, last["ema20"], last["ema50"]

    tp_count = 0
    sl_count = 0
    total_pnl = 0.0

    trade_records = []

    for deal in sorted(bot_deals, key=lambda x: x["time"]):
        pos_id = deal.get("position_id", deal.get("order"))
        entry_p = deal.get("price", 0.0)
        entry_t_sec = deal.get("time", 0)
        entry_dt = datetime.fromtimestamp(entry_t_sec, tz=timezone.utc)
        direction = "BUY" if deal.get("type") == 0 else "SELL"

        trend, ema20, ema50 = get_m15_trend_at(entry_dt)

        # Look up exit deal in history
        pos_deals = [d for d in deals if d.position_id == pos_id and d.entry == 1]
        if pos_deals:
            exit_d = pos_deals[0]
            pnl = exit_d.profit
            if pnl > 0:
                tp_count += 1
                exit_reason = "HIT_TP"
            else:
                sl_count += 1
                exit_reason = "HIT_SL"
            total_pnl += pnl
        else:
            pnl = 0.0
            exit_reason = "OPEN"

        is_trend_aligned = (direction == "BUY" and trend == "UPTREND") or (direction == "SELL" and trend == "DOWNTREND")

        trade_records.append({
            "ticket": pos_id,
            "time": entry_dt.strftime("%H:%M:%S"),
            "dir": direction,
            "entry_p": entry_p,
            "trend": trend,
            "aligned": is_trend_aligned,
            "result": exit_reason,
            "pnl": pnl
        })

    print("==========================================================================================")
    print("  TODAY'S LIVE PERFORMANCE SUMMARY (JULY 30, 2026)")
    print("==========================================================================================")
    print(f"Total Live Trades Executed: {len(trade_records)}")
    print(f"  - Take Profit Hits: {tp_count}")
    print(f"  - Stop Loss Hits: {sl_count}")
    print(f"  - Net Realized PnL: ${total_pnl:+.2f}\n")

    aligned_trades = [r for r in trade_records if r["aligned"]]
    misaligned_trades = [r for r in trade_records if not r["aligned"]]

    print(f"Trend Alignment Breakdown:")
    print(f"  - Trend Aligned Entries: {len(aligned_trades)}")
    print(f"  - Counter-Trend Entries (FLAW/BUG): {len(misaligned_trades)}")
    print("==========================================================================================\n")

    print("Recent 20 Trades Detail:")
    for r in trade_records[-20:]:
        align_str = "ALIGNED" if r["aligned"] else "MISALIGNED (BUG!)"
        print(f"  [{r['time']}] {r['dir']} @ ${r['entry_p']:.2f} | M15 Trend: {r['trend']} ({align_str}) | Result: {r['result']} (${r['pnl']:+.2f})")

if __name__ == "__main__":
    audit_today_live()
