"""
Full Calendar Week Price Action Inspector for Gold (XAU/USD): Monday Aug 3 to Friday Aug 7, 2026.

Inspects all 5 trading days of the full previous week step-by-step, extracting:
1. Daily macro open, high, low, close, and total range.
2. Setup counts & session breakdowns (Asia, London, Overlap, NY).
3. Scalping setup performance (FVG Displacement vs Liquidity Sweep Reversals).
4. Top 10 high-yield scalping moves of the calendar week.
"""

import sys
from pathlib import Path
from datetime import datetime, date
import pandas as pd
import numpy as np

def inspect_calendar_week():
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

    # Monday Aug 3 to Friday Aug 7, 2026
    start_date = date(2026, 8, 3)
    end_date = date(2026, 8, 7)

    target_dates = [d for d in df_1m['timestamp'].dt.date.unique() if start_date <= d <= end_date]
    target_dates = sorted(target_dates)

    print("=" * 85)
    print(f" PREVIOUS CALENDAR WEEK PRICE ACTION INSPECTION (MONDAY AUG 3 - FRIDAY AUG 7, 2026)")
    print("=" * 85)

    weekly_moves = []

    for d in target_dates:
        df_1m_day = df_1m[df_1m['timestamp'].dt.date == d].sort_values('timestamp').reset_index(drop=True)
        df_5m_day = df_5m[df_5m['timestamp'].dt.date == d].sort_values('timestamp').reset_index(drop=True)
        
        if df_1m_day.empty or df_5m_day.empty:
            continue

        d_open = df_1m_day['open'].iloc[0]
        d_close = df_1m_day['close'].iloc[-1]
        d_high = df_1m_day['high'].max()
        d_low = df_1m_day['low'].min()
        d_range = d_high - d_low
        day_name = d.strftime('%A')

        print("\n" + "-" * 85)
        print(f" {day_name.upper()} {d} | Open: ${d_open:.2f} | High: ${d_high:.2f} | Low: ${d_low:.2f} | Close: ${d_close:.2f} | Range: ${d_range:.2f} ({d_range*10:.1f} pips)")
        print("-" * 85)

        highs_5 = df_5m_day['high'].values
        lows_5 = df_5m_day['low'].values
        closes_5 = df_5m_day['close'].values
        times_5 = df_5m_day['timestamp'].dt.strftime('%H:%M UTC').values
        hours_5 = df_5m_day['timestamp'].dt.hour.values
        n_5 = len(df_5m_day)

        day_moves = 0

        for i in range(2, n_5 - 4):
            hour = hours_5[i]
            session = "ASIA" if (hour < 7 or hour >= 21) else ("LONDON" if (7 <= hour < 12) else ("OVERLAP" if (12 <= hour < 16) else "NY"))

            # 1. Bullish Sweep
            prev_low_10 = np.min(lows_5[max(0, i-10):i])
            cur_low = lows_5[i]
            cur_close = closes_5[i]

            if cur_low < prev_low_10 and cur_close > prev_low_10:
                post_high = np.max(highs_5[i+1:min(i+7, n_5)])
                move_size = post_high - cur_close
                if move_size >= 3.0:
                    day_moves += 1
                    risk_amt = max(0.5, (cur_close - (cur_low - 0.50)))
                    weekly_moves.append({
                        'date': str(d),
                        'day_name': day_name,
                        'time': times_5[i],
                        'session': session,
                        'type': 'BULLISH SWEEP REVERSAL',
                        'entry': cur_close,
                        'sl': cur_low - 0.50,
                        'pips': move_size * 10,
                        'risk': risk_amt,
                        'rr': move_size / risk_amt
                    })

            # 2. Bearish Sweep
            prev_high_10 = np.max(highs_5[max(0, i-10):i])
            cur_high = highs_5[i]
            if cur_high > prev_high_10 and cur_close < prev_high_10:
                post_low = np.min(lows_5[i+1:min(i+7, n_5)])
                move_size = cur_close - post_low
                if move_size >= 3.0:
                    day_moves += 1
                    risk_amt = max(0.5, ((cur_high + 0.50) - cur_close))
                    weekly_moves.append({
                        'date': str(d),
                        'day_name': day_name,
                        'time': times_5[i],
                        'session': session,
                        'type': 'BEARISH SWEEP REVERSAL',
                        'entry': cur_close,
                        'sl': cur_high + 0.50,
                        'pips': move_size * 10,
                        'risk': risk_amt,
                        'rr': move_size / risk_amt
                    })

            # 3. Bullish 5m FVG
            if lows_5[i] > highs_5[i-2]:
                gap = lows_5[i] - highs_5[i-2]
                if gap >= 0.50:
                    fvg_mid = (lows_5[i] + highs_5[i-2]) / 2.0
                    post_high = np.max(highs_5[i+1:min(i+7, n_5)])
                    move_size = post_high - fvg_mid
                    if move_size >= 3.0:
                        day_moves += 1
                        risk_amt = max(0.5, (fvg_mid - (highs_5[i-2] - 0.50)))
                        weekly_moves.append({
                            'date': str(d),
                            'day_name': day_name,
                            'time': times_5[i],
                            'session': session,
                            'type': 'BULLISH FVG DISPLACEMENT',
                            'entry': fvg_mid,
                            'sl': highs_5[i-2] - 0.50,
                            'pips': move_size * 10,
                            'risk': risk_amt,
                            'rr': move_size / risk_amt
                        })

            # 4. Bearish 5m FVG
            elif highs_5[i] < lows_5[i-2]:
                gap = lows_5[i-2] - highs_5[i]
                if gap >= 0.50:
                    fvg_mid = (lows_5[i-2] + highs_5[i]) / 2.0
                    post_low = np.min(lows_5[i+1:min(i+7, n_5)])
                    move_size = fvg_mid - post_low
                    if move_size >= 3.0:
                        day_moves += 1
                        risk_amt = max(0.5, ((lows_5[i-2] + 0.50) - fvg_mid))
                        weekly_moves.append({
                            'date': str(d),
                            'day_name': day_name,
                            'time': times_5[i],
                            'session': session,
                            'type': 'BEARISH FVG DISPLACEMENT',
                            'entry': fvg_mid,
                            'sl': lows_5[i-2] + 0.50,
                            'pips': move_size * 10,
                            'risk': risk_amt,
                            'rr': move_size / risk_amt
                        })

        print(f"  -> Total Scalping Moves (>= 30 pips) on {day_name} {d}: {day_moves}")

    df_wm = pd.DataFrame(weekly_moves)
    print("\n" + "=" * 85)
    print(f" FULL CALENDAR WEEK SUMMARY (AUG 3 - AUG 7): TOTAL MOVES = {len(df_wm)}")
    print("=" * 85)

    if not df_wm.empty:
        sess_summary = df_wm.groupby('session')['pips'].agg(['count', 'mean', 'max']).reset_index()
        print("\n Scalping Moves by Session Window:")
        for _, r in sess_summary.iterrows():
            print(f"   - {r['session']:<8}: Count={r['count']} moves | Avg Expansion=+{r['mean']:.1f} pips | Max Expansion=+{r['max']:.1f} pips")

        type_summary = df_wm.groupby('type')['rr'].agg(['count', 'mean', 'max']).reset_index()
        print("\n Setup Performance Breakdown:")
        for _, r in type_summary.iterrows():
            print(f"   - {r['type']:<26}: Count={r['count']} | Avg RR=1:{r['mean']:.1f} | Max RR=1:{r['max']:.1f}")

        print("\n Top 10 Scalping Moves of Calendar Week (Aug 3 - Aug 7):")
        top_10 = df_wm.sort_values('pips', ascending=False).head(10)
        for idx, r in top_10.iterrows():
            print(f"   [{r['date']} ({r['day_name'][:3]})] [{r['time']}] [{r['session']:<7}] {r['type']:<26} | Entry:${r['entry']:.2f} | SL:${r['sl']:.2f} | Expansion:+{r['pips']:.1f} pips | RR=1:{r['rr']:.1f}")

if __name__ == "__main__":
    inspect_calendar_week()
