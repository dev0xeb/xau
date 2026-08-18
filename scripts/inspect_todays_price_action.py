"""
Detailed Step-by-Step Price Action & Scalping Setup Inspector for Today's Gold (XAU/USD) Chart.

Extracts today's full 1m, 5m, and 15m data, identifies all major price swings, liquidity sweeps,
FVGs, session open impulses, and exact scalping opportunities step-by-step.
"""

import sys
from pathlib import Path
from datetime import datetime
import pandas as pd
import numpy as np

def inspect_today():
    raw_1m_path = Path("data/raw/xau_1m_5y.parquet")
    proc_5m_path = Path("data/processed/xau_5m_5y.parquet")
    proc_15m_path = Path("data/processed/xau_15m_5y.parquet")

    if not (raw_1m_path.exists() and proc_5m_path.exists() and proc_15m_path.exists()):
        print("[ERROR] Datasets missing!")
        return

    df_1m = pd.read_parquet(raw_1m_path)
    df_5m = pd.read_parquet(proc_5m_path)
    df_15m = pd.read_parquet(proc_15m_path)

    df_1m['timestamp'] = pd.to_datetime(df_1m['timestamp'])
    df_5m['timestamp'] = pd.to_datetime(df_5m['timestamp'])
    df_15m['timestamp'] = pd.to_datetime(df_15m['timestamp'])

    # Find latest date in dataset
    latest_ts = df_1m['timestamp'].max()
    latest_date = latest_ts.date()

    print("=" * 85)
    print(f" TODAY'S STEP-BY-STEP GOLD (XAU/USD) PRICE ACTION INSPECTION ({latest_date})")
    print("=" * 85)

    df_1m_today = df_1m[df_1m['timestamp'].dt.date == latest_date].sort_values('timestamp').reset_index(drop=True)
    df_5m_today = df_5m[df_5m['timestamp'].dt.date == latest_date].sort_values('timestamp').reset_index(drop=True)
    df_15m_today = df_15m[df_15m['timestamp'].dt.date == latest_date].sort_values('timestamp').reset_index(drop=True)

    print(f" Total Candles Today ({latest_date}):")
    print(f"  - 1m Candles:  {len(df_1m_today)}")
    print(f"  - 5m Candles:  {len(df_5m_today)}")
    print(f"  - 15m Candles: {len(df_15m_today)}")

    day_open = df_1m_today['open'].iloc[0]
    day_close = df_1m_today['close'].iloc[-1]
    day_high = df_1m_today['high'].max()
    day_low = df_1m_today['low'].min()
    day_range = day_high - day_low

    print(f"\n Today's Macro Overview:")
    print(f"  - Day Open:  ${day_open:.2f}")
    print(f"  - Day High:  ${day_high:.2f}")
    print(f"  - Day Low:   ${day_low:.2f}")
    print(f"  - Day Close: ${day_close:.2f}")
    print(f"  - Total Range: ${day_range:.2f} ({day_range*10:.1f} pips)")

    print("\n" + "=" * 85)
    print(" 15-MINUTE CHRONOLOGICAL SESSION BREAKDOWN")
    print("=" * 85)

    for idx, row in df_15m_today.iterrows():
        ts_str = row['timestamp'].strftime('%H:%M UTC')
        o, h, l, c = row['open'], row['high'], row['low'], row['close']
        rng = h - l
        body = abs(c - o)
        direction = "BULL" if c >= o else "BEAR"
        hour = row['timestamp'].hour

        session_tag = "ASIA" if (hour < 7 or hour >= 21) else ("LONDON" if (7 <= hour < 12) else ("OVERLAP" if (12 <= hour < 16) else "NY"))

        print(f" [{ts_str}] [{session_tag:<7}] {direction} | O:${o:.2f} H:${h:.2f} L:${l:.2f} C:${c:.2f} | Range:${rng:.2f} Body:${body:.2f}")

    print("\n" + "=" * 85)
    print(" SCALPING MOVES & PATTERN IDENTIFICATION (TODAY)")
    print("=" * 85)

    # Detect 5m FVGs, Sweeps, and CHoCHs for today
    highs_5 = df_5m_today['high'].values
    lows_5 = df_5m_today['low'].values
    closes_5 = df_5m_today['close'].values
    opens_5 = df_5m_today['open'].values
    times_5 = df_5m_today['timestamp'].dt.strftime('%H:%M UTC').values
    n_5 = len(df_5m_today)

    moves_found = []

    for i in range(2, n_5 - 4):
        # 1. Check for 5m Bullish FVG or Low Sweep
        prev_low_20 = np.min(lows_5[max(0, i-10):i])
        cur_low = lows_5[i]
        cur_close = closes_5[i]

        # Low Sweep
        if cur_low < prev_low_20 and cur_close > prev_low_20:
            post_high = np.max(highs_5[i+1:min(i+7, n_5)])
            move_size = post_high - cur_close
            moves_found.append({
                'time': times_5[i],
                'type': 'BULLISH SWEEP REVERSAL',
                'entry': cur_close,
                'sl': cur_low - 0.50,
                'potential_tp': post_high,
                'pips': move_size * 10,
                'desc': f"Wicked below 10-bar low (${prev_low_20:.2f}), closed at ${cur_close:.2f}. Pushed +${move_size:.2f} (+{move_size*10:.1f} pips) in next 30m."
            })

        # High Sweep
        prev_high_20 = np.max(highs_5[max(0, i-10):i])
        cur_high = highs_5[i]
        if cur_high > prev_high_20 and cur_close < prev_high_20:
            post_low = np.min(lows_5[i+1:min(i+7, n_5)])
            move_size = cur_close - post_low
            moves_found.append({
                'time': times_5[i],
                'type': 'BEARISH SWEEP REVERSAL',
                'entry': cur_close,
                'sl': cur_high + 0.50,
                'potential_tp': post_low,
                'pips': move_size * 10,
                'desc': f"Wicked above 10-bar high (${prev_high_20:.2f}), closed at ${cur_close:.2f}. Dropped -${move_size:.2f} (+{move_size*10:.1f} pips) in next 30m."
            })

        # Bullish 5m FVG (Displacement)
        if lows_5[i] > highs_5[i-2]:
            gap = lows_5[i] - highs_5[i-2]
            if gap >= 0.40:
                fvg_mid = (lows_5[i] + highs_5[i-2]) / 2.0
                post_high = np.max(highs_5[i+1:min(i+7, n_5)])
                move_size = post_high - fvg_mid
                moves_found.append({
                    'time': times_5[i],
                    'type': 'BULLISH FVG DISPLACEMENT',
                    'entry': fvg_mid,
                    'sl': highs_5[i-2] - 0.50,
                    'potential_tp': post_high,
                    'pips': move_size * 10,
                    'desc': f"5m FVG formed (${highs_5[i-2]:.2f} to ${lows_5[i]:.2f}, gap=${gap:.2f}). Retrace to mid (${fvg_mid:.2f}) expanded +${move_size:.2f} (+{move_size*10:.1f} pips)."
                })

        # Bearish 5m FVG (Displacement)
        elif highs_5[i] < lows_5[i-2]:
            gap = lows_5[i-2] - highs_5[i]
            if gap >= 0.40:
                fvg_mid = (lows_5[i-2] + highs_5[i]) / 2.0
                post_low = np.min(lows_5[i+1:min(i+7, n_5)])
                move_size = fvg_mid - post_low
                moves_found.append({
                    'time': times_5[i],
                    'type': 'BEARISH FVG DISPLACEMENT',
                    'entry': fvg_mid,
                    'sl': lows_5[i-2] + 0.50,
                    'potential_tp': post_low,
                    'pips': move_size * 10,
                    'desc': f"5m Bearish FVG formed (gap=${gap:.2f}). Retrace to mid (${fvg_mid:.2f}) dropped -${move_size:.2f} (+{move_size*10:.1f} pips)."
                })

    df_moves = pd.DataFrame(moves_found)
    print(f"\n TOTAL DISTINCT SCALPING OPPORTUNITIES IDENTIFIED TODAY: {len(df_moves)}\n")

    for idx, r in df_moves.iterrows():
        print(f" Move #{idx+1:02d} [{r['time']}] -> {r['type']}")
        print(f"    Entry: ${r['entry']:.2f} | SL: ${r['sl']:.2f} | Max Target: ${r['potential_tp']:.2f}")
        print(f"    Expansion: +{r['pips']:.1f} pips")
        print(f"    Details: {r['desc']}\n")

if __name__ == "__main__":
    inspect_today()
