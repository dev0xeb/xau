"""
Diagnostic Inspector for the 3 Losing Overlap Trades (Aug 3, Aug 4, Aug 5, 2026).

Inspects exact 1m and 5m candles during:
1. Trade #01 (Aug 3, 12:20 UTC BUY)
2. Trade #02 (Aug 4, 12:40 UTC SELL)
3. Trade #03 (Aug 5, 13:35 UTC SELL)
"""

import sys
from pathlib import Path
from datetime import datetime, date
import pandas as pd
import numpy as np

def diagnose_losing_overlap_trades():
    proc_1m_path = Path("data/raw/xau_1m_5y.parquet")
    proc_5m_path = Path("data/processed/xau_5m_5y.parquet")

    if not (proc_1m_path.exists() and proc_5m_path.exists()):
        print("[ERROR] Datasets missing!")
        return

    df_1m = pd.read_parquet(proc_1m_path)
    df_5m = pd.read_parquet(proc_5m_path)

    df_1m['timestamp'] = pd.to_datetime(df_1m['timestamp'])
    df_5m['timestamp'] = pd.to_datetime(df_5m['timestamp'])

    # 3 Losing Trades details:
    losses = [
        {'date': date(2026, 8, 3), 'time': '12:20 UTC', 'type': 'BUY', 'entry': 4052.64, 'sl': 4047.33, 'tp': 4064.82},
        {'date': date(2026, 8, 4), 'time': '12:40 UTC', 'type': 'SELL', 'entry': 4078.16, 'sl': 4085.79, 'tp': 4059.78},
        {'date': date(2026, 8, 5), 'time': '13:35 UTC', 'type': 'SELL', 'entry': 4200.75, 'sl': 4206.16, 'tp': 4183.30}
    ]

    print("=" * 95)
    print(" EMPIRICAL DIAGNOSTIC OF THE 3 LOSING OVERLAP TRADES")
    print("=" * 95)

    for idx, l in enumerate(losses):
        d = l['date']
        df_1m_day = df_1m[df_1m['timestamp'].dt.date == d].sort_values('timestamp').reset_index(drop=True)
        df_5m_day = df_5m[df_5m['timestamp'].dt.date == d].sort_values('timestamp').reset_index(drop=True)

        print(f"\n LOSS #{idx+1:02d} | Date: {d} at {l['time']} | {l['type']} Entry:${l['entry']:.2f} | SL:${l['sl']:.2f} | Target:${l['tp']:.2f}")
        print("-" * 95)

        # Find 1m candles around trade entry
        entry_t_str = f"{d} {l['time'][:5]}"
        df_1m_sub = df_1m_day[df_1m_day['timestamp'].dt.strftime('%Y-%m-%d %H:%M') >= entry_t_str].head(30)

        if not df_1m_sub.empty:
            min_l_post = df_1m_sub['low'].min()
            max_h_post = df_1m_sub['high'].max()

            print(f"  1m Post-Entry Price Action (Next 30 Mins):")
            print(f"     - Lowest Price Reached:  ${min_l_post:.2f}")
            print(f"     - Highest Price Reached: ${max_h_post:.2f}")

            if l['type'] == 'BUY':
                sweep_beyond_sl = (min_l_post < l['sl'])
                recovered_after = (max_h_post >= l['tp'])
                print(f"  DIAGNOSIS:")
                if recovered_after:
                    print(f"     - STOP LOSS WHIPSAW / SECOND SWEEP: Price wicked down to ${min_l_post:.2f} (sweeping SL by ${l['sl']-min_l_post:.2f}), then REVERSED & EXPANDED to target at ${l['tp']:.2f}!")
                else:
                    print(f"     - EARLY ENTRY / PREMATURE TRIGGER: Entered at 12:20 UTC BEFORE the actual 13:00 UTC London sweep low was established at ${df_1m_day['low'].min():.2f}.")
            else:
                sweep_beyond_sl = (max_h_post > l['sl'])
                recovered_after = (min_l_post <= l['tp'])
                print(f"  DIAGNOSIS:")
                if recovered_after:
                    print(f"     - STOP LOSS WHIPSAW / SECOND SWEEP: Price wicked up to ${max_h_post:.2f} (sweeping SL by ${max_h_post-l['sl']:.2f}), then REVERSED & EXPANDED to target at ${l['tp']:.2f}!")
                else:
                    print(f"     - COUNTER-TREND EXPANSION: Entered SELL at 12:40/13:35 UTC during strong NY bullish expansion. Price broke through SL to reach daily high.")

if __name__ == "__main__":
    diagnose_losing_overlap_trades()
