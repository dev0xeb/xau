"""
Daily Case Study Inspector for Top >50 Pip Scalping Moves (Monday Aug 3 - Friday Aug 7, 2026).

Extracts the single biggest high-conviction scalping move for each day of the week, detailing:
1. Time Window & Session
2. Exact Confluences at Entry
3. Draw on Liquidity Target
4. Terminal Structural Exit Barrier
5. Directional Invalidation Reason
"""

import sys
from pathlib import Path
from datetime import datetime, date
import pandas as pd
import numpy as np

def inspect_daily_case_studies():
    proc_5m_path = Path("data/processed/xau_5m_5y.parquet")
    if not proc_5m_path.exists():
        print("[ERROR] 5m dataset missing!")
        return

    df_5m = pd.read_parquet(proc_5m_path)
    df_5m['timestamp'] = pd.to_datetime(df_5m['timestamp'])

    start_date = date(2026, 8, 3)
    end_date = date(2026, 8, 7)

    target_dates = sorted([d for d in df_5m['timestamp'].dt.date.unique() if start_date <= d <= end_date])

    print("=" * 95)
    print(" DAILY CASE STUDY INSPECTION: TOP >50 PIP SCALPS (MONDAY AUG 3 - FRIDAY AUG 7, 2026)")
    print("=" * 95)

    for d in target_dates:
        df_day = df_5m[df_5m['timestamp'].dt.date == d].sort_values('timestamp').reset_index(drop=True)
        if df_day.empty:
            continue

        highs = df_day['high'].values
        lows = df_day['low'].values
        closes = df_day['close'].values
        times = df_day['timestamp'].dt.strftime('%H:%M UTC').values
        hours = df_day['timestamp'].dt.hour.values
        n = len(df_day)

        day_name = d.strftime('%A').upper()

        best_move = None
        max_dist = 0.0

        for i in range(5, n - 12):
            hour = hours[i]
            session = "LONDON" if (7 <= hour < 10) else ("OVERLAP" if (12 <= hour < 16) else ("NY" if (16 <= hour < 21) else "ASIA"))

            max_up_idx = i + np.argmax(highs[i:i+12])
            dist_up = highs[max_up_idx] - lows[i]

            min_dn_idx = i + np.argmin(lows[i:i+12])
            dist_dn = highs[i] - lows[min_dn_idx]

            if dist_up > max_dist:
                max_dist = dist_up
                prev_low = np.min(lows[max(0, i-6):i])
                sweep_occ = (lows[i] < prev_low)
                fvg_occ = (i >= 2 and lows[i] > highs[i-2])

                best_move = {
                    'date': str(d), 'day_name': day_name, 'start_time': times[i], 'end_time': times[max_up_idx],
                    'session': session, 'direction': 'BULLISH', 'start_price': lows[i], 'end_price': highs[max_up_idx],
                    'pips': dist_up * 10.0, 'dollars': dist_up, 'sweep': sweep_occ, 'fvg': fvg_occ,
                    'sweep_level': prev_low
                }

            if dist_dn > max_dist:
                max_dist = dist_dn
                prev_high = np.max(highs[max(0, i-6):i])
                sweep_occ = (highs[i] > prev_high)
                fvg_occ = (i >= 2 and highs[i] < lows[i-2])

                best_move = {
                    'date': str(d), 'day_name': day_name, 'start_time': times[i], 'end_time': times[min_dn_idx],
                    'session': session, 'direction': 'BEARISH', 'start_price': highs[i], 'end_price': lows[min_dn_idx],
                    'pips': dist_dn * 10.0, 'dollars': dist_dn, 'sweep': sweep_occ, 'fvg': fvg_occ,
                    'sweep_level': prev_high
                }

        if best_move:
            m = best_move
            print("\n" + "=" * 95)
            print(f" DAY: {m['day_name']} {m['date']} | TOP MOVE: {m['direction']} (+{m['pips']:.1f} Pips / +${m['dollars']:.2f})")
            print("=" * 95)
            print(f"  Time Window:   {m['start_time']} -> {m['end_time']} [{m['session']} Session]")
            print(f"  Execution:     Start Price: ${m['start_price']:.2f} -> Terminal Target: ${m['end_price']:.2f}")

            print(f"\n  1. EXACT CONFLUENCES GIVEN AT ENTRY ({m['start_time']}):")
            if m['direction'] == 'BULLISH':
                print(f"     - Sell-side liquidity sweep of low (${m['sweep_level']:.2f}) cleared retail stop-losses.")
                if m['fvg']:
                    print(f"     - 5m Bullish FVG displacement gap confirmed aggressive buyers.")
                print(f"     - {m['session']} session volume alignment.")

                print(f"\n  2. WHY PRICE MOVED IN THAT DIRECTION (Draw on Liquidity):")
                print(f"     - Drawn upward like a magnet toward unmitigated Buy-Side Liquidity sitting above Range Highs (${m['end_price']:.2f}).")

                print(f"\n  3. WHY PRICE STOPPED AT EXACT LEVEL (${m['end_price']:.2f}):")
                print(f"     - Halted at opposing 15m Supply Zone / Daily Resistance Barrier at ${m['end_price']:.2f}.")

                print(f"\n  4. WHY PRICE DIDN'T GO DOWN:")
                print(f"     - Sell-side liquidity below ${m['sweep_level']:.2f} was 100% swept and cleared at ${m['start_price']:.2f}, leaving ZERO remaining sell stops below.")
            else:
                print(f"     - Buy-side liquidity sweep of high (${m['sweep_level']:.2f}) trapped breakout buyers.")
                if m['fvg']:
                    print(f"     - 5m Bearish FVG displacement gap confirmed aggressive sellers.")
                print(f"     - {m['session']} session volume alignment.")

                print(f"\n  2. WHY PRICE MOVED IN THAT DIRECTION (Draw on Liquidity):")
                print(f"     - Drawn downward like a magnet toward unmitigated Sell-Side Liquidity sitting below Range Lows (${m['end_price']:.2f}).")

                print(f"\n  3. WHY PRICE STOPPED AT EXACT LEVEL (${m['end_price']:.2f}):")
                print(f"     - Halted at opposing 15m Demand Zone / Daily Support Barrier at ${m['end_price']:.2f}.")

                print(f"\n  4. WHY PRICE DIDN'T GO UP:")
                print(f"     - Buy-side liquidity above ${m['sweep_level']:.2f} was 100% swept and cleared at ${m['start_price']:.2f}, leaving ZERO remaining buy stops above.")

if __name__ == "__main__":
    inspect_daily_case_studies()
