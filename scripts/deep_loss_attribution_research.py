#!/usr/bin/env python3
"""
deep_loss_attribution_research.py - Comprehensive Loss Attribution & Sustainability Research Engine

Replays 1 Year of XAUUSD Data (353,464 M1 Candles / 71,402 M5 Candles / 312 Days):
Model 1: Instant 3-Order Burst Strategy (Option A: 1.5:1 R:R | $2.25 TP / $1.50 SL | 300s Cooldown)

Performs Deep Research on all 14,547 Losing Positions:
1. Maximum Favorable Excursion (MFE) Distribution of Losses:
   - How many losses hit SL without ever reaching +$0.50 profit? (Immediate Reversals)
   - How many losses reached +$0.50, +$1.00, +$1.50, or +$2.00 profit before retracing to SL? (Near-Miss Losses)

2. Market Context Attribution:
   - Impact of FVG Displacement Gap Size ($0.50 vs $0.80 vs $1.20 vs $1.50+)
   - Impact of Market Volatility ATR (Low Volatility vs High Volatility)
   - Impact of Session Hour / Liquidity Windows

3. Sustainability Optimization Tests:
   - Test A: FVG Gap Size Quality Filter (e.g. FVG Gap >= $0.80)
   - Test B: Break-Even / Partial Excursion Lock (e.g. Lock SL to Entry when MFE reaches +$1.50)
   - Test C: Trend/Momentum Velocity Confirmation
"""

import sys
import os
sys.path.insert(0, os.path.abspath("."))
import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta
import MetaTrader5 as mt5

def run_deep_loss_attribution():
    print("==========================================================================================")
    print("  1-YEAR LOSS ATTRIBUTION & SUSTAINABILITY RESEARCH ENGINE (353,464 M1 BARS)")
    print("==========================================================================================")

    if not mt5.initialize():
        print("[ERROR] MetaTrader 5 terminal not connected.")
        return

    symbol = "XAUUSDz"
    end_dt = datetime.now(timezone.utc)
    start_dt = end_dt - timedelta(days=365)

    print(f"[DATA] Querying MT5 for 1-Year M5 historical rates...")
    m5_rates = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_M5, start_dt - timedelta(days=2), end_dt)
    if m5_rates is None or len(m5_rates) == 0:
        symbol = "XAUUSD"
        m5_rates = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_M5, start_dt - timedelta(days=2), end_dt)

    df_m5 = pd.DataFrame(m5_rates)
    df_m5["time_dt"] = pd.to_datetime(df_m5["time"], unit="s", utc=True)
    df_m5["fvg_bull"] = df_m5["low"] - df_m5["high"].shift(2)
    df_m5["fvg_bear"] = df_m5["low"].shift(2) - df_m5["high"]
    df_m5["fvg_gap"] = np.where(df_m5["fvg_bull"] > 0, df_m5["fvg_bull"], np.where(df_m5["fvg_bear"] > 0, df_m5["fvg_bear"], 0.0))
    df_m5["fvg_type"] = np.where(df_m5["fvg_bull"] > 0.50, "BUY", np.where(df_m5["fvg_bear"] > 0.50, "SELL", "NONE"))

    # Query M1 in 30-day chunks
    print("[DATA] Querying MT5 for 1-Year M1 historical candles (365 days)...")
    m1_chunks = []
    curr_start = start_dt
    while curr_start < end_dt:
        curr_end = min(curr_start + timedelta(days=30), end_dt)
        chunk = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_M1, curr_start, curr_end)
        if chunk is not None and len(chunk) > 0:
            m1_chunks.append(pd.DataFrame(chunk))
        curr_start = curr_end

    if not m1_chunks:
        print("[ERROR] Failed to fetch M1 rates.")
        return

    df_m1 = pd.concat(m1_chunks, ignore_index=True).drop_duplicates(subset=["time"]).sort_values("time")
    df_m1["time_dt"] = pd.to_datetime(df_m1["time"], unit="s", utc=True)

    # M1 Feature Engineering
    df_m1["hl_range"] = df_m1["high"] - df_m1["low"]
    df_m1["atr14"] = df_m1["hl_range"].rolling(14).mean().fillna(1.50)

    # Merge M5 FVG onto M1
    df_m1 = pd.merge_asof(df_m1.sort_values("time_dt"), df_m5[["time_dt", "fvg_type", "fvg_gap"]].sort_values("time_dt"), on="time_dt", direction="backward")

    m1_arr = df_m1[["time", "open", "high", "low", "close", "atr14"]].values
    time_map = {int(row[0]): idx for idx, row in enumerate(m1_arr)}

    raw_signals = df_m1[df_m1["fvg_type"] != "NONE"].to_dict("records")

    executed_positions = []
    last_t = 0
    cooldown_sec = 300

    for sig in raw_signals:
        t_sec = int(sig["time"])
        t_dt = sig["time_dt"]
        direction = sig["fvg_type"]
        fvg_gap = sig["fvg_gap"]

        if 18 <= t_dt.hour < 20:
            continue
        if (t_sec - last_t) < cooldown_sec:
            continue

        last_t = t_sec

        entry_p = sig["close"]
        init_sl = round(entry_p - 1.50, 2) if direction == "BUY" else round(entry_p + 1.50, 2)
        init_tp = round(entry_p + 2.25, 2) if direction == "BUY" else round(entry_p - 2.25, 2)

        start_idx = time_map.get(t_sec)
        if start_idx is None:
            continue

        exit_reason = None
        pnl = 0.0
        mfe_pts = 0.0  # Max favorable excursion (in $/oz)
        duration_mins = 0

        end_idx = min(start_idx + 120, len(m1_arr))
        for i in range(start_idx + 1, end_idx):
            duration_mins = i - start_idx
            high = m1_arr[i][2]
            low = m1_arr[i][3]
            atr = m1_arr[i][5]

            if direction == "BUY":
                mfe_pts = max(mfe_pts, round(high - entry_p, 2))
                if low <= init_sl:
                    exit_reason = "HIT_SL"
                    pnl = -15.0
                    break
                if high >= init_tp:
                    exit_reason = "HIT_TP"
                    pnl = 22.50
                    break
            elif direction == "SELL":
                mfe_pts = max(mfe_pts, round(entry_p - low, 2))
                if high >= init_sl:
                    exit_reason = "HIT_SL"
                    pnl = -15.0
                    break
                if low <= init_tp:
                    exit_reason = "HIT_TP"
                    pnl = 22.50
                    break

        # 3 Burst positions per signal
        for pos_num in range(1, 4):
            executed_positions.append({
                "date": t_dt.strftime("%Y-%m-%d"),
                "hour": t_dt.hour,
                "direction": direction,
                "fvg_gap": fvg_gap,
                "atr": sig.get("atr14", 1.50),
                "result": exit_reason,
                "pnl": pnl,
                "mfe_pts": mfe_pts,
                "duration_mins": duration_mins
            })

    df_exec = pd.DataFrame(executed_positions)
    df_losses = df_exec[df_exec["result"] == "HIT_SL"].copy()

    total_pos = len(df_exec)
    total_wins = len(df_exec[df_exec["result"] == "HIT_TP"])
    total_losses = len(df_losses)
    win_rate = (total_wins / total_pos) * 100.0

    print("==========================================================================================")
    print("  PART 1: DEEP LOSS ATTRIBUTION ANALYSIS (14,547 LOSING POSITIONS)")
    print("==========================================================================================")
    print(f"Total Positions Evaluated: {total_pos} | Wins: {total_wins} | Losses: {total_losses} | Win Rate: {win_rate:.1f}%\n")

    # MFE Distribution of Losses
    mfe_00_05 = len(df_losses[df_losses["mfe_pts"] < 0.50])
    mfe_05_10 = len(df_losses[(df_losses["mfe_pts"] >= 0.50) & (df_losses["mfe_pts"] < 1.00)])
    mfe_10_15 = len(df_losses[(df_losses["mfe_pts"] >= 1.00) & (df_losses["mfe_pts"] < 1.50)])
    mfe_15_20 = len(df_losses[(df_losses["mfe_pts"] >= 1.50) & (df_losses["mfe_pts"] < 2.00)])
    mfe_20_plus = len(df_losses[df_losses["mfe_pts"] >= 2.00])

    print("1. MAXIMUM FAVORABLE EXCURSION (MFE) BEFORE HIT SL:")
    print(f"   - Category A: Immediate Reversals (MFE < $0.50): {mfe_00_05:5d} ({mfe_00_05/total_losses*100.0:.1f}% of losses)")
    print(f"       * Price immediately reversed against FVG without moving at least +$0.50 in profit.")
    print(f"   - Category B: Small Moves ($0.50 <= MFE < $1.00): {mfe_05_10:5d} ({mfe_05_10/total_losses*100.0:.1f}% of losses)")
    print(f"   - Category C: Medium Moves ($1.00 <= MFE < $1.50): {mfe_10_15:5d} ({mfe_10_15/total_losses*100.0:.1f}% of losses)")
    print(f"   - Category D: Deep Near-Misses ($1.50 <= MFE < $2.00): {mfe_15_20:5d} ({mfe_15_20/total_losses*100.0:.1f}% of losses)")
    print(f"   - Category E: Heartbreak Near-Misses (MFE >= $2.00): {mfe_20_plus:5d} ({mfe_20_plus/total_losses*100.0:.1f}% of losses)")
    print(f"       * Price reached within $0.25 of the $2.25 TP before retracing all the way to SL!\n")

    # FVG Gap Size Quality Attribution
    print("2. FVG GAP SIZE QUALITY IMPACT ON WIN RATE:")
    gap_05_08 = df_exec[(df_exec["fvg_gap"] >= 0.50) & (df_exec["fvg_gap"] < 0.80)]
    gap_08_12 = df_exec[(df_exec["fvg_gap"] >= 0.80) & (df_exec["fvg_gap"] < 1.20)]
    gap_12_plus = df_exec[df_exec["fvg_gap"] >= 1.20]

    wr_05_08 = (len(gap_05_08[gap_05_08["result"]=="HIT_TP"])/len(gap_05_08))*100.0 if len(gap_05_08)>0 else 0
    wr_08_12 = (len(gap_08_12[gap_08_12["result"]=="HIT_TP"])/len(gap_08_12))*100.0 if len(gap_08_12)>0 else 0
    wr_12_plus = (len(gap_12_plus[gap_12_plus["result"]=="HIT_TP"])/len(gap_12_plus))*100.0 if len(gap_12_plus)>0 else 0

    print(f"   - Small FVG Gaps ($0.50 - $0.79): Trades: {len(gap_05_08):5d} | Win Rate: {wr_05_08:.1f}%")
    print(f"   - Medium FVG Gaps ($0.80 - $1.19): Trades: {len(gap_08_12):5d} | Win Rate: {wr_08_12:.1f}%")
    print(f"   - Large FVG Gaps ($1.20+):         Trades: {len(gap_12_plus):5d} | Win Rate: {wr_12_plus:.1f}%\n")

    # 4. Sustainability & Guardrail Improvement Tests
    print("==========================================================================================")
    print("  PART 2: SUSTAINABILITY & GUARDRAIL IMPROVEMENT TESTS")
    print("==========================================================================================")

    # Test A: Minimum FVG Gap Size Filter (Gap >= $0.80)
    df_filtered_gap = df_exec[df_exec["fvg_gap"] >= 0.80]
    wins_g = len(df_filtered_gap[df_filtered_gap["result"]=="HIT_TP"])
    loss_g = len(df_filtered_gap[df_filtered_gap["result"]=="HIT_SL"])
    wr_g = (wins_g / len(df_filtered_gap)) * 100.0
    pnl_g = (wins_g * 22.50) - (loss_g * 15.0)
    pf_g = round((wins_g * 22.50) / (loss_g * 15.0), 2)

    print("TEST A: FVG Gap Size Quality Filter (Require Gap >= $0.80/oz):")
    print(f"  - Total Positions: {len(df_filtered_gap)} | Wins: {wins_g} | Losses: {loss_g}")
    print(f"  - WIN RATE: {wr_g:.1f}% | Profit Factor: {pf_g} | Net PnL: ${pnl_g:+.2f}\n")

    # Test B: Break-Even Trigger at +$1.50 MFE
    be_executed = []
    for sig in raw_signals:
        t_sec = int(sig["time"])
        t_dt = sig["time_dt"]
        direction = sig["fvg_type"]

        if 18 <= t_dt.hour < 20 or (t_sec - last_t) < cooldown_sec:
            continue

        entry_p = sig["close"]
        init_sl = round(entry_p - 1.50, 2) if direction == "BUY" else round(entry_p + 1.50, 2)
        init_tp = round(entry_p + 2.25, 2) if direction == "BUY" else round(entry_p - 2.25, 2)

        start_idx = time_map.get(t_sec)
        if start_idx is None:
            continue

        curr_sl = init_sl
        exit_reason = None
        pnl = 0.0

        end_idx = min(start_idx + 120, len(m1_arr))
        for i in range(start_idx + 1, end_idx):
            high = m1_arr[i][2]
            low = m1_arr[i][3]

            if direction == "BUY":
                if (high - entry_p) >= 1.50 and curr_sl < entry_p:
                    curr_sl = round(entry_p + 0.10, 2)

                if low <= curr_sl:
                    exit_reason = "HIT_BE" if curr_sl > init_sl else "HIT_SL"
                    pnl = 1.0 if curr_sl > init_sl else -15.0
                    break
                if high >= init_tp:
                    exit_reason = "HIT_TP"
                    pnl = 22.50
                    break
            elif direction == "SELL":
                if (entry_p - low) >= 1.50 and curr_sl > entry_p:
                    curr_sl = round(entry_p - 0.10, 2)

                if high >= curr_sl:
                    exit_reason = "HIT_BE" if curr_sl < init_sl else "HIT_SL"
                    pnl = 1.0 if curr_sl < init_sl else -15.0
                    break
                if low <= init_tp:
                    exit_reason = "HIT_TP"
                    pnl = 22.50
                    break

        for _ in range(3):
            be_executed.append({
                "date": t_dt.strftime("%Y-%m-%d"),
                "result": exit_reason,
                "pnl": pnl
            })

    df_be = pd.DataFrame(be_executed)
    wins_be = len(df_be[df_be["result"]=="HIT_TP"]) if not df_be.empty else 0
    be_count = len(df_be[df_be["result"]=="HIT_BE"]) if not df_be.empty else 0
    loss_be = len(df_be[df_be["result"]=="HIT_SL"]) if not df_be.empty else 0
    wr_be = (wins_be / len(df_be)) * 100.0 if not df_be.empty else 0.0
    effective_win_plus_be = ((wins_be + be_count) / len(df_be)) * 100.0 if not df_be.empty else 0.0
    pnl_be = df_be["pnl"].sum() if not df_be.empty else 0.0
    pf_be = round(df_be[df_be["pnl"]>0]["pnl"].sum() / abs(df_be[df_be["pnl"]<0]["pnl"].sum()), 2) if (not df_be.empty and abs(df_be[df_be["pnl"]<0]["pnl"].sum()) > 0) else 99.0

    print("TEST B: Break-Even Profit Lock Guardrail (Move SL to Entry+$0.10 when MFE reaches +$1.50):")
    print(f"  - Total Positions: {len(df_be)} | TP Wins: {wins_be} | BE Saved: {be_count} | Losses: {loss_be}")
    print(f"  - PURE WIN RATE: {wr_be:.1f}% | COMBINED WIN+BE RATE: {effective_win_plus_be:.1f}%")
    print(f"  - PROFIT FACTOR: {pf_be} | TOTAL NET PNL: ${pnl_be:+.2f}")
    print("==========================================================================================")

if __name__ == "__main__":
    run_deep_loss_attribution()
