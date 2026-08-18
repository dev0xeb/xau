"""
Market Structure Diagnostic for Asian vs London vs NY Sessions on Gold (Past 3 Months).

Measures:
1. Mean Reversion Rate (How often a 5m sweep reverses back into range).
2. Continuation / Breakout Rate (How often a 5m sweep continues as a macro trend breakout).
3. Average Expansion Volatility per session.
"""

import sys
from pathlib import Path
from datetime import datetime, date
import pandas as pd
import numpy as np

def diagnose_session_structures():
    proc_5m_path = Path("data/processed/xau_5m_5y.parquet")
    if not proc_5m_path.exists():
        print("[ERROR] 5m dataset missing!")
        return

    df_5m = pd.read_parquet(proc_5m_path)
    df_5m['timestamp'] = pd.to_datetime(df_5m['timestamp'])

    cutoff_date = pd.to_datetime("2026-05-10", utc=True)
    df_5m_3m = df_5m[df_5m['timestamp'] >= cutoff_date].sort_values('timestamp').reset_index(drop=True)

    df_5m_3m['hour'] = df_5m_3m['timestamp'].dt.hour

    closes = df_5m_3m['close'].values
    highs = df_5m_3m['high'].values
    lows = df_5m_3m['low'].values
    hours = df_5m_3m['hour'].values
    n = len(df_5m_3m)

    sessions = {'ASIA': [], 'LONDON': [], 'NY': [], 'OVERLAP': []}

    for i in range(15, n - 12):
        h = hours[i]
        sess_key = 'ASIA' if (h >= 21 or h < 7) else ('LONDON' if (7 <= h < 12) else ('OVERLAP' if (12 <= h < 16) else 'NY'))

        range_high = np.max(highs[i-10:i])
        range_low = np.min(lows[i-10:i])
        range_size = range_high - range_low

        if not (1.50 <= range_size <= 12.00):
            continue

        c_high = highs[i]
        c_low = lows[i]
        c_close = closes[i]

        # Check if a sweep wick occurred
        is_low_sweep = (c_low < range_low and c_close > range_low)
        is_high_sweep = (c_high > range_high and c_close < range_high)

        if is_low_sweep or is_high_sweep:
            fut_highs = highs[i+1:i+12]
            fut_lows = lows[i+1:i+12]

            max_expansion_up = np.max(fut_highs) - c_close
            max_expansion_dn = c_close - np.min(fut_lows)

            if is_low_sweep:
                reversed_to_target = (np.max(fut_highs) >= range_high)
                continued_down = (np.min(fut_lows) <= range_low - 2.00)
                sessions[sess_key].append({'reversed': reversed_to_target, 'continued': continued_down, 'range_size': range_size})
            elif is_high_sweep:
                reversed_to_target = (np.min(fut_lows) <= range_low)
                continued_up = (np.max(fut_highs) >= range_high + 2.00)
                sessions[sess_key].append({'reversed': reversed_to_target, 'continued': continued_up, 'range_size': range_size})

    print("=" * 95)
    print(" EMPIRICAL SESSION MARKET STRUCTURE DIAGNOSIS (PAST 3 MONTHS)")
    print("=" * 95)

    for k, data in sessions.items():
        if not data:
            continue
        df_s = pd.DataFrame(data)
        tot = len(df_s)
        rev = len(df_s[df_s['reversed'] == True])
        cont = len(df_s[df_s['continued'] == True])

        rev_rate = (rev / tot) * 100.0
        cont_rate = (cont / tot) * 100.0

        print(f"\n SESSION: {k:<8} | Total Sweep Events: {tot}")
        print(f"   - Clean Range Reversals (Mean Reversion):  {rev:<3} events ({rev_rate:>5.1f}%)")
        print(f"   - Trend Breakouts (Macro Expansion):      {cont:<3} events ({cont_rate:>5.1f}%)")
        print(f"   - Primary Behavior: {'RANGING / MEAN REVERTING' if rev_rate > cont_rate else 'TREND BREAKOUT / MOMENTUM EXPANSION'}")

if __name__ == "__main__":
    diagnose_session_structures()
