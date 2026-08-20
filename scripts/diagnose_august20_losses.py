"""
Forensic Audit of August Gold Price Action & Trades
---------------------------------------------------
Audits bar-by-bar price action, volatility spikes, and trade triggers on recent August trading days.
"""

import sys
from pathlib import Path
import pandas as pd
import numpy as np
import joblib

def audit_august_session():
    dataset_path = Path("data/processed/xau_5m_5y.parquet")
    model_path = Path("models/saved_models/model2_fvg_rf_quality_gate.joblib")

    if not dataset_path.exists() or not model_path.exists():
        print("[ERROR] Dataset or model missing!")
        return

    df = pd.read_parquet(dataset_path)
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    df = df.sort_values('timestamp').reset_index(drop=True)

    # Inspect last 1,000 bars
    df_recent = df.tail(1000).reset_index(drop=True)

    print("=========================================================================================")
    print(" FORENSIC AUDIT OF RECENT AUGUST GOLD PRICE ACTION & TRADES")
    print("=========================================================================================")
    print(f" Total M5 Bars Inspected: {len(df_recent)} Bars from {df_recent['timestamp'].iloc[0]} to {df_recent['timestamp'].iloc[-1]}")
    print(f" High-Low Volatility Range: ${df_recent['high'].max() - df_recent['low'].min():.2f} (High: ${df_recent['high'].max():.2f} / Low: ${df_recent['low'].min():.2f})")

    rf_model = joblib.load(model_path)

    df_recent['m5_ema21'] = df_recent['close'].ewm(span=21, adjust=False).mean()
    tr = np.maximum(df_recent['high'] - df_recent['low'], np.maximum(np.abs(df_recent['high'] - df_recent['close'].shift(1)), np.abs(df_recent['low'] - df_recent['close'].shift(1))))
    df_recent['atr14'] = pd.Series(tr).ewm(span=14, adjust=False).mean()

    pip_size = 0.10
    total_setups = 0
    winning_setups = 0
    losing_setups = 0

    print("\n--- RECENT TRADING DAY SETUP DISCOVERY ---")
    for i in range(5, len(df_recent) - 20):
        t = df_recent['timestamp'].iloc[i]
        hour = t.hour
        if hour < 6 or hour >= 17: continue

        idx = i
        high_t, low_t = df_recent['high'].iloc[idx], df_recent['low'].iloc[idx]
        high_t2, low_t2 = df_recent['high'].iloc[idx-2], df_recent['low'].iloc[idx-2]

        bull_fvg_size = (low_t - high_t2) / pip_size
        bear_fvg_size = (low_t2 - high_t) / pip_size

        bull_fvg = bull_fvg_size >= 1.5
        bear_fvg = bear_fvg_size >= 1.5
        if not (bull_fvg or bear_fvg): continue

        prior_5_low = df_recent['low'].iloc[idx-5:idx].min()
        prior_5_high = df_recent['high'].iloc[idx-5:idx].max()
        e21 = df_recent['m5_ema21'].iloc[idx]

        bull_sweep = prior_5_low <= e21
        bear_sweep = prior_5_high >= e21

        close = df_recent['close'].iloc[idx]
        base_buy = bull_fvg and bull_sweep and (close > e21)
        base_sell = bear_fvg and bear_sweep and (close < e21)
        if not (base_buy or base_sell): continue

        direction = "BUY" if base_buy else "SELL"
        total_setups += 1

        entry = high_t2 + 0.35 if direction == "BUY" else low_t2 - 0.35
        sl = entry - 3.50 if direction == "BUY" else entry + 3.50
        tp = entry + 7.00 if direction == "BUY" else entry - 7.00

        win = False
        loss = False
        for k in range(idx + 1, min(idx + 50, len(df_recent))):
            if direction == "BUY":
                if df_recent['low'].iloc[k] <= sl:
                    loss = True
                    break
                if df_recent['high'].iloc[k] >= tp:
                    win = True
                    break
            else:
                if df_recent['high'].iloc[k] >= sl:
                    loss = True
                    break
                if df_recent['low'].iloc[k] <= tp:
                    win = True
                    break

        status = "WIN (+2.0x R)" if win else ("LOSS (-1.0x R)" if loss else "OPEN")
        if win: winning_setups += 1
        if loss: losing_setups += 1

        print(f" [{t.strftime('%Y-%m-%d %H:%M UTC')}] Direction: {direction:4s} | Entry: ${entry:.2f} | SL: ${sl:.2f} | FVG: ${bull_fvg_size*0.10:.2f} | Status: {status}")

    print("-----------------------------------------------------------------------------------------")
    print(f" Total Setups Found         : {total_setups}")
    print(f" Winning Setups             : {winning_setups}")
    print(f" Losing Setups              : {losing_setups}")
    if total_setups > 0:
        print(f" Win Rate (%)               : {winning_setups / (winning_setups + losing_setups + 1e-9) * 100:.1f}%")
    print("=========================================================================================")

if __name__ == "__main__":
    audit_august_session()
