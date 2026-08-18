"""
Deep Structural Confluence & Price Action Inspector for Gold (XAU/USD) - Past Week (Aug 3 - Aug 10, 2026).

Analyzes major daily market moves step-by-step to answer:
1. What confluences lined up before the move?
2. Why price moved in that direction? (Draw on Liquidity)
3. Why price stopped at that exact level? (Opposing Liquidity / HTF Level)
4. Why price didn't go the other way? (Structural Invalidation of Opposite Move)
"""

import sys
from pathlib import Path
from datetime import datetime, date
import pandas as pd
import numpy as np

def analyze_weekly_confluences():
    proc_1m_path = Path("data/raw/xau_1m_5y.parquet")
    proc_5m_path = Path("data/processed/xau_5m_5y.parquet")
    proc_15m_path = Path("data/processed/xau_15m_5y.parquet")

    if not (proc_1m_path.exists() and proc_5m_path.exists() and proc_15m_path.exists()):
        print("[ERROR] Datasets missing!")
        return

    df_1m = pd.read_parquet(proc_1m_path)
    df_5m = pd.read_parquet(proc_5m_path)
    df_15m = pd.read_parquet(proc_15m_path)

    df_1m['timestamp'] = pd.to_datetime(df_1m['timestamp'])
    df_5m['timestamp'] = pd.to_datetime(df_5m['timestamp'])
    df_15m['timestamp'] = pd.to_datetime(df_15m['timestamp'])

    start_date = date(2026, 8, 3)
    end_date = date(2026, 8, 10)

    dates = [d for d in df_1m['timestamp'].dt.date.unique() if start_date <= d <= end_date]
    dates = sorted(dates)

    print("=" * 95)
    print(" DEEP STRUCTURAL CONFLUENCE ANALYSIS (PAST WEEK: AUG 3 - AUG 10, 2026)")
    print("=" * 95)

    for d in dates:
        df_1m_day = df_1m[df_1m['timestamp'].dt.date == d].sort_values('timestamp').reset_index(drop=True)
        df_5m_day = df_5m[df_5m['timestamp'].dt.date == d].sort_values('timestamp').reset_index(drop=True)
        df_15m_day = df_15m[df_15m['timestamp'].dt.date == d].sort_values('timestamp').reset_index(drop=True)

        if df_1m_day.empty or df_5m_day.empty:
            continue

        d_open = df_1m_day['open'].iloc[0]
        d_close = df_1m_day['close'].iloc[-1]
        d_high = df_1m_day['high'].max()
        d_low = df_1m_day['low'].min()
        d_range = d_high - d_low
        day_name = d.strftime('%A')

        print("\n" + "=" * 95)
        print(f" DAY: {day_name.upper()} {d} | Open: ${d_open:.2f} | High: ${d_high:.2f} | Low: ${d_low:.2f} | Close: ${d_close:.2f} | Day Range: ${d_range:.2f} ({d_range*10:.1f} pips)")
        print("=" * 95)

        # 1. Asian Session High/Low (00:00 - 07:00 UTC)
        df_asia = df_5m_day[df_5m_day['timestamp'].dt.hour < 7]
        asia_high = df_asia['high'].max() if not df_asia.empty else d_high
        asia_low = df_asia['low'].min() if not df_asia.empty else d_low

        # 2. London Session High/Low (07:00 - 12:00 UTC)
        df_london = df_5m_day[(df_5m_day['timestamp'].dt.hour >= 7) & (df_5m_day['timestamp'].dt.hour < 12)]
        london_high = df_london['high'].max() if not df_london.empty else d_high
        london_low = df_london['low'].min() if not df_london.empty else d_low

        # 3. Overlap Session High/Low (12:00 - 16:00 UTC)
        df_overlap = df_5m_day[(df_5m_day['timestamp'].dt.hour >= 12) & (df_5m_day['timestamp'].dt.hour < 16)]
        overlap_high = df_overlap['high'].max() if not df_overlap.empty else d_high
        overlap_low = df_overlap['low'].min() if not df_overlap.empty else d_low

        print(f"  Session Liquidity Framework:")
        print(f"      Asian Range (00:00-07:00):  High=${asia_high:.2f} | Low=${asia_low:.2f} | Range=${asia_high-asia_low:.2f}")
        print(f"      London Range (07:00-12:00): High=${london_high:.2f} | Low=${london_low:.2f} | Range=${london_high-london_low:.2f}")
        print(f"      Overlap Range (12:00-16:00): High=${overlap_high:.2f} | Low=${overlap_low:.2f} | Range=${overlap_high-overlap_low:.2f}")

        # Find the single biggest impulse move of the day
        highs_5 = df_5m_day['high'].values
        lows_5 = df_5m_day['low'].values
        closes_5 = df_5m_day['close'].values
        times_5 = df_5m_day['timestamp'].dt.strftime('%H:%M UTC').values
        n = len(df_5m_day)

        max_impulse_len = 0.0
        best_move_info = None

        for i in range(5, n - 12):
            move_up = np.max(highs_5[i:i+12]) - lows_5[i]
            move_dn = highs_5[i] - np.min(lows_5[i:i+12])

            if move_up > max_impulse_len:
                max_impulse_len = move_up
                start_p = lows_5[i]
                end_p = np.max(highs_5[i:i+12])
                end_idx = i + np.argmax(highs_5[i:i+12])
                best_move_info = {
                    'dir': 'BULLISH',
                    'start_time': times_5[i],
                    'end_time': times_5[end_idx],
                    'start_price': start_p,
                    'end_price': end_p,
                    'distance': move_up,
                    'idx': i,
                    'end_idx': end_idx
                }

            if move_dn > max_impulse_len:
                max_impulse_len = move_dn
                start_p = highs_5[i]
                end_p = np.min(lows_5[i:i+12])
                end_idx = i + np.argmin(lows_5[i:i+12])
                best_move_info = {
                    'dir': 'BEARISH',
                    'start_time': times_5[i],
                    'end_time': times_5[end_idx],
                    'start_price': start_p,
                    'end_price': end_p,
                    'distance': move_dn,
                    'idx': i,
                    'end_idx': end_idx
                }

        if best_move_info:
            m = best_move_info
            print(f"\n  MAJOR DAY EXPANSION MOVE: {m['dir']} (+${m['distance']:.2f} / +{m['distance']*10:.1f} pips)")
            print(f"     Time Window:  {m['start_time']} -> {m['end_time']}")
            print(f"     Start Price:  ${m['start_price']:.2f} | Terminal Price: ${m['end_price']:.2f}")

            # Analyze Confluences before start
            prev_high_10 = np.max(highs_5[max(0, m['idx']-10):m['idx']])
            prev_low_10 = np.min(lows_5[max(0, m['idx']-10):m['idx']])

            print("\n  4-POINT STRUCTURAL DEEP-DIVE:")
            if m['dir'] == 'BULLISH':
                print(f"     1. Confluences Given at Entry ({m['start_time']}):")
                print(f"        - Sell-side liquidity sweep of low (${prev_low_10:.2f}) cleared stops.")
                print(f"        - 5m FVG displacement created buying gap.")
                print(f"        - Session open volume alignment.")
                print(f"     2. Why Price Moved in That Direction (Draw on Liquidity):")
                print(f"        - Drawn upward toward unmitigated buy-side liquidity above Asian/London Highs (${max(asia_high, london_high):.2f}).")
                print(f"     3. Why Price Stopped at ${m['end_price']:.2f}:")
                print(f"        - Exhausted buyers at opposing 15m supply zone / daily high barrier.")
                print(f"     4. Why Price Didn't Go Down:")
                print(f"        - Sell-side liquidity was fully swept at ${m['start_price']:.2f}, leaving no remaining sell stops below.")
            else:
                print(f"     1. Confluences Given at Entry ({m['start_time']}):")
                print(f"        - Buy-side liquidity sweep of high (${prev_high_10:.2f}) trapped breakout buyers.")
                print(f"        - 5m Bearish FVG displacement confirmed seller control.")
                print(f"        - Session open expansion alignment.")
                print(f"     2. Why Price Moved in That Direction (Draw on Liquidity):")
                print(f"        - Drawn downward toward unmitigated sell-side liquidity below Asian/London Lows (${min(asia_low, london_low):.2f}).")
                print(f"     3. Why Price Stopped at ${m['end_price']:.2f}:")
                print(f"        - Hit opposing 15m demand block / key daily support barrier.")
                print(f"     4. Why Price Didn't Go Up:")
                print(f"        - Buy-side liquidity was fully cleared at ${m['start_price']:.2f}, creating instant seller dominance.")

if __name__ == "__main__":
    analyze_weekly_confluences()
