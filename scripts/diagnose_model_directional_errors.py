"""
Empirical Diagnostic of Model Directional Errors (What the Model Did Wrong).

Inspects:
1. Trade #01 (Aug 3, 12:20 UTC BUY) vs Daily Open ($4,072.46 -> Price below Daily Open)
2. Trade #02 (Aug 4, 12:40 UTC SELL) vs Daily Open ($4,058.25 -> Price above Daily Open)
3. Trade #03 (Aug 5, 13:35 UTC SELL) vs Daily Open ($4,072.46 -> Price above Daily Open)
"""

import sys
from pathlib import Path
from datetime import datetime, date
import pandas as pd
import numpy as np

def diagnose_directional_errors():
    proc_1m_path = Path("data/raw/xau_1m_5y.parquet")
    proc_5m_path = Path("data/processed/xau_5m_5y.parquet")

    if not (proc_1m_path.exists() and proc_5m_path.exists()):
        print("[ERROR] Datasets missing!")
        return

    df_1m = pd.read_parquet(proc_1m_path)
    df_5m = pd.read_parquet(proc_5m_path)

    df_1m['timestamp'] = pd.to_datetime(df_1m['timestamp'])
    df_5m['timestamp'] = pd.to_datetime(df_5m['timestamp'])

    losses = [
        {'date': date(2026, 8, 3), 'time': '12:20 UTC', 'type': 'BUY', 'entry': 4052.64, 'sl': 4047.33, 'tp': 4064.82},
        {'date': date(2026, 8, 4), 'time': '12:40 UTC', 'type': 'SELL', 'entry': 4078.16, 'sl': 4085.79, 'tp': 4059.78},
        {'date': date(2026, 8, 5), 'time': '13:35 UTC', 'type': 'SELL', 'entry': 4200.75, 'sl': 4206.16, 'tp': 4183.30}
    ]

    print("=" * 95)
    print(" DETAILED DIAGNOSTIC: WHAT THE MODEL DID WRONG ON THE 3 LOSING TRADES")
    print("=" * 95)

    for idx, l in enumerate(losses):
        d = l['date']
        df_day = df_1m[df_1m['timestamp'].dt.date == d].sort_values('timestamp').reset_index(drop=True)

        daily_open = df_day['open'].iloc[0]
        entry_price = l['entry']

        price_diff = entry_price - daily_open
        market_bias = "BULLISH EXPANSION (Price Above Daily Open)" if price_diff > 0 else "BEARISH EXPANSION (Price Below Daily Open)"

        print(f"\n LOSS #{idx+1:02d} | Date: {d} at {l['time']} | Model Execution: {l['type']} at ${entry_price:.2f}")
        print("-" * 95)
        print(f"  Daily Midnight Open Price:  ${daily_open:.2f}")
        print(f"  Price Position at Entry:    ${entry_price:.2f} ({price_diff:+.2f} dollars from Daily Open)")
        print(f"  Actual Market Expansion:    {market_bias}")

        print(f"\n  WHAT THE MODEL DID WRONG:")
        if l['type'] == 'BUY' and price_diff < 0:
            print(f"     [ERROR] MODEL EXECUTED A BUY WHEN PRICE WAS TRADING BELOW THE DAILY OPEN (${daily_open:.2f})!")
            print(f"             The market was in a BEARISH EXPANSION DAY (-${abs(price_diff):.2f}). The model tried to 'fade' a falling market instead of selling with the bearish momentum.")
        elif l['type'] == 'SELL' and price_diff > 0:
            print(f"     [ERROR] MODEL EXECUTED A SELL WHEN PRICE WAS TRADING ABOVE THE DAILY OPEN (${daily_open:.2f})!")
            print(f"             The market was in a BULLISH EXPANSION DAY (+${price_diff:.2f}). The model tried to 'fade' a rising market instead of buying with the bullish momentum.")

if __name__ == "__main__":
    diagnose_directional_errors()
