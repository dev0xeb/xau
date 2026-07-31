#!/usr/bin/env python3
"""
audit_live_win_loss_outcomes_strat001_vs_strat002.py - Head-to-Head Win/Loss Audit

Replays all executed live candidate signals logged in decision_snapshots.jsonl
against MT5 M1 price history to determine exact Win/Loss outcomes, Win Rates,
Profit Factors, and Net PnL for STRAT-001 vs STRAT-002.
"""

import sys
import os
import json
import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta
import MetaTrader5 as mt5

def audit_live_win_loss_outcomes():
    print("==========================================================================================")
    print("  HEAD-TO-HEAD LIVE TRADE WIN/LOSS OUTCOME AUDIT (STRAT-001 VS STRAT-002)")
    print("==========================================================================================")

    if not mt5.initialize():
        print("[ERROR] MetaTrader 5 terminal not connected.")
        return

    symbol = "XAUUSDz" if mt5.symbol_info("XAUUSDz") else "XAUUSD"

    log_file = "decision_engine/decision_logs/decision_snapshots.jsonl"
    if not os.path.exists(log_file):
        print(f"[ERROR] Snapshot file '{log_file}' not found.")
        return

    records = []
    with open(log_file, "r") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                data = json.loads(line.strip())
                cand = data.get("candidate_snapshot", data)
                if cand.get("decision") == "EXECUTE" and "BURST" in str(cand.get("strategy_version", "")):
                    records.append(cand)
            except Exception:
                pass

    if not records:
        print("[INFO] No burst strategy executions found in decision log.")
        return

    records_with_ts = []
    for r in records:
        ts_sec = float(r.get("timestamp_sec") or 0.0)
        if ts_sec == 0.0:
            dt_str = r.get("created_at_utc") or r.get("timestamp_utc") or r.get("timestamp")
            if dt_str:
                try:
                    dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
                    ts_sec = dt.timestamp()
                except Exception:
                    pass
        if ts_sec > 1700000000:
            r["ts_sec"] = int(ts_sec)
            records_with_ts.append(r)

    print(f"[DATA] Found {len(records_with_ts)} candidate signals with valid timestamps.\n")

    min_t = min(r["ts_sec"] for r in records_with_ts)
    max_t = max(r["ts_sec"] for r in records_with_ts)

    start_dt = datetime.fromtimestamp(min_t - 300, tz=timezone.utc)
    end_dt = datetime.fromtimestamp(max_t + 7200, tz=timezone.utc)

    print(f"[DATA] Querying MT5 M1 candles from {start_dt.strftime('%Y-%m-%d %H:%M UTC')} to {end_dt.strftime('%Y-%m-%d %H:%M UTC')}...")
    m1_rates = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_M1, start_dt, end_dt)
    if m1_rates is None or len(m1_rates) == 0:
        print("[ERROR] Failed to fetch M1 rates from MT5.")
        return

    df_m1 = pd.DataFrame(m1_rates)
    m1_arr = df_m1[["time", "open", "high", "low", "close"]].values
    time_map = {int(row[0]): idx for idx, row in enumerate(m1_arr)}

    s1_results = []
    s2_results = []

    for r in records_with_ts:
        cand_id = r.get("candidate_id", "N/A")
        strat = r.get("strategy_version", "")
        direction = r.get("direction", "BUY")
        entry_p = float(r.get("entry_target") or 0.0)
        sl_usd = 1.50
        tp_usd = 2.25

        sl_p = round(entry_p - sl_usd, 2) if direction == "BUY" else round(entry_p + sl_usd, 2)
        tp_p = round(entry_p + tp_usd, 2) if direction == "BUY" else round(entry_p - tp_usd, 2)

        t_sec = r["ts_sec"]
        
        # Find closest M1 candle
        start_idx = None
        for offset in range(-60, 60):
            if (t_sec + offset) in time_map:
                start_idx = time_map[t_sec + offset]
                break

        if start_idx is None:
            continue

        outcome = "OPEN"
        pnl = 0.0

        end_idx = min(start_idx + 180, len(m1_arr))
        for i in range(start_idx, end_idx):
            high = m1_arr[i][2]
            low = m1_arr[i][3]

            if direction == "BUY":
                if low <= sl_p:
                    outcome = "HIT_SL"
                    pnl = - (sl_usd * 10.0)
                    break
                if high >= tp_p:
                    outcome = "HIT_TP"
                    pnl = tp_usd * 10.0
                    break
            elif direction == "SELL":
                if high >= sl_p:
                    outcome = "HIT_SL"
                    pnl = - (sl_usd * 10.0)
                    break
                if low <= tp_p:
                    outcome = "HIT_TP"
                    pnl = tp_usd * 10.0
                    break

        item = {
            "candidate_id": cand_id,
            "direction": direction,
            "entry_p": entry_p,
            "outcome": outcome,
            "pnl": pnl
        }

        # 3 Burst Positions per signal
        for _ in range(3):
            if "FVG" in strat:
                s1_results.append(dict(item))
            elif "BOS" in strat:
                s2_results.append(dict(item))

    def evaluate_performance(name, res_list):
        print(f"[OUTCOME AUDIT] {name}:")
        if not res_list:
            print("   - No trades executed.\n")
            return

        df_res = pd.DataFrame(res_list)
        total_pos = len(df_res)
        wins = len(df_res[df_res["outcome"] == "HIT_TP"])
        losses = len(df_res[df_res["outcome"] == "HIT_SL"])
        open_pos = len(df_res[df_res["outcome"] == "OPEN"])

        closed_pos = wins + losses
        win_rate = (wins / closed_pos * 100.0) if closed_pos > 0 else 0.0
        
        gross_win = wins * 22.50
        gross_loss = losses * 15.00
        pf = round(gross_win / gross_loss, 2) if gross_loss > 0 else 99.0
        net_pnl = df_res["pnl"].sum()

        print(f"   - Total Burst Positions Fired: {total_pos} ({total_pos//3} Signals)")
        print(f"   - Completed Exits: {closed_pos} Positions ({wins} Wins / {losses} Losses / {open_pos} Active Open)")
        print(f"   - LIVE WIN RATE: {win_rate:.1f}%")
        print(f"   - LIVE PROFIT FACTOR: {pf}")
        print(f"   - NET REALIZED PNL: ${net_pnl:+.2f}")
        print("\n" + "-" * 90 + "\n")

    evaluate_performance("STRAT-001 (M5 Fair Value Gap Imbalance - STRAT-XAU-FVG-BURST)", s1_results)
    evaluate_performance("STRAT-002 (M5 CHOCH / BOS Breakout - STRAT-XAU-BOS-BURST)", s2_results)

    print("==========================================================================================")

if __name__ == "__main__":
    audit_live_win_loss_outcomes()
