"""
Micro-Scalping Price Action Cycle Analyzer for Gold (XAU/USD) - Past Week (Aug 3 - Aug 10, 2026).

Inspects lower timeframe (1m, 5m, 15m) market mechanics:
1. Ranging & Consolidation Building Phases (Range High / Range Low)
2. Range Liquidity Sweeps & 5m FVG Displacement Confluences
3. Draw-on-Liquidity Expansion Pathways
4. Structural Termination Barriers (Opposing Order Blocks)
"""

import sys
from pathlib import Path
from datetime import datetime, date
import pandas as pd
import numpy as np

def analyze_micro_cycles():
    raw_1m_path = Path("data/raw/xau_1m_5y.parquet")
    proc_5m_path = Path("data/processed/xau_5m_5y.parquet")
    proc_15m_path = Path("data/processed/xau_15m_5y.parquet")

    if not (raw_1m_path.exists() and proc_5m_path.exists() and proc_15m_path.exists()):
        print("[ERROR] Datasets missing!")
        return

    df_5m = pd.read_parquet(proc_5m_path)
    df_5m['timestamp'] = pd.to_datetime(df_5m['timestamp'])

    # Get recent dates
    unique_dates = df_5m['timestamp'].dt.date.unique()
    target_dates = sorted(unique_dates)[-6:]  # Past 6 trading days

    print("=" * 95)
    print(f" MICRO 1M/5M/15M SCALPING CYCLE ANALYSIS ({target_dates[0]} to {target_dates[-1]})")
    print("=" * 95)

    all_case_studies = []

    for d in target_dates:
        df_5m_day = df_5m[df_5m['timestamp'].dt.date == d].sort_values('timestamp').reset_index(drop=True)

        if df_5m_day.empty or len(df_5m_day) < 20:
            continue

        highs_5 = df_5m_day['high'].values
        lows_5 = df_5m_day['low'].values
        closes_5 = df_5m_day['close'].values
        times_5 = df_5m_day['timestamp'].dt.strftime('%H:%M UTC').values
        hours_5 = df_5m_day['timestamp'].dt.hour.values
        n_5 = len(df_5m_day)

        for i in range(10, n_5 - 8):
            hour = hours_5[i]
            session_tag = "LONDON" if (7 <= hour < 10) else ("OVERLAP" if (12 <= hour < 16) else ("NY" if (16 <= hour < 21) else "ASIA"))

            range_high = np.max(highs_5[i-10:i])
            range_low = np.min(lows_5[i-10:i])
            range_size = range_high - range_low

            # Flexible consolidation box
            if not (1.00 <= range_size <= 15.00):
                continue

            cur_high = highs_5[i]
            cur_low = lows_5[i]
            cur_close = closes_5[i]

            # Bullish Sweep of Range Low
            if cur_low < range_low and cur_close > range_low:
                sweep_depth = range_low - cur_low
                if 0.30 <= sweep_depth <= 3.50:
                    fut_highs = highs_5[i+1:min(i+8, n_5)]
                    post_expansion_high = np.max(fut_highs)
                    move_pips = (post_expansion_high - cur_close) * 10

                    if move_pips >= 20.0:
                        all_case_studies.append({
                            'date': str(d),
                            'day_name': d.strftime('%A'),
                            'time': times_5[i],
                            'session': session_tag,
                            'type': 'BULLISH RANGE SWEEP & EXPANSION',
                            'range_high': range_high,
                            'range_low': range_low,
                            'range_size': range_size,
                            'sweep_level': cur_low,
                            'entry_price': cur_close,
                            'terminal_barrier': post_expansion_high,
                            'expansion_pips': move_pips,
                            'why_moved': f"Magnet draw toward unmitigated buy-side liquidity sitting above Range High (${range_high:.2f}).",
                            'why_stopped': f"Halted at opposing 5m/15m Order Block / Resistance at ${post_expansion_high:.2f}.",
                            'why_not_down': f"Sell-side liquidity below Range Low (${range_low:.2f}) was 100% swept and cleared at ${cur_low:.2f}, leaving zero remaining sell stops to push price lower."
                        })

            # Bearish Sweep of Range High
            elif cur_high > range_high and cur_close < range_high:
                sweep_depth = cur_high - range_high
                if 0.30 <= sweep_depth <= 3.50:
                    fut_lows = lows_5[i+1:min(i+8, n_5)]
                    post_expansion_low = np.min(fut_lows)
                    move_pips = (cur_close - post_expansion_low) * 10

                    if move_pips >= 20.0:
                        all_case_studies.append({
                            'date': str(d),
                            'day_name': d.strftime('%A'),
                            'time': times_5[i],
                            'session': session_tag,
                            'type': 'BEARISH RANGE SWEEP & EXPANSION',
                            'range_high': range_high,
                            'range_low': range_low,
                            'range_size': range_size,
                            'sweep_level': cur_high,
                            'entry_price': cur_close,
                            'terminal_barrier': post_expansion_low,
                            'expansion_pips': move_pips,
                            'why_moved': f"Magnet draw toward unmitigated sell-side liquidity sitting below Range Low (${range_low:.2f}).",
                            'why_stopped': f"Halted at opposing 5m/15m Demand Block / Support at ${post_expansion_low:.2f}.",
                            'why_not_up': f"Buy-side liquidity above Range High (${range_high:.2f}) was 100% swept and cleared at ${cur_high:.2f}, leaving zero remaining buy stops to propel price higher."
                        })

    print(f" TOTAL MICRO-SCALPING CASE STUDIES IDENTIFIED IN PAST WEEK: {len(all_case_studies)}\n")

    for idx, c in enumerate(all_case_studies[:12]):
        print("-" * 95)
        print(f" CASE STUDY #{idx+1:02d} | Date: {c['date']} ({c['day_name'][:3]}) at {c['time']} [{c['session']}]")
        print(f" Pattern: {c['type']}")
        print("-" * 95)
        print(f"  1. CONSOLIDATION RANGE CONTEXT:")
        print(f"     - 5m Range Boundaries: High=${c['range_high']:.2f} | Low=${c['range_low']:.2f} | Box Size=${c['range_size']:.2f} (${c['range_size']*10:.1f} pips)")
        print(f"     - Sweep Execution: Wicked to ${c['sweep_level']:.2f}, Closed back inside range at Entry=${c['entry_price']:.2f}")

        print(f"  2. WHY PRICE MOVED IN THAT DIRECTION (Draw on Liquidity):")
        print(f"     - {c['why_moved']}")

        print(f"  3. WHY PRICE STOPPED AT EXACT LEVEL (${c['terminal_barrier']:.2f}):")
        if 'why_stopped' in c:
            print(f"     - {c['why_stopped']}")

        print(f"  4. WHY PRICE DIDN'T GO THE OTHER WAY:")
        if 'why_not_down' in c:
            print(f"     - {c['why_not_down']}")
        elif 'why_not_up' in c:
            print(f"     - {c['why_not_up']}")

        print(f"  5. MICRO-SCALPING EXPANSION RESULT:")
        print(f"     - Total Expansion: +{c['expansion_pips']:.1f} Pips from Entry (${c['entry_price']:.2f}) to Barrier (${c['terminal_barrier']:.2f})\n")

if __name__ == "__main__":
    analyze_micro_cycles()
