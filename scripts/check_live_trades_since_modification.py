#!/usr/bin/env python3
"""
check_live_trades_since_modification.py - Audit Live Trades Since M5 FVG Deployment

Queries MetaTrader 5 deal history and open positions from 17:30 UTC to current time (20:39 UTC).
"""

import sys
import os
sys.path.insert(0, os.path.abspath("."))
import pandas as pd
from datetime import datetime, timezone, timedelta
import MetaTrader5 as mt5

def audit_live_trades():
    print("==========================================================================================")
    print("  LIVE TRADE AUDIT SINCE M5 FVG STRATEGY DEPLOYMENT (17:30 UTC TO PRESENT)")
    print("==========================================================================================")

    if not mt5.initialize():
        print("[ERROR] MetaTrader 5 terminal not connected.")
        return

    now_dt = datetime.now(timezone.utc)
    deploy_dt = datetime(2026, 7, 30, 17, 30, 0, tzinfo=timezone.utc)

    # 1. Fetch Closed Deals since 17:30 UTC
    deals = mt5.history_deals_get(deploy_dt, now_dt)
    print(f"[DATA] Checking deal history between {deploy_dt.strftime('%H:%M:%S UTC')} and {now_dt.strftime('%H:%M:%S UTC')}...")

    if deals is None or len(deals) == 0:
        print("[DEALS] No closed trades found in MT5 deal history since 17:30 UTC.")
    else:
        deal_records = [d._asdict() for d in deals]
        df_deals = pd.DataFrame(deal_records)
        df_deals["time_dt"] = pd.to_datetime(df_deals["time"], unit="s", utc=True)
        # Filter for entry/exit trades (exclude initial balance deposits)
        trade_deals = df_deals[df_deals["entry"].isin([0, 1])].copy()
        
        if trade_deals.empty:
            print("[DEALS] No market order fills found in MT5 deal history since 17:30 UTC.")
        else:
            print(f"[DEALS] Found {len(trade_deals)} trade execution events since 17:30 UTC:\n")
            for idx, r in trade_deals.iterrows():
                deal_type = "BUY" if r["type"] == 0 else "SELL"
                entry_type = "ENTRY" if r["entry"] == 0 else "EXIT"
                print(f"  - Ticket #{r['ticket']} | Time: {r['time_dt'].strftime('%H:%M:%S UTC')} | {entry_type} {deal_type} | Vol: {r['volume']} | Price: ${r['price']:.2f} | Profit: ${r['profit']:+.2f} | Comment: {r['comment']}")

    # 2. Check Open Positions
    positions = mt5.positions_get()
    print("\n[POSITIONS] Checking active open positions in MT5:")
    if positions is None or len(positions) == 0:
        print("  - No active open positions currently in MT5.")
    else:
        print(f"  - Found {len(positions)} active open positions:")
        for p in positions:
            p_type = "BUY" if p.type == 0 else "SELL"
            t_dt = datetime.fromtimestamp(p.time, tz=timezone.utc)
            print(f"    * Ticket #{p.ticket} | Time: {t_dt.strftime('%H:%M:%S UTC')} | {p_type} {p.volume} lots @ ${p.price_open:.2f} | SL: ${p.sl:.2f} | TP: ${p.tp:.2f} | PnL: ${p.profit:+.2f}")

    # 3. Check Current M5 FVG Status
    rates_m5 = mt5.copy_rates_from_pos("XAUUSDz", mt5.TIMEFRAME_M5, 0, 5)
    if rates_m5 is None:
        rates_m5 = mt5.copy_rates_from_pos("XAUUSD", mt5.TIMEFRAME_M5, 0, 5)

    if rates_m5 is not None and len(rates_m5) >= 4:
        df_m5 = pd.DataFrame(rates_m5)
        low1 = df_m5["low"].iloc[-2]
        high3 = df_m5["high"].iloc[-4]
        high1 = df_m5["high"].iloc[-2]
        low3 = df_m5["low"].iloc[-4]

        bull_gap = round(low1 - high3, 2)
        bear_gap = round(low3 - high1, 2)

        print("\n[M5_FVG] Current M5 Market State:")
        print(f"  - Last Completed Candle (bar 1): High ${high1:.2f} | Low ${low1:.2f}")
        print(f"  - Reference Candle (bar 3): High ${high3:.2f} | Low ${low3:.2f}")
        print(f"  - Bullish Gap: ${bull_gap:.2f}/oz (Threshold >= $0.50)")
        print(f"  - Bearish Gap: ${bear_gap:.2f}/oz (Threshold >= $0.50)")

        if bull_gap >= 0.50:
            print(f"  - Status: ACTIVE BULLISH FVG SIGNAL (${bull_gap:.2f} >= $0.50)")
        elif bear_gap >= 0.50:
            print(f"  - Status: ACTIVE BEARISH FVG SIGNAL (${bear_gap:.2f} >= $0.50)")
        else:
            print("  - Status: NO ACTIVE FVG GAPS (> $0.50) AT THIS MINUTE (Consolidation)")

    print("==========================================================================================")

if __name__ == "__main__":
    audit_live_trades()
