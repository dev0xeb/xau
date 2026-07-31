#!/usr/bin/env python3
"""
audit_live_trades_since_yesterday_modification.py - Detailed Strategy Breakdown Since Modification

Audits all candidate JSON files created in execution_engine/audit/ and MT5 deals
from July 30, 2026 17:30 UTC to current time (July 31, 2026 07:30 UTC).
"""

import sys
import os
sys.path.insert(0, os.path.abspath("."))
import json
import glob
import pandas as pd
from datetime import datetime, timezone, timedelta
import MetaTrader5 as mt5

def audit_trades_since_modification():
    print("==========================================================================================")
    print("  LIVE TRADE BREAKDOWN SINCE STRATEGY MODIFICATION (JULY 30 17:30 UTC TO PRESENT)")
    print("==========================================================================================")

    if not mt5.initialize():
        print("[ERROR] MetaTrader 5 terminal not connected.")
        return

    deploy_dt = datetime(2026, 7, 30, 17, 30, 0, tzinfo=timezone.utc)
    now_dt = datetime.now(timezone.utc)

    # 1. Inspect candidate JSON audit files
    audit_files = glob.glob("execution_engine/audit/audit_CAND-LIVE-*.json")
    print(f"[DATA] Found {len(audit_files)} candidate audit files in execution_engine/audit/...")

    records = []
    for af in audit_files:
        try:
            mtime = os.path.getmtime(af)
            file_dt = datetime.fromtimestamp(mtime, tz=timezone.utc)
            if file_dt < deploy_dt:
                continue

            with open(af, "r") as f:
                data = json.load(f)
                data["file_dt"] = file_dt
                records.append(data)
        except Exception:
            pass

    print(f"[DATA] Found {len(records)} candidate execution records logged since modification (17:30 UTC yesterday).\n")

    # 2. Fetch MT5 Deal History since 17:30 UTC yesterday
    deals = mt5.history_deals_get(deploy_dt, now_dt)
    df_deals = pd.DataFrame()
    if deals is not None and len(deals) > 0:
        deal_records = [d._asdict() for d in deals]
        df_deals = pd.DataFrame(deal_records)
        df_deals["time_dt"] = pd.to_datetime(df_deals["time"], unit="s", utc=True)

    # Strategy Breakdown
    s1_records = []
    s2_records = []

    for r in records:
        strat = str(r.get("strategy_version", ""))
        if "BOS" in strat:
            s2_records.append(r)
        else:
            s1_records.append(r)

    def print_strategy_breakdown(name, record_list):
        print(f"[BREAKDOWN] {name}:")
        if not record_list:
            print("   - No trades executed for this strategy since modification.\n")
            return

        df_rec = pd.DataFrame(record_list)
        df_rec = df_rec.sort_values("file_dt")
        total_pos = len(df_rec)
        buy_pos = len(df_rec[df_rec["direction"] == "BUY"])
        sell_pos = len(df_rec[df_rec["direction"] == "SELL"])

        print(f"   - Total Burst Positions Executed: {total_pos} ({buy_pos} BUY / {sell_pos} SELL)")
        print(f"   - First Execution Time: {df_rec['file_dt'].iloc[0].strftime('%Y-%m-%d %H:%M:%S UTC')}")
        print(f"   - Latest Execution Time: {df_rec['file_dt'].iloc[-1].strftime('%Y-%m-%d %H:%M:%S UTC')}")

        # Match with MT5 Deal History
        matched_deals = []
        if not df_deals.empty:
            for idx, r in df_rec.iterrows():
                cand_id = r.get("candidate_id", "")
                if cand_id:
                    matching = df_deals[df_deals["comment"].str.contains(cand_id, na=False)]
                    if not matching.empty:
                        matched_deals.extend(matching.to_dict("records"))

        if matched_deals:
            df_m = pd.DataFrame(matched_deals).drop_duplicates(subset=["ticket"])
            exits = df_m[df_m["entry"] == 1]
            total_pnl = exits["profit"].sum() if not exits.empty else 0.0
            wins = len(exits[exits["profit"] > 0]) if not exits.empty else 0
            losses = len(exits[exits["profit"] < 0]) if not exits.empty else 0
            wr = (wins / len(exits) * 100.0) if (not exits.empty and len(exits) > 0) else 0.0

            print(f"   - Matched MT5 Closed Deals: {len(exits)} Exits ({wins} Wins / {losses} Losses | Win Rate: {wr:.1f}%)")
            print(f"   - Realized PnL: ${total_pnl:+.2f}")
        else:
            print("   - MT5 Closed Deals: 0 closed deals matched (Positions currently active or pending exit).")

        print("\n   - Recent Trade Executions Log:")
        for idx, r in df_rec.tail(6).iterrows():
            cand_id = r.get("candidate_id", "N/A")
            t_str = r['file_dt'].strftime('%H:%M:%S UTC')
            direction = r.get("direction", "BUY")
            entry_p = float(r.get("entry_target") or 0.0)
            sl_p = float(r.get("sl") or 0.0)
            tp_p = float(r.get("tp") or 0.0)
            print(f"     * [{t_str}] {cand_id} | {direction} @ ${entry_p:.2f} | SL: ${sl_p:.2f} | TP: ${tp_p:.2f}")

        print("\n" + "-" * 90 + "\n")

    print_strategy_breakdown("STRAT-001 (M5 Fair Value Gap Imbalance)", s1_records)
    print_strategy_breakdown("STRAT-002 (M5 CHOCH / BOS Breakout)", s2_records)

    # 3. Check Current Open Positions in MT5 right now
    positions = mt5.positions_get()
    print("[PART 3: CURRENT ACTIVE MT5 OPEN POSITIONS RIGHT NOW]")
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

    print("==========================================================================================")

if __name__ == "__main__":
    audit_trades_since_modification()
