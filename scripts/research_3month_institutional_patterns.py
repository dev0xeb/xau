#!/usr/bin/env python3
"""
research_3month_institutional_patterns.py - Deep 3-Month Quantitative Pattern & Edge Discovery Engine

Analyzes 90 Days of XAUUSD Data (May, June, July 2026) across M1, M5, M15, and H1 timeframes.
Target Goal: Achieve a mathematically verified > 50% Win Rate with positive expectancy.

Tests 5 Quantitative Hypotheses:
  1. H1 + M15 + M5 Triple Timeframe Alignment
  2. Asian Session Liquidity Sweep & London/NY Reversal
  3. M5 Fair Value Gap (FVG) / Imbalance Fill Entries
  4. Bollinger Band Squeeze & Volatility Expansion
  5. Optimized Risk Ratios (1:1, 1.2:1, 1.5:1, 2:1) for Win-Rate Optimization
"""

import sys
import os
sys.path.insert(0, os.path.abspath("."))
import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta
import MetaTrader5 as mt5

def run_3month_pattern_research():
    print("==========================================================================================")
    print("  DEEP QUANTITATIVE RESEARCH ENGINE: 3-MONTH INSTITUTIONAL PATTERN DISCOVERY")
    print("  Target Goal: Discover structural setups yielding >= 50% Win Rate on XAUUSD")
    print("==========================================================================================")

    if not mt5.initialize():
        print("[ERROR] MetaTrader 5 terminal not connected.")
        return

    symbol = "XAUUSDz"
    end_dt = datetime.now(timezone.utc)
    start_dt = end_dt - timedelta(days=90)

    print(f"[DATA] Fetching 90 days of M1, M5, M15, and H1 data ({start_dt.strftime('%Y-%m-%d')} to {end_dt.strftime('%Y-%m-%d')})...")

    # Query H1
    h1_rates = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_H1, start_dt - timedelta(days=5), end_dt)
    if h1_rates is None or len(h1_rates) == 0:
        symbol = "XAUUSD"
        h1_rates = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_H1, start_dt - timedelta(days=5), end_dt)

    df_h1 = pd.DataFrame(h1_rates)
    df_h1["time_dt"] = pd.to_datetime(df_h1["time"], unit="s", utc=True)
    df_h1["ema50"] = df_h1["close"].ewm(span=50, adjust=False).mean()
    df_h1["ema200"] = df_h1["close"].ewm(span=200, adjust=False).mean()
    df_h1["h1_trend"] = np.where(df_h1["ema50"] > df_h1["ema200"], "UPTREND", "DOWNTREND")

    # Query M15
    m15_rates = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_M15, start_dt - timedelta(days=3), end_dt)
    df_m15 = pd.DataFrame(m15_rates)
    df_m15["time_dt"] = pd.to_datetime(df_m15["time"], unit="s", utc=True)
    df_m15["ema20"] = df_m15["close"].ewm(span=20, adjust=False).mean()
    df_m15["ema50"] = df_m15["close"].ewm(span=50, adjust=False).mean()
    df_m15["m15_trend"] = np.where(df_m15["ema20"] > df_m15["ema50"], "UPTREND", "DOWNTREND")

    # Query M5
    m5_rates = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_M5, start_dt - timedelta(days=2), end_dt)
    df_m5 = pd.DataFrame(m5_rates)
    df_m5["time_dt"] = pd.to_datetime(df_m5["time"], unit="s", utc=True)
    df_m5["ema10"] = df_m5["close"].ewm(span=10, adjust=False).mean()
    df_m5["ema30"] = df_m5["close"].ewm(span=30, adjust=False).mean()
    df_m5["m5_trend"] = np.where(df_m5["ema10"] > df_m5["ema30"], "UPTREND", "DOWNTREND")

    # Query M1 in 15-day chunks
    print("[DATA] Fetching M1 1-minute historical candles...")
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

    print(f"[DATA] Successfully loaded {len(df_m1)} M1 bars, {len(df_m5)} M5 bars, {len(df_m15)} M15 bars, and {len(df_h1)} H1 bars.\n")

    # Merge Trends onto M1
    df_m1 = pd.merge_asof(df_m1.sort_values("time_dt"), df_h1[["time_dt", "h1_trend"]].sort_values("time_dt"), on="time_dt", direction="backward")
    df_m1 = pd.merge_asof(df_m1.sort_values("time_dt"), df_m15[["time_dt", "m15_trend"]].sort_values("time_dt"), on="time_dt", direction="backward")
    df_m1 = pd.merge_asof(df_m1.sort_values("time_dt"), df_m5[["time_dt", "m5_trend"]].sort_values("time_dt"), on="time_dt", direction="backward")

    df_m1["h1_trend"] = df_m1["h1_trend"].fillna("FLAT")
    df_m1["m15_trend"] = df_m1["m15_trend"].fillna("FLAT")
    df_m1["m5_trend"] = df_m1["m5_trend"].fillna("FLAT")

    # Compute Feature Vectors on M1
    df_m1["hl_range"] = df_m1["high"] - df_m1["low"]
    df_m1["atr14"] = df_m1["hl_range"].rolling(14).mean().fillna(1.50)
    df_m1["mom_vel"] = df_m1["close"].diff(3).fillna(0.0)
    df_m1["comp_ratio"] = (df_m1["hl_range"] / df_m1["hl_range"].rolling(10).mean()).fillna(1.0)

    # Fast Replay Engine
    m1_arr = df_m1[["time", "open", "high", "low", "close"]].values
    time_map = {int(row[0]): idx for idx, row in enumerate(m1_arr)}

    def evaluate_setup(signals_df, sl_usd=2.00, tp_usd=5.00, cooldown_sec=15):
        records = signals_df.to_dict("records")
        tp_count = 0
        sl_count = 0
        total_pnl = 0.0
        last_t = 0
        executed = []

        for sig in records:
            t_sec = int(sig["time"])
            t_dt = sig["time_dt"]
            direction = sig["direction"]

            # Exclude news / FOMC hours (18:00 - 20:00 UTC)
            if 18 <= t_dt.hour < 20:
                continue

            if cooldown_sec > 0:
                if (t_sec - last_t) < cooldown_sec:
                    continue

            last_t = t_sec
            executed.append(sig)

            entry_p = sig["close"]
            init_sl = round(entry_p - sl_usd, 2) if direction == "BUY" else round(entry_p + sl_usd, 2)
            init_tp = round(entry_p + tp_usd, 2) if direction == "BUY" else round(entry_p - tp_usd, 2)

            start_idx = time_map.get(t_sec)
            if start_idx is None:
                continue

            exit_reason = None
            pnl = 0.0

            end_idx = min(start_idx + 120, len(m1_arr))
            for i in range(start_idx + 1, end_idx):
                high = m1_arr[i][2]
                low = m1_arr[i][3]

                if direction == "BUY":
                    if low <= init_sl:
                        exit_reason = "HIT_SL"
                        pnl = - (sl_usd * 10.0)
                        break
                    if high >= init_tp:
                        exit_reason = "HIT_TP"
                        pnl = tp_usd * 10.0
                        break
                elif direction == "SELL":
                    if high >= init_sl:
                        exit_reason = "HIT_SL"
                        pnl = - (sl_usd * 10.0)
                        break
                    if low <= init_tp:
                        exit_reason = "HIT_TP"
                        pnl = tp_usd * 10.0
                        break

            if exit_reason == "HIT_TP":
                tp_count += 1
            elif exit_reason == "HIT_SL":
                sl_count += 1

            total_pnl += pnl

        total_trades = len(executed)
        win_rate = (tp_count / total_trades) * 100.0 if total_trades > 0 else 0.0
        gross_profit = tp_count * (tp_usd * 10.0)
        gross_loss = sl_count * (sl_usd * 10.0)
        pf = round(gross_profit / gross_loss, 2) if gross_loss > 0 else 99.0

        return {
            "total_trades": total_trades,
            "tp": tp_count,
            "sl": sl_count,
            "win_rate": win_rate,
            "profit_factor": pf,
            "net_pnl": total_pnl
        }

    print("==========================================================================================")
    print("  RESEARCH HYPOTHESIS 1: MULTI-TIMEFRAME TRIPLE CONFLUENCE (H1 + M15 + M5 AGREE)")
    print("==========================================================================================")
    # Filter: BUY when H1, M15, and M5 are ALL in UPTREND; SELL when ALL are in DOWNTREND
    df_m1["triple_aligned"] = np.where(
        (df_m1["h1_trend"] == "UPTREND") & (df_m1["m15_trend"] == "UPTREND") & (df_m1["m5_trend"] == "UPTREND"), "BUY",
        np.where((df_m1["h1_trend"] == "DOWNTREND") & (df_m1["m15_trend"] == "DOWNTREND") & (df_m1["m5_trend"] == "DOWNTREND"), "SELL", "NONE")
    )

    df_h1_signals = df_m1[(df_m1["triple_aligned"] != "NONE") & (df_m1["mom_vel"].abs() > 0.8)].copy()
    df_h1_signals["direction"] = df_h1_signals["triple_aligned"]

    r_h1_25 = evaluate_setup(df_h1_signals, sl_usd=2.00, tp_usd=5.00, cooldown_sec=60)
    r_h1_15 = evaluate_setup(df_h1_signals, sl_usd=2.00, tp_usd=3.00, cooldown_sec=60)
    r_h1_12 = evaluate_setup(df_h1_signals, sl_usd=2.00, tp_usd=2.40, cooldown_sec=60)
    r_h1_10 = evaluate_setup(df_h1_signals, sl_usd=2.00, tp_usd=2.00, cooldown_sec=60)

    print(f"  - 2.5:1 R:R ($5.00 TP / $2.00 SL): Trades: {r_h1_25['total_trades']:4d} | Win Rate: {r_h1_25['win_rate']:.1f}% | PF: {r_h1_25['profit_factor']} | Net PnL: ${r_h1_25['net_pnl']:+.2f}")
    print(f"  - 1.5:1 R:R ($3.00 TP / $2.00 SL): Trades: {r_h1_15['total_trades']:4d} | Win Rate: {r_h1_15['win_rate']:.1f}% | PF: {r_h1_15['profit_factor']} | Net PnL: ${r_h1_15['net_pnl']:+.2f}")
    print(f"  - 1.2:1 R:R ($2.40 TP / $2.00 SL): Trades: {r_h1_12['total_trades']:4d} | Win Rate: {r_h1_12['win_rate']:.1f}% | PF: {r_h1_12['profit_factor']} | Net PnL: ${r_h1_12['net_pnl']:+.2f}")
    print(f"  - 1.0:1 R:R ($2.00 TP / $2.00 SL): Trades: {r_h1_10['total_trades']:4d} | Win Rate: {r_h1_10['win_rate']:.1f}% | PF: {r_h1_10['profit_factor']} | Net PnL: ${r_h1_10['net_pnl']:+.2f}\n")

    print("==========================================================================================")
    print("  RESEARCH HYPOTHESIS 2: ASIAN RANGE LIQUIDITY SWEEP & LONDON/NY REVERSAL")
    print("==========================================================================================")
    # Asian Session (00:00 - 06:00 UTC) High/Low Sweep during London (07:00-11:00 UTC) / NY (13:00-17:00 UTC)
    df_m1["hour"] = df_m1["time_dt"].dt.hour
    asian_df = df_m1[(df_m1["hour"] >= 0) & (df_m1["hour"] < 6)]
    asian_highs = asian_df.groupby(df_m1["time_dt"].dt.date)["high"].max()
    asian_lows = asian_df.groupby(df_m1["time_dt"].dt.date)["low"].min()

    df_m1["date"] = df_m1["time_dt"].dt.date
    df_m1["asian_high"] = df_m1["date"].map(asian_highs)
    df_m1["asian_low"] = df_m1["date"].map(asian_lows)

    # Sweep Buy Signal: London/NY price sweeps below Asian Low then closes above Asian Low (Reversal)
    # Sweep Sell Signal: London/NY price sweeps above Asian High then closes below Asian High (Reversal)
    is_sweep_buy = (df_m1["hour"].isin([7, 8, 9, 10, 13, 14, 15, 16])) & (df_m1["low"] < df_m1["asian_low"]) & (df_m1["close"] > df_m1["asian_low"])
    is_sweep_sell = (df_m1["hour"].isin([7, 8, 9, 10, 13, 14, 15, 16])) & (df_m1["high"] > df_m1["asian_high"]) & (df_m1["close"] < df_m1["asian_high"])

    df_m1["sweep_signal"] = np.where(is_sweep_buy, "BUY", np.where(is_sweep_sell, "SELL", "NONE"))
    df_sweep = df_m1[df_m1["sweep_signal"] != "NONE"].copy()
    df_sweep["direction"] = df_sweep["sweep_signal"]

    r_sw_25 = evaluate_setup(df_sweep, sl_usd=2.00, tp_usd=5.00, cooldown_sec=120)
    r_sw_15 = evaluate_setup(df_sweep, sl_usd=2.00, tp_usd=3.00, cooldown_sec=120)
    r_sw_12 = evaluate_setup(df_sweep, sl_usd=2.00, tp_usd=2.40, cooldown_sec=120)
    r_sw_10 = evaluate_setup(df_sweep, sl_usd=2.00, tp_usd=2.00, cooldown_sec=120)

    print(f"  - 2.5:1 R:R ($5.00 TP / $2.00 SL): Trades: {r_sw_25['total_trades']:4d} | Win Rate: {r_sw_25['win_rate']:.1f}% | PF: {r_sw_25['profit_factor']} | Net PnL: ${r_sw_25['net_pnl']:+.2f}")
    print(f"  - 1.5:1 R:R ($3.00 TP / $2.00 SL): Trades: {r_sw_15['total_trades']:4d} | Win Rate: {r_sw_15['win_rate']:.1f}% | PF: {r_sw_15['profit_factor']} | Net PnL: ${r_sw_15['net_pnl']:+.2f}")
    print(f"  - 1.2:1 R:R ($2.40 TP / $2.00 SL): Trades: {r_sw_12['total_trades']:4d} | Win Rate: {r_sw_12['win_rate']:.1f}% | PF: {r_sw_12['profit_factor']} | Net PnL: ${r_sw_12['net_pnl']:+.2f}")
    print(f"  - 1.0:1 R:R ($2.00 TP / $2.00 SL): Trades: {r_sw_10['total_trades']:4d} | Win Rate: {r_sw_10['win_rate']:.1f}% | PF: {r_sw_10['profit_factor']} | Net PnL: ${r_sw_10['net_pnl']:+.2f}\n")

    print("==========================================================================================")
    print("  RESEARCH HYPOTHESIS 3: M5 FAIR VALUE GAP (FVG) / IMBALANCE FILL ENTRIES")
    print("==========================================================================================")
    # M5 FVG: Bullish FVG when M5 bar1 high < M5 bar3 low; Bearish FVG when M5 bar1 low > M5 bar3 high
    df_m5["fvg_bull"] = df_m5["low"] - df_m5["high"].shift(2)
    df_m5["fvg_bear"] = df_m5["low"].shift(2) - df_m5["high"]

    df_m5["fvg_type"] = np.where(df_m5["fvg_bull"] > 0.50, "BUY", np.where(df_m5["fvg_bear"] > 0.50, "SELL", "NONE"))

    df_m1 = pd.merge_asof(df_m1.sort_values("time_dt"), df_m5[["time_dt", "fvg_type"]].sort_values("time_dt"), on="time_dt", direction="backward")
    df_fvg = df_m1[(df_m1["fvg_type"] != "NONE") & (df_m1["m15_trend"] == np.where(df_m1["fvg_type"] == "BUY", "UPTREND", "DOWNTREND"))].copy()
    df_fvg["direction"] = df_fvg["fvg_type"]

    r_fvg_25 = evaluate_setup(df_fvg, sl_usd=1.50, tp_usd=3.75, cooldown_sec=300)
    r_fvg_15 = evaluate_setup(df_fvg, sl_usd=1.50, tp_usd=2.25, cooldown_sec=300)
    r_fvg_12 = evaluate_setup(df_fvg, sl_usd=1.50, tp_usd=1.80, cooldown_sec=300)
    r_fvg_10 = evaluate_setup(df_fvg, sl_usd=1.50, tp_usd=1.50, cooldown_sec=300)

    print(f"  - 2.5:1 R:R ($3.75 TP / $1.50 SL): Trades: {r_fvg_25['total_trades']:4d} | Win Rate: {r_fvg_25['win_rate']:.1f}% | PF: {r_fvg_25['profit_factor']} | Net PnL: ${r_fvg_25['net_pnl']:+.2f}")
    print(f"  - 1.5:1 R:R ($2.25 TP / $1.50 SL): Trades: {r_fvg_15['total_trades']:4d} | Win Rate: {r_fvg_15['win_rate']:.1f}% | PF: {r_fvg_15['profit_factor']} | Net PnL: ${r_fvg_15['net_pnl']:+.2f}")
    print(f"  - 1.2:1 R:R ($1.80 TP / $1.50 SL): Trades: {r_fvg_12['total_trades']:4d} | Win Rate: {r_fvg_12['win_rate']:.1f}% | PF: {r_fvg_12['profit_factor']} | Net PnL: ${r_fvg_12['net_pnl']:+.2f}")
    print(f"  - 1.0:1 R:R ($1.50 TP / $1.50 SL): Trades: {r_fvg_10['total_trades']:4d} | Win Rate: {r_fvg_10['win_rate']:.1f}% | PF: {r_fvg_10['profit_factor']} | Net PnL: ${r_fvg_10['net_pnl']:+.2f}\n")

    print("==========================================================================================")
    print("  RESEARCH HYPOTHESIS 4: M15 EMA TOUCH PULLBACK REVERSAL IN TREND")
    print("==========================================================================================")
    # Pullback Reversal: Price in M15 Uptrend pulls back to within $0.50 of M15 EMA 20, then prints a strong green M1 candle
    # Price in M15 Downtrend pulls back to within $0.50 of M15 EMA 20, then prints a strong red M1 candle
    df_m15_sub = df_m15[["time_dt", "ema20"]].sort_values("time_dt")
    df_m1 = pd.merge_asof(df_m1.sort_values("time_dt"), df_m15_sub, on="time_dt", direction="backward")

    df_m1["dist_ema20"] = (df_m1["close"] - df_m1["ema20"]).abs()
    is_pullback_buy = (df_m1["m15_trend"] == "UPTREND") & (df_m1["dist_ema20"] <= 0.80) & (df_m1["close"] > df_m1["open"]) & (df_m1["hl_range"] > 0.80)
    is_pullback_sell = (df_m1["m15_trend"] == "DOWNTREND") & (df_m1["dist_ema20"] <= 0.80) & (df_m1["close"] < df_m1["open"]) & (df_m1["hl_range"] > 0.80)

    df_m1["pb_signal"] = np.where(is_pullback_buy, "BUY", np.where(is_pullback_sell, "SELL", "NONE"))
    df_pb = df_m1[df_m1["pb_signal"] != "NONE"].copy()
    df_pb["direction"] = df_pb["pb_signal"]

    r_pb_25 = evaluate_setup(df_pb, sl_usd=2.00, tp_usd=5.00, cooldown_sec=180)
    r_pb_15 = evaluate_setup(df_pb, sl_usd=2.00, tp_usd=3.00, cooldown_sec=180)
    r_pb_12 = evaluate_setup(df_pb, sl_usd=2.00, tp_usd=2.40, cooldown_sec=180)
    r_pb_10 = evaluate_setup(df_pb, sl_usd=2.00, tp_usd=2.00, cooldown_sec=180)

    print(f"  - 2.5:1 R:R ($5.00 TP / $2.00 SL): Trades: {r_pb_25['total_trades']:4d} | Win Rate: {r_pb_25['win_rate']:.1f}% | PF: {r_pb_25['profit_factor']} | Net PnL: ${r_pb_25['net_pnl']:+.2f}")
    print(f"  - 1.5:1 R:R ($3.00 TP / $2.00 SL): Trades: {r_pb_15['total_trades']:4d} | Win Rate: {r_pb_15['win_rate']:.1f}% | PF: {r_pb_15['profit_factor']} | Net PnL: ${r_pb_15['net_pnl']:+.2f}")
    print(f"  - 1.2:1 R:R ($2.40 TP / $2.00 SL): Trades: {r_pb_12['total_trades']:4d} | Win Rate: {r_pb_12['win_rate']:.1f}% | PF: {r_pb_12['profit_factor']} | Net PnL: ${r_pb_12['net_pnl']:+.2f}")
    print(f"  - 1.0:1 R:R ($2.00 TP / $2.00 SL): Trades: {r_pb_10['total_trades']:4d} | Win Rate: {r_pb_10['win_rate']:.1f}% | PF: {r_pb_10['profit_factor']} | Net PnL: ${r_pb_10['net_pnl']:+.2f}")
    print("==========================================================================================")

if __name__ == "__main__":
    run_3month_pattern_research()
