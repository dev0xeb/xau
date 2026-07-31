#!/usr/bin/env python3
"""
audit_live_ensemble_breakdown.py - Live Multi-Strategy Ensemble Performance Audit

Queries MT5 deal history, open positions, and audit files since the Ensemble deployment.
Provides strategy-by-strategy breakdown of STRAT-001 vs STRAT-002.
"""

import sys
import os
sys.path.insert(0, os.path.abspath("."))
import json
import glob
import pandas as pd
from datetime import datetime, timezone, timedelta
import MetaTrader5 as mt5

def audit_live_ensemble():
    print("==========================================================================================")
    print("  LIVE MULTI-STRATEGY ENSEMBLE PERFORMANCE AUDIT (STRAT-001 VS STRAT-002)")
    print("==========================================================================================")

    if not mt5.initialize():
        print("[ERROR] MetaTrader 5 terminal not connected.")
        return

    now_dt = datetime.now(timezone.utc)
    today_start = datetime(now_dt.year, now_dt.month, now_dt.day, 0, 0, 0, tzinfo=timezone.utc)

    # 1. MT5 Deal History Audit (Today)
    deals = mt5.history_deals_get(today_start, now_dt)
    print(f"[DATA] Querying MT5 deal history for today ({today_start.strftime('%Y-%m-%d')} 00:00 UTC to present)...")

    s1_deals = []
    s2_deals = []
    other_deals = []

    if deals is not None and len(deals) > 0:
        deal_records = [d._asdict() for d in deals]
        df_deals = pd.DataFrame(deal_records)
        df_deals["time_dt"] = pd.to_datetime(df_deals["time"], unit="s", utc=True)
        trade_deals = df_deals[df_deals["entry"].isin([0, 1])].copy()

        for idx, r in trade_deals.iterrows():
            comment = str(r.get("comment", ""))
            profit = float(r.get("profit", 0.0))

            if "BOS" in comment:
                s2_deals.append(r)
            elif "FVG" in comment or "CAND-LIVE" in comment:
                s1_deals.append(r)
            else:
                other_deals.append(r)

    print("\n[PART 1: STRATEGY-BY-STRATEGY TODAY BREAKDOWN]")
    
    def print_deal_summary(name, deal_list):
        if not deal_list:
            print(f"[SUMMARY] {name}: 0 Completed Deals Today.")
            return
        df_d = pd.DataFrame(deal_list)
        exits = df_d[df_d["entry"] == 1]
        total_pnl = exits["profit"].sum() if not exits.empty else 0.0
        wins = len(exits[exits["profit"] > 0]) if not exits.empty else 0
        losses = len(exits[exits["profit"] < 0]) if not exits.empty else 0
        wr = (wins / len(exits) * 100.0) if (not exits.empty and len(exits) > 0) else 0.0

        print(f"[SUMMARY] {name}:")
        print(f"   - Total Deal Events: {len(df_d)} | Completed Exits: {len(exits)}")
        print(f"   - Wins: {wins} | Losses: {losses} | Win Rate: {wr:.1f}%")
        print(f"   - Realized PnL: ${total_pnl:+.2f}")

    print_deal_summary("STRAT-001 (M5 FVG Imbalance 3-Burst)", s1_deals)
    print_deal_summary("STRAT-002 (M5 CHOCH/BOS 3-Burst)", s2_deals)

    # 2. MT5 Open Positions Audit Right Now
    positions = mt5.positions_get()
    print("\n[PART 2: CURRENT MT5 OPEN POSITIONS]")
    if positions is None or len(positions) == 0:
        print("  - No active open positions currently in MT5.")
    else:
        print(f"  - Found {len(positions)} active open positions:")
        for p in positions:
            p_type = "BUY" if p.type == 0 else "SELL"
            t_dt = datetime.fromtimestamp(p.time, tz=timezone.utc)
            comment = p.comment
            strat_tag = "STRAT-002 (BOS)" if "BOS" in comment else "STRAT-001 (FVG)"
            print(f"    * Ticket #{p.ticket} [{strat_tag}] | Time: {t_dt.strftime('%H:%M:%S UTC')} | {p_type} {p.volume} lots @ ${p.price_open:.2f} | SL: ${p.sl:.2f} | TP: ${p.tp:.2f} | PnL: ${p.profit:+.2f}")

    # 3. Live Signal Engine Status
    from execution_engine.filters.fvg_filter import M5FairValueGapFilter
    from execution_engine.filters.bos_filter import M5StructureBreakoutFilter

    symbol = "XAUUSDz" if mt5.symbol_info("XAUUSDz") else "XAUUSD"
    fvg_filter = M5FairValueGapFilter(symbol=symbol)
    bos_filter = M5StructureBreakoutFilter(symbol=symbol)

    fvg_s = fvg_filter.check_fvg_status()
    bos_s = bos_filter.check_structure_breakout()

    print("\n[PART 3: LIVE SIGNAL STATUS RIGHT NOW]")
    print(f"  - STRAT-001 (M5 FVG): Active={fvg_s['is_fvg_active']} | Type={fvg_s['fvg_type']} | GapSize=${fvg_s['fvg_gap_size']:.2f}")
    print(f"  - STRAT-002 (M5 CHOCH/BOS): Active={bos_s['active']} | Type={bos_s['bos_type']} | BreakoutPrice=${bos_s['breakout_price']:.2f}")
    print("==========================================================================================")

if __name__ == "__main__":
    audit_live_ensemble()
