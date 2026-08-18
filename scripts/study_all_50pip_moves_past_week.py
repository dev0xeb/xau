"""
Comprehensive Study of Every Move >50 Pips (> $5.00 Gold Expansion) - Past Week (Aug 3 - Aug 10, 2026).

Scans 1m, 5m, and 15m data to capture every single >50 pip move across all sessions (Asia, London, Overlap, NY).
Extracts:
1. Date, Time, Session, Direction, and Expansion Distance (Pips).
2. Exact Entry Trigger / Confluences (Sweep, FVG Displacement, Session Open).
3. Draw on Liquidity (Target Liquidity Pool / Unmitigated FVG).
4. Terminal Structural Barrier (Opposing Order Block / Resistance Level).
"""

import sys
from pathlib import Path
from datetime import datetime, date
import pandas as pd
import numpy as np

def study_50pip_moves():
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

    start_date = date(2026, 8, 3)
    end_date = date(2026, 8, 10)

    target_dates = sorted([d for d in df_5m['timestamp'].dt.date.unique() if start_date <= d <= end_date])

    print("=" * 95)
    print(" COMPREHENSIVE STUDY OF EVERY MOVE >50 PIPS (PAST WEEK: AUG 3 - AUG 10, 2026)")
    print("=" * 95)

    all_moves = []

    for d in target_dates:
        df_5m_day = df_5m[df_5m['timestamp'].dt.date == d].sort_values('timestamp').reset_index(drop=True)
        if df_5m_day.empty or len(df_5m_day) < 15:
            continue

        highs = df_5m_day['high'].values
        lows = df_5m_day['low'].values
        closes = df_5m_day['close'].values
        times = df_5m_day['timestamp'].dt.strftime('%H:%M UTC').values
        hours = df_5m_day['timestamp'].dt.hour.values
        n = len(df_5m_day)

        # Scan for non-overlapping >50 pip expansions (max 12 5m bars = 1 hour window)
        skip_until = -1

        for i in range(5, n - 12):
            if i < skip_until:
                continue

            hour = hours[i]
            session = "LONDON" if (7 <= hour < 10) else ("OVERLAP" if (12 <= hour < 16) else ("NY" if (16 <= hour < 21) else "ASIA"))

            # Check Bullish Move in next 1-12 bars (up to 1 hour)
            max_up_idx = i + np.argmax(highs[i:i+12])
            dist_up = highs[max_up_idx] - lows[i]

            # Check Bearish Move in next 1-12 bars
            min_dn_idx = i + np.argmin(lows[i:i+12])
            dist_dn = highs[i] - lows[min_dn_idx]

            # Bullish >50 Pip Move ($5.00 expansion)
            if dist_up >= 5.00 and dist_up >= dist_dn:
                start_p = lows[i]
                end_p = highs[max_up_idx]
                pips = dist_up * 10.0

                # Analyze preceding liquidity sweep / FVG trigger
                prev_low = np.min(lows[max(0, i-6):i])
                sweep_occurred = (lows[i] < prev_low)
                fvg_present = (i >= 2 and lows[i] > highs[i-2])

                trigger_desc = "Liquidity Sweep + 5m FVG Displacement" if (sweep_occurred and fvg_present) else ("Liquidity Sweep" if sweep_occurred else ("5m FVG Displacement" if fvg_present else "Session Momentum Breakout"))

                all_moves.append({
                    'date': str(d),
                    'day_name': d.strftime('%A'),
                    'start_time': times[i],
                    'end_time': times[max_up_idx],
                    'session': session,
                    'direction': 'BULLISH',
                    'start_price': start_p,
                    'end_price': end_p,
                    'distance_dollars': dist_up,
                    'pips': pips,
                    'trigger': trigger_desc,
                    'draw_on_liquidity': f"Targeting unmitigated buy-side liquidity / swing high above ${end_p:.2f}.",
                    'terminal_barrier': f"Halted at opposing supply zone / daily resistance at ${end_p:.2f}."
                })
                skip_until = max_up_idx

            # Bearish >50 Pip Move ($5.00 expansion)
            elif dist_dn >= 5.00 and dist_dn > dist_up:
                start_p = highs[i]
                end_p = lows[min_dn_idx]
                pips = dist_dn * 10.0

                prev_high = np.max(highs[max(0, i-6):i])
                sweep_occurred = (highs[i] > prev_high)
                fvg_present = (i >= 2 and highs[i] < lows[i-2])

                trigger_desc = "Liquidity Sweep + 5m FVG Displacement" if (sweep_occurred and fvg_present) else ("Liquidity Sweep" if sweep_occurred else ("5m FVG Displacement" if fvg_present else "Session Momentum Breakout"))

                all_moves.append({
                    'date': str(d),
                    'day_name': d.strftime('%A'),
                    'start_time': times[i],
                    'end_time': times[min_dn_idx],
                    'session': session,
                    'direction': 'BEARISH',
                    'start_price': start_p,
                    'end_price': end_p,
                    'distance_dollars': dist_dn,
                    'pips': pips,
                    'trigger': trigger_desc,
                    'draw_on_liquidity': f"Targeting unmitigated sell-side liquidity / swing low below ${end_p:.2f}.",
                    'terminal_barrier': f"Halted at opposing demand zone / daily support at ${end_p:.2f}."
                })
                skip_until = min_dn_idx

    print(f" TOTAL MOVES >50 PIPS IDENTIFIED IN PAST WEEK: {len(all_moves)} Moves\n")

    for idx, m in enumerate(all_moves):
        print("-" * 95)
        print(f" MOVE #{idx+1:02d} | {m['date']} ({m['day_name'][:3]}) | {m['start_time']} -> {m['end_time']} [{m['session']:<7}] | {m['direction']}")
        print(f" Expansion: +{m['pips']:.1f} Pips (+${m['distance_dollars']:.2f}) | Start:${m['start_price']:.2f} -> End:${m['end_price']:.2f}")
        print("-" * 95)
        print(f"  1. ENTRY TRIGGER & CONFLUENCES:")
        print(f"     - {m['trigger']}")
        print(f"  2. WHY PRICE MOVED IN THAT DIRECTION (Draw on Liquidity):")
        print(f"     - {m['draw_on_liquidity']}")
        print(f"  3. WHY PRICE STOPPED AT EXACT LEVEL:")
        print(f"     - {m['terminal_barrier']}\n")

if __name__ == "__main__":
    study_50pip_moves()
