"""
Whipsaw Inspector for Standard Overlap Model (No Lag) Losing Trades.

Checks whether post-SL price action reached the TP target later in the day:
1. Trade #01 (Aug 3, 12:20 UTC BUY)
2. Trade #02 (Aug 4, 12:40 UTC SELL)
3. Trade #03 (Aug 5, 13:35 UTC SELL)
"""

import sys
from pathlib import Path
from datetime import datetime, date
import pandas as pd
import numpy as np

def check_whipsaws():
    proc_1m_path = Path("data/raw/xau_1m_5y.parquet")
    if not proc_1m_path.exists():
        print("[ERROR] 1m dataset missing!")
        return

    df_1m = pd.read_parquet(proc_1m_path)
    df_1m['timestamp'] = pd.to_datetime(df_1m['timestamp'])

    # 3 Losing Trades details in Standard Overlap Model:
    losses = [
        {'date': date(2026, 8, 3), 'time': '12:20 UTC', 'type': 'BUY', 'entry': 4052.64, 'sl': 4047.33, 'tp': 4064.82},
        {'date': date(2026, 8, 4), 'time': '12:40 UTC', 'type': 'SELL', 'entry': 4078.16, 'sl': 4085.79, 'tp': 4059.78},
        {'date': date(2026, 8, 5), 'time': '13:35 UTC', 'type': 'SELL', 'entry': 4200.75, 'sl': 4206.16, 'tp': 4183.30}
    ]

    print("=" * 95)
    print(" WHIPSAW AUDIT: DID PRICE HIT SL FIRST AND THEN RUN TO TP?")
    print("=" * 95)

    for idx, l in enumerate(losses):
        d = l['date']
        df_day = df_1m[df_1m['timestamp'].dt.date == d].sort_values('timestamp').reset_index(drop=True)

        entry_t_str = f"{d} {l['time'][:5]}"
        df_post = df_day[df_day['timestamp'].dt.strftime('%Y-%m-%d %H:%M') >= entry_t_str].reset_index(drop=True)

        highs = df_post['high'].values
        lows = df_post['low'].values
        times = df_post['timestamp'].dt.strftime('%H:%M UTC').values

        sl_hit_time = None
        tp_hit_time = None

        if l['type'] == 'BUY':
            # Check SL hit
            sl_mask = (lows <= l['sl'])
            if np.any(sl_mask):
                sl_idx = np.argmax(sl_mask)
                sl_hit_time = times[sl_idx]

                # Check if TP was hit AFTER SL
                tp_mask = (highs[sl_idx:] >= l['tp'])
                if np.any(tp_mask):
                    tp_post_idx = sl_idx + np.argmax(tp_mask)
                    tp_hit_time = times[tp_post_idx]

        elif l['type'] == 'SELL':
            sl_mask = (highs >= l['sl'])
            if np.any(sl_mask):
                sl_idx = np.argmax(sl_mask)
                sl_hit_time = times[sl_idx]

                tp_mask = (lows[sl_idx:] <= l['tp'])
                if np.any(tp_mask):
                    tp_post_idx = sl_idx + np.argmax(tp_mask)
                    tp_hit_time = times[tp_post_idx]

        print(f"\n LOSS #{idx+1:02d} | Date: {d} at {l['time']} | {l['type']} | Entry:${l['entry']:.2f} | SL:${l['sl']:.2f} | TP:${l['tp']:.2f}")
        print("-" * 95)
        print(f"  Stop Loss Hit Time: {sl_hit_time}")
        if tp_hit_time:
            print(f"  RESULT: YES! WHIPSAW DETECTED! Price hit SL at {sl_hit_time}, then REVERSED & HIT TP at {tp_hit_time}!")
        else:
            print(f"  RESULT: NO WHIPSAW. Price continued past SL and did NOT reach TP target.")

if __name__ == "__main__":
    check_whipsaws()
