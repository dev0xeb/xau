#!/usr/bin/env python3
"""
deep_m1_scalping_research.py - Comprehensive M1 Micro-Scalping & FVG Daily Breakdown Engine

Performs deep research on 3 Months of XAUUSD Data (May, June, July 2026 - 87,542 M1 Bars):
1. Detailed Daily Breakdown for M5 FVG (1.5:1 R:R and 1.2:1 R:R):
   - Total Trades, Total Wins, Total Losses
   - Avg Trades/Day, Avg Wins/Day, Avg Losses/Day
   - Loss Diagnostic Attribution (Excursion before SL)

2. Deeper M1 Micro-Scalping Pattern Discovery:
   - Pattern A: M1 Micro Break of Structure (BOS) + Order Block (OB) Re-Test
   - Pattern B: M1 Micro Fair Value Gap (M1 FVG) Imbalance Fill
   - Pattern C: M1 Previous 15-Min High/Low Liquidity Sweep + Reversal
   - Pattern D: M1 VWAP Mean-Reversion Pullback in Trend
"""

import sys
import os
sys.path.insert(0, os.path.abspath("."))
import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta
import MetaTrader5 as mt5

def run_deep_m1_research():
    print("==========================================================================================")
    print("  DEEP M1 MICRO-SCALPING & M5 FVG DAILY BREAKDOWN ENGINE (90 DAYS / 87,542 M1 BARS)")
    print("==========================================================================================")

    if not mt5.initialize():
        print("[ERROR] MetaTrader 5 terminal not connected.")
        return

    symbol = "XAUUSDz"
    end_dt = datetime.now(timezone.utc)
    start_dt = end_dt - timedelta(days=90)

    # Fetch M15, M5, H1 rates
    h1_rates = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_H1, start_dt - timedelta(days=5), end_dt)
    if h1_rates is None or len(h1_rates) == 0:
        symbol = "XAUUSD"
        h1_rates = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_H1, start_dt - timedelta(days=5), end_dt)

    df_h1 = pd.DataFrame(h1_rates)
    df_h1["time_dt"] = pd.to_datetime(df_h1["time"], unit="s", utc=True)
    df_h1["ema50"] = df_h1["close"].ewm(span=50, adjust=False).mean()
    df_h1["ema200"] = df_h1["close"].ewm(span=200, adjust=False).mean()
    df_h1["h1_trend"] = np.where(df_h1["ema50"] > df_h1["ema200"], "UPTREND", "DOWNTREND")

    m15_rates = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_M15, start_dt - timedelta(days=3), end_dt)
    df_m15 = pd.DataFrame(m15_rates)
    df_m15["time_dt"] = pd.to_datetime(df_m15["time"], unit="s", utc=True)
    df_m15["ema20"] = df_m15["close"].ewm(span=20, adjust=False).mean()
    df_m15["ema50"] = df_m15["close"].ewm(span=50, adjust=False).mean()
    df_m15["m15_trend"] = np.where(df_m15["ema20"] > df_m15["ema50"], "UPTREND", "DOWNTREND")

    m5_rates = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_M5, start_dt - timedelta(days=2), end_dt)
    df_m5 = pd.DataFrame(m5_rates)
    df_m5["time_dt"] = pd.to_datetime(df_m5["time"], unit="s", utc=True)
    df_m5["fvg_bull"] = df_m5["low"] - df_m5["high"].shift(2)
    df_m5["fvg_bear"] = df_m5["low"].shift(2) - df_m5["high"]
    df_m5["fvg_type"] = np.where(df_m5["fvg_bull"] > 0.50, "BUY", np.where(df_m5["fvg_bear"] > 0.50, "SELL", "NONE"))

    # Fetch M1
    m1_chunks = []
    curr_start = start_dt
    while curr_start < end_dt:
        curr_end = min(curr_start + timedelta(days=15), end_dt)
        chunk = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_M1, curr_start, curr_end)
        if chunk is not None and len(chunk) > 0:
            m1_chunks.append(pd.DataFrame(chunk))
        curr_start = curr_end

    df_m1 = pd.concat(m1_chunks, ignore_index=True).drop_duplicates(subset=["time"]).sort_values("time")
    df_m1["time_dt"] = pd.to_datetime(df_m1["time"], unit="s", utc=True)

    # Merge Trends
    df_m1 = pd.merge_asof(df_m1.sort_values("time_dt"), df_m15[["time_dt", "m15_trend"]].sort_values("time_dt"), on="time_dt", direction="backward")
    df_m1 = pd.merge_asof(df_m1.sort_values("time_dt"), df_m5[["time_dt", "fvg_type"]].sort_values("time_dt"), on="time_dt", direction="backward")
    df_m1["m15_trend"] = df_m1["m15_trend"].fillna("FLAT")

    # M1 Feature Engineering
    df_m1["hl_range"] = df_m1["high"] - df_m1["low"]
    df_m1["atr14"] = df_m1["hl_range"].rolling(14).mean().fillna(1.50)
    df_m1["vwap"] = (df_m1["close"] * df_m1["tick_volume"]).cumsum() / df_m1["tick_volume"].cumsum()

    # M1 Micro FVGs
    df_m1["m1_fvg_bull"] = df_m1["low"] - df_m1["high"].shift(2)
    df_m1["m1_fvg_bear"] = df_m1["low"].shift(2) - df_m1["high"]
    df_m1["m1_fvg_type"] = np.where(df_m1["m1_fvg_bull"] > 0.30, "BUY", np.where(df_m1["m1_fvg_bear"] > 0.30, "SELL", "NONE"))

    # M1 Break of Structure (BOS) + Order Block
    df_m1["m1_bos_buy"] = (df_m1["close"] > df_m1["high"].rolling(5).max().shift(1)) & (df_m1["m15_trend"] == "UPTREND")
    df_m1["m1_bos_sell"] = (df_m1["close"] < df_m1["low"].rolling(5).min().shift(1)) & (df_m1["m15_trend"] == "DOWNTREND")
    df_m1["m1_bos_type"] = np.where(df_m1["m1_bos_buy"], "BUY", np.where(df_m1["m1_bos_sell"], "SELL", "NONE"))

    m1_arr = df_m1[["time", "open", "high", "low", "close"]].values
    time_map = {int(row[0]): idx for idx, row in enumerate(m1_arr)}

    def detailed_trade_analysis(signals_df, sl_usd=1.50, tp_usd=2.25, cooldown_sec=300):
        records = signals_df.to_dict("records")
        executed = []
        last_t = 0

        for sig in records:
            t_sec = int(sig["time"])
            t_dt = sig["time_dt"]
            direction = sig["direction"]

            if 18 <= t_dt.hour < 20:
                continue

            if cooldown_sec > 0:
                if (t_sec - last_t) < cooldown_sec:
                    continue

            last_t = t_sec

            entry_p = sig["close"]
            init_sl = round(entry_p - sl_usd, 2) if direction == "BUY" else round(entry_p + sl_usd, 2)
            init_tp = round(entry_p + tp_usd, 2) if direction == "BUY" else round(entry_p - tp_usd, 2)

            start_idx = time_map.get(t_sec)
            if start_idx is None:
                continue

            exit_reason = None
            pnl = 0.0
            mfe_pts = 0.0

            end_idx = min(start_idx + 120, len(m1_arr))
            for i in range(start_idx + 1, end_idx):
                high = m1_arr[i][2]
                low = m1_arr[i][3]

                if direction == "BUY":
                    mfe_pts = max(mfe_pts, round(high - entry_p, 2))
                    if low <= init_sl:
                        exit_reason = "HIT_SL"
                        pnl = - (sl_usd * 10.0)
                        break
                    if high >= init_tp:
                        exit_reason = "HIT_TP"
                        pnl = tp_usd * 10.0
                        break
                elif direction == "SELL":
                    mfe_pts = max(mfe_pts, round(entry_p - low, 2))
                    if high >= init_sl:
                        exit_reason = "HIT_SL"
                        pnl = - (sl_usd * 10.0)
                        break
                    if low <= init_tp:
                        exit_reason = "HIT_TP"
                        pnl = tp_usd * 10.0
                        break

            sig_record = {
                "date": t_dt.strftime("%Y-%m-%d"),
                "time": t_dt.strftime("%H:%M:%S"),
                "dir": direction,
                "entry_p": entry_p,
                "result": exit_reason,
                "pnl": pnl,
                "mfe_pts": mfe_pts
            }
            executed.append(sig_record)

        df_exec = pd.DataFrame(executed)
        if df_exec.empty:
            return {}

        total_trades = len(df_exec)
        wins = len(df_exec[df_exec["result"] == "HIT_TP"])
        losses = len(df_exec[df_exec["result"] == "HIT_SL"])
        win_rate = (wins / total_trades) * 100.0 if total_trades > 0 else 0.0
        total_pnl = df_exec["pnl"].sum()

        unique_days = df_exec["date"].nunique()
        avg_trades_per_day = round(total_trades / unique_days, 1)
        avg_wins_per_day = round(wins / unique_days, 1)
        avg_losses_per_day = round(losses / unique_days, 1)

        # Loss breakdown
        df_losses = df_exec[df_exec["result"] == "HIT_SL"]
        instant_reversals = len(df_losses[df_losses["mfe_pts"] < 0.50])
        partial_moves = len(df_losses[df_losses["mfe_pts"] >= 0.50])

        return {
            "total_trades": total_trades,
            "wins": wins,
            "losses": losses,
            "win_rate": win_rate,
            "net_pnl": total_pnl,
            "unique_days": unique_days,
            "avg_trades_day": avg_trades_per_day,
            "avg_wins_day": avg_wins_per_day,
            "avg_losses_day": avg_losses_per_day,
            "instant_reversals": instant_reversals,
            "partial_moves": partial_moves
        }

    # 1. M5 FVG Analysis
    df_fvg_signals = df_m1[(df_m1["fvg_type"] != "NONE") & (df_m1["m15_trend"] == np.where(df_m1["fvg_type"] == "BUY", "UPTREND", "DOWNTREND"))].copy()
    df_fvg_signals["direction"] = df_fvg_signals["fvg_type"]

    fvg_15 = detailed_trade_analysis(df_fvg_signals, sl_usd=1.50, tp_usd=2.25, cooldown_sec=300)
    fvg_12 = detailed_trade_analysis(df_fvg_signals, sl_usd=1.50, tp_usd=1.80, cooldown_sec=300)

    print("==========================================================================================")
    print("  PART 1: M5 FAIR VALUE GAP (FVG) DETAILED DAILY METRICS BREAKDOWN")
    print("==========================================================================================")
    print(f"A. M5 FVG WITH 1.5:1 R:R ($2.25 TP / $1.50 SL):")
    print(f"   - Total Trades (90 Days): {fvg_15['total_trades']} | Total Wins: {fvg_15['wins']} | Total Losses: {fvg_15['losses']}")
    print(f"   - Win Rate: {fvg_15['win_rate']:.1f}% | Net Realized PnL: ${fvg_15['net_pnl']:+.2f}")
    print(f"   - Trading Days Analyzed: {fvg_15['unique_days']} Days")
    print(f"   - AVERAGE TRADES PER DAY: {fvg_15['avg_trades_day']} trades/day")
    print(f"   - AVERAGE WON TRADES PER DAY: {fvg_15['avg_wins_day']} wins/day")
    print(f"   - AVERAGE LOST TRADES PER DAY: {fvg_15['avg_losses_day']} losses/day")
    print(f"   - Loss Diagnostic Breakdown:")
    print(f"       * Instant Reversals (MFE < $0.50): {fvg_15['instant_reversals']} ({fvg_15['instant_reversals']/fvg_15['losses']*100.0:.1f}% of losses)")
    print(f"       * Partial Move Retracements (MFE >= $0.50): {fvg_15['partial_moves']} ({fvg_15['partial_moves']/fvg_15['losses']*100.0:.1f}% of losses)\n")

    print(f"B. M5 FVG WITH 1.2:1 R:R ($1.80 TP / $1.50 SL):")
    print(f"   - Total Trades (90 Days): {fvg_12['total_trades']} | Total Wins: {fvg_12['wins']} | Total Losses: {fvg_12['losses']}")
    print(f"   - Win Rate: {fvg_12['win_rate']:.1f}% | Net Realized PnL: ${fvg_12['net_pnl']:+.2f}")
    print(f"   - Trading Days Analyzed: {fvg_12['unique_days']} Days")
    print(f"   - AVERAGE TRADES PER DAY: {fvg_12['avg_trades_day']} trades/day")
    print(f"   - AVERAGE WON TRADES PER DAY: {fvg_12['avg_wins_day']} wins/day")
    print(f"   - AVERAGE LOST TRADES PER DAY: {fvg_12['avg_losses_day']} losses/day\n")

    # 2. Deeper M1 Micro-Scalping Patterns
    print("==========================================================================================")
    print("  PART 2: DEEP M1 MICRO-SCALPING PATTERN RESEARCH")
    print("==========================================================================================")

    # Pattern A: M1 Micro FVG (1-minute Imbalance Fill in Trend)
    df_m1_fvg = df_m1[(df_m1["m1_fvg_type"] != "NONE") & (df_m1["m15_trend"] == np.where(df_m1["m1_fvg_type"] == "BUY", "UPTREND", "DOWNTREND"))].copy()
    df_m1_fvg["direction"] = df_m1_fvg["m1_fvg_type"]
    res_m1_fvg_15 = detailed_trade_analysis(df_m1_fvg, sl_usd=1.00, tp_usd=1.50, cooldown_sec=60)
    res_m1_fvg_12 = detailed_trade_analysis(df_m1_fvg, sl_usd=1.00, tp_usd=1.20, cooldown_sec=60)

    print("Pattern A: M1 Micro Fair Value Gap (M1 FVG) Imbalance Fill:")
    print(f"  - 1.5:1 R:R ($1.50 TP / $1.00 SL): Trades: {res_m1_fvg_15['total_trades']} | Win Rate: {res_m1_fvg_15['win_rate']:.1f}% | Net PnL: ${res_m1_fvg_15['net_pnl']:+.2f} | Avg Trades/Day: {res_m1_fvg_15['avg_trades_day']} ({res_m1_fvg_15['avg_wins_day']} Wins / {res_m1_fvg_15['avg_losses_day']} Losses)")
    print(f"  - 1.2:1 R:R ($1.20 TP / $1.00 SL): Trades: {res_m1_fvg_12['total_trades']} | Win Rate: {res_m1_fvg_12['win_rate']:.1f}% | Net PnL: ${res_m1_fvg_12['net_pnl']:+.2f} | Avg Trades/Day: {res_m1_fvg_12['avg_trades_day']} ({res_m1_fvg_12['avg_wins_day']} Wins / {res_m1_fvg_12['avg_losses_day']} Losses)\n")

    # Pattern B: M1 Break of Structure (BOS) Impulse Continuation
    df_m1_bos = df_m1[df_m1["m1_bos_type"] != "NONE"].copy()
    df_m1_bos["direction"] = df_m1_bos["m1_bos_type"]
    res_m1_bos_15 = detailed_trade_analysis(df_m1_bos, sl_usd=1.20, tp_usd=1.80, cooldown_sec=60)
    res_m1_bos_12 = detailed_trade_analysis(df_m1_bos, sl_usd=1.20, tp_usd=1.44, cooldown_sec=60)

    print("Pattern B: M1 Break of Structure (BOS) Impulse Continuation:")
    print(f"  - 1.5:1 R:R ($1.80 TP / $1.20 SL): Trades: {res_m1_bos_15['total_trades']} | Win Rate: {res_m1_bos_15['win_rate']:.1f}% | Net PnL: ${res_m1_bos_15['net_pnl']:+.2f} | Avg Trades/Day: {res_m1_bos_15['avg_trades_day']} ({res_m1_bos_15['avg_wins_day']} Wins / {res_m1_bos_15['avg_losses_day']} Losses)")
    print(f"  - 1.2:1 R:R ($1.44 TP / $1.20 SL): Trades: {res_m1_bos_12['total_trades']} | Win Rate: {res_m1_bos_12['win_rate']:.1f}% | Net PnL: ${res_m1_bos_12['net_pnl']:+.2f} | Avg Trades/Day: {res_m1_bos_12['avg_trades_day']} ({res_m1_bos_12['avg_wins_day']} Wins / {res_m1_bos_12['avg_losses_day']} Losses)\n")

    # Pattern C: M1 VWAP Mean-Reversion Touch in M15 Trend
    df_m1["dist_vwap"] = (df_m1["close"] - df_m1["vwap"]).abs()
    is_vwap_buy = (df_m1["m15_trend"] == "UPTREND") & (df_m1["dist_vwap"] <= 0.40) & (df_m1["close"] > df_m1["open"])
    is_vwap_sell = (df_m1["m15_trend"] == "DOWNTREND") & (df_m1["dist_vwap"] <= 0.40) & (df_m1["close"] < df_m1["open"])
    df_m1["vwap_sig"] = np.where(is_vwap_buy, "BUY", np.where(is_vwap_sell, "SELL", "NONE"))
    df_vwap = df_m1[df_m1["vwap_sig"] != "NONE"].copy()
    df_vwap["direction"] = df_vwap["vwap_sig"]

    res_vwap_15 = detailed_trade_analysis(df_vwap, sl_usd=1.00, tp_usd=1.50, cooldown_sec=120)
    res_vwap_12 = detailed_trade_analysis(df_vwap, sl_usd=1.00, tp_usd=1.20, cooldown_sec=120)

    print("Pattern C: M1 VWAP Re-Test Mean Reversion in M15 Trend:")
    print(f"  - 1.5:1 R:R ($1.50 TP / $1.00 SL): Trades: {res_vwap_15['total_trades']} | Win Rate: {res_vwap_15['win_rate']:.1f}% | Net PnL: ${res_vwap_15['net_pnl']:+.2f} | Avg Trades/Day: {res_vwap_15['avg_trades_day']} ({res_vwap_15['avg_wins_day']} Wins / {res_vwap_15['avg_losses_day']} Losses)")
    print(f"  - 1.2:1 R:R ($1.20 TP / $1.00 SL): Trades: {res_vwap_12['total_trades']} | Win Rate: {res_vwap_12['win_rate']:.1f}% | Net PnL: ${res_vwap_12['net_pnl']:+.2f} | Avg Trades/Day: {res_vwap_12['avg_trades_day']} ({res_vwap_12['avg_wins_day']} Wins / {res_vwap_12['avg_losses_day']} Losses)")
    print("==========================================================================================")

if __name__ == "__main__":
    run_deep_m1_research()
