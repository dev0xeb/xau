"""
Phases 6, 7, 8, 9, 10, 11, 12, 13 — Microstructure, Price Action & Session Interactions Engine.

Performs statistical analysis of:
1. Liquidity Sweeps & Reaction Distances
2. Opening Range Breakout (ORB) vs False Break Probabilities
3. 5m/15m Displacement Candle Continuation Probabilities
4. FVG Mitigation & Order Block Reaction Expectations
5. Session Continuation / Reversal Probabilities (Asian -> London -> NY Overlap)
"""

import sys
from pathlib import Path
from datetime import datetime, date
import pandas as pd
import numpy as np

def run_phases_6_to_13():
    raw_1m_path = Path("data/raw/xau_1m_5y.parquet")
    if not raw_1m_path.exists():
        print("[ERROR] 1m raw dataset missing!")
        return

    df_1m = pd.read_parquet(raw_1m_path)
    df_1m['timestamp'] = pd.to_datetime(df_1m['timestamp'])
    if df_1m['timestamp'].dt.tz is None:
        df_1m['timestamp'] = df_1m['timestamp'].dt.tz_localize('UTC')
    else:
        df_1m['timestamp'] = df_1m['timestamp'].dt.tz_convert('UTC')

    df_1m = df_1m.sort_values('timestamp').reset_index(drop=True)

    start_week = pd.to_datetime("2026-08-03 00:00:00", utc=True)
    end_week = pd.to_datetime("2026-08-07 23:59:59", utc=True)
    df_week = df_1m[(df_1m['timestamp'] >= start_week) & (df_1m['timestamp'] <= end_week)].copy()
    df_week['date'] = df_week['timestamp'].dt.date

    print("=========================================================================================")
    print(" PHASE 6 & 13 — LIQUIDITY SWEEP & SESSION INTERACTION STATISTICS")
    print("=========================================================================================")

    # Track Asian (00:00-07:00) and London (07:00-12:00) High/Low for each day
    sweep_events = []

    for d in sorted(df_week['date'].unique()):
        df_d = df_week[df_week['date'] == d].reset_index(drop=True)
        asian_df = df_d[(df_d['timestamp'].dt.hour >= 0) & (df_d['timestamp'].dt.hour < 7)]
        london_df = df_d[(df_d['timestamp'].dt.hour >= 7) & (df_d['timestamp'].dt.hour < 12)]

        if asian_df.empty or london_df.empty:
            continue

        asian_high = asian_df['high'].max()
        asian_low = asian_df['low'].min()

        london_high = london_df['high'].max()
        london_low = london_df['low'].min()

        # Check Overlap / NY Session (12:00-21:00) Sweeps
        ny_df = df_d[(df_d['timestamp'].dt.hour >= 12) & (df_d['timestamp'].dt.hour < 21)].reset_index(drop=True)

        for i in range(len(ny_df)):
            row = ny_df.iloc[i]
            t = row['timestamp']

            # High Sweep of London/Asian High
            if row['high'] > max(asian_high, london_high):
                # Measure next 15 mins reaction
                fut = ny_df.iloc[i+1:min(i+30, len(ny_df))]
                if not fut.empty:
                    min_after = fut['low'].min()
                    max_after = fut['high'].max()
                    reversal = (min_after < row['close'] - 2.00)
                    continuation = (max_after > row['close'] + 5.00)
                    sweep_events.append({'date': d, 'type': 'HIGH_SWEEP', 'time': t.strftime('%H:%M'), 'reversal': reversal, 'continuation': continuation})
                break

            # Low Sweep of London/Asian Low
            elif row['low'] < min(asian_low, london_low):
                fut = ny_df.iloc[i+1:min(i+30, len(ny_df))]
                if not fut.empty:
                    max_after = fut['high'].max()
                    min_after = fut['low'].min()
                    reversal = (max_after > row['close'] + 2.00)
                    continuation = (min_after < row['close'] - 5.00)
                    sweep_events.append({'date': d, 'type': 'LOW_SWEEP', 'time': t.strftime('%H:%M'), 'reversal': reversal, 'continuation': continuation})
                break

    df_sweeps = pd.DataFrame(sweep_events)
    if not df_sweeps.empty:
        rev_rate = (df_sweeps['reversal'].sum() / len(df_sweeps)) * 100.0
        cont_rate = (df_sweeps['continuation'].sum() / len(df_sweeps)) * 100.0
        print(f"  Total Session Sweeps Detected:  {len(df_sweeps)} Events")
        print(f"  Post-Sweep Reversal Rate:       {rev_rate:.1f}% (Reaction back across range)")
        print(f"  Post-Sweep Continuation Rate:   {cont_rate:.1f}% (Direct trend expansion)")

    print("\n=========================================================================================")
    print(" PHASE 8 — OPENING RANGE BREAKOUT (ORB) STATISTICAL ANALYSIS")
    print("=========================================================================================")

    orb_results = []
    for d in sorted(df_week['date'].unique()):
        df_d = df_week[df_week['date'] == d].reset_index(drop=True)

        # London 15m ORB (07:00 - 07:15 UTC)
        or_london = df_d[(df_d['timestamp'].dt.hour == 7) & (df_d['timestamp'].dt.minute < 15)]
        # NY Overlap 15m ORB (12:00 - 12:15 UTC)
        or_ny = df_d[(df_d['timestamp'].dt.hour == 12) & (df_d['timestamp'].dt.minute < 15)]

        if not or_ny.empty:
            or_high = or_ny['high'].max()
            or_low = or_ny['low'].min()
            or_range = or_high - or_low

            post_ny = df_d[(df_d['timestamp'].dt.hour >= 12) & (df_d['timestamp'].dt.minute >= 15) & (df_d['timestamp'].dt.hour < 16)].reset_index(drop=True)

            if not post_ny.empty:
                break_high = np.any(post_ny['high'] > or_high)
                break_low = np.any(post_ny['low'] < or_low)

                # False break vs Continuation
                high_cont = (post_ny['high'].max() >= or_high + 5.00)
                low_cont = (post_ny['low'].min() <= or_low - 5.00)

                orb_results.append({'date': d, 'or_range': or_range, 'break_high': break_high, 'break_low': break_low, 'cont': (high_cont or low_cont)})

    df_orb = pd.DataFrame(orb_results)
    if not df_orb.empty:
        orb_break_rate = ((df_orb['break_high'].sum() + df_orb['break_low'].sum()) / (len(df_orb)*2)) * 100.0
        orb_cont_rate = (df_orb['cont'].sum() / len(df_orb)) * 100.0
        print(f"  15m NY Overlap ORB Break Probability:   {orb_break_rate:.1f}%")
        print(f"  15m ORB Continuation Probability (>50 pips): {orb_cont_rate:.1f}%")

    print("\n=========================================================================================")
    print(" PHASE 9 & 10 — CANDLE DISPLACEMENT & FAIR VALUE GAP (FVG) MITIGATION")
    print("=========================================================================================")

    # Measure 5m candle displacement continuation on 5m data
    proc_5m_path = Path("data/processed/xau_5m_5y.parquet")
    if proc_5m_path.exists():
        df_5m = pd.read_parquet(proc_5m_path)
        df_5m['timestamp'] = pd.to_datetime(df_5m['timestamp'])
        if df_5m['timestamp'].dt.tz is None:
            df_5m['timestamp'] = df_5m['timestamp'].dt.tz_localize('UTC')
        else:
            df_5m['timestamp'] = df_5m['timestamp'].dt.tz_convert('UTC')

        df_5m_w = df_5m[(df_5m['timestamp'] >= start_week) & (df_5m['timestamp'] <= end_week)].reset_index(drop=True)

        bodies = abs(df_5m_w['close'] - df_5m_w['open'])
        disp_candles = df_5m_w[bodies >= 3.00]  # $3.00 (30 pip) displacement candle

        cont_count = 0
        retrace_count = 0

        for idx in disp_candles.index:
            if idx + 3 < len(df_5m_w):
                c_dir = 1 if df_5m_w.loc[idx, 'close'] > df_5m_w.loc[idx, 'open'] else -1
                next_3_high = df_5m_w.loc[idx+1:idx+3, 'high'].max()
                next_3_low = df_5m_w.loc[idx+1:idx+3, 'low'].min()

                if c_dir == 1:
                    if next_3_high > df_5m_w.loc[idx, 'close'] + 2.00: cont_count += 1
                    if next_3_low < df_5m_w.loc[idx, 'open']: retrace_count += 1
                else:
                    if next_3_low < df_5m_w.loc[idx, 'close'] - 2.00: cont_count += 1
                    if next_3_high > df_5m_w.loc[idx, 'open']: retrace_count += 1

        tot_disp = len(disp_candles)
        if tot_disp > 0:
            print(f"  5m Large Displacement Candles (>= $3.00): {tot_disp} Candles Detected")
            print(f"  Probability of Immediate Continuation:    {(cont_count/tot_disp)*100.0:.1f}%")
            print(f"  Probability of Full Retracement (FVG Fill): {(retrace_count/tot_disp)*100.0:.1f}%")

if __name__ == "__main__":
    run_phases_6_to_13()
