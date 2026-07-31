#!/usr/bin/env python3
"""
audit_live_mt5_account_trades_by_bot.py - Deep Multi-Bot MT5 Account Audit

Separates all MT5 deals and active positions today by Magic Number:
- Magic 1001 (xau project: STRAT-001 FVG & STRAT-002 CHOCH/BOS)
- Magic != 1001 (100pipsScalper project)
"""

import sys
import os
import pandas as pd
from datetime import datetime, timezone, timedelta
import MetaTrader5 as mt5

def audit_account_by_bot():
    print("==========================================================================================")
    print("  LIVE MT5 ACCOUNT MULTI-BOT AUDIT (XAU ENGINE VS 100PIPSSCALPER BOT)")
    print("==========================================================================================")

    if not mt5.initialize():
        print("[ERROR] MetaTrader 5 terminal not connected.")
        return

    now_dt = datetime.now(timezone.utc)
    today_start = datetime(now_dt.year, now_dt.month, now_dt.day, 0, 0, 0, tzinfo=timezone.utc)

    # Fetch MT5 account info
    acc = mt5.account_info()
    if acc:
        print(f"[ACCOUNT] Login #{acc.login} | Server: {acc.server} | Balance: ${acc.balance:.2f} | Equity: ${acc.equity:.2f} | Profit: ${acc.profit:+.2f}")

    # Fetch MT5 deal history for today
    deals = mt5.history_deals_get(today_start, now_dt)
    print(f"\n[DATA] Querying MT5 deal history from 00:00 UTC to present ({now_dt.strftime('%H:%M UTC')})...")

    if deals is None or len(deals) == 0:
        print("No MT5 deals recorded today.")
        return

    df_deals = pd.DataFrame([d._asdict() for d in deals])
    df_deals["time_dt"] = pd.to_datetime(df_deals["time"], unit="s", utc=True)
    
    # Filter for exit deals (entry == 1)
    exits = df_deals[df_deals["entry"] == 1].copy()

    xau_exits = exits[exits["magic"] == 1001]
    scalper_exits = exits[exits["magic"] != 1001]

    def print_bot_stats(bot_name, df_e):
        print(f"\n[BOT STATS] {bot_name}:")
        if df_e.empty:
            print("   - 0 Closed Deals Today.")
            return

        total_trades = len(df_e)
        wins = len(df_e[df_e["profit"] > 0])
        losses = len(df_e[df_e["profit"] < 0])
        win_rate = (wins / total_trades) * 100.0 if total_trades > 0 else 0.0
        total_pnl = df_e["profit"].sum()
        gross_win = df_e[df_e["profit"] > 0]["profit"].sum()
        gross_loss = abs(df_e[df_e["profit"] < 0]["profit"].sum())
        pf = round(gross_win / gross_loss, 2) if gross_loss > 0 else 99.0

        print(f"   - Total Closed Deals: {total_trades}")
        print(f"   - Wins: {wins} | Losses: {losses} | Win Rate: {win_rate:.1f}%")
        print(f"   - Profit Factor: {pf}")
        print(f"   - Realized PnL Today: ${total_pnl:+.2f}")

        print("   - Last 5 Closed Deals:")
        for idx, r in df_e.tail(5).iterrows():
            t_str = r['time_dt'].strftime('%H:%M:%S UTC')
            sym = r['symbol']
            vol = r['volume']
            profit = r['profit']
            comment = r['comment']
            print(f"     * [{t_str}] Ticket #{r['ticket']} ({sym} {vol} lots) -> PnL: ${profit:+.2f} | Comment: '{comment}'")

    print_bot_stats("XAU ENGINE (Magic 1001: STRAT-001 & STRAT-002)", xau_exits)
    print_bot_stats("100PIPSSCALPER BOT (Magic != 1001)", scalper_exits)

    # Open Positions Audit
    positions = mt5.positions_get()
    print("\n[PART 2: CURRENT LIVE OPEN POSITIONS IN MT5]")
    if positions is None or len(positions) == 0:
        print("  - No active open positions currently in MT5.")
    else:
        print(f"  - Found {len(positions)} active open positions:")
        for p in positions:
            p_type = "BUY" if p.type == 0 else "SELL"
            t_dt = datetime.fromtimestamp(p.time, tz=timezone.utc)
            bot_tag = "XAU ENGINE (Magic 1001)" if p.magic == 1001 else f"100PIPSSCALPER (Magic {p.magic})"
            print(f"    * Ticket #{p.ticket} [{bot_tag}] | Time: {t_dt.strftime('%H:%M:%S UTC')} | {p.symbol} {p_type} {p.volume} lots @ ${p.price_open:.2f} | SL: ${p.sl:.2f} | TP: ${p.tp:.2f} | PnL: ${p.profit:+.2f}")

    print("==========================================================================================")

if __name__ == "__main__":
    audit_account_by_bot()
