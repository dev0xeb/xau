"""
Diagnostic Tool for Analyzing Losing Scalp Trades (Past Week: Aug 3 - Aug 10, 2026).

Inspects all losing trades step-by-step to classify root causes:
1. Trend Expansion Expansion vs Counter-Trend Reversal
2. First-Sweep Trap (Double Sweep Hunt)
3. Stop Loss Buffer Insufficiency (Minor 1m Noise Wicks)
"""

import sys
from pathlib import Path
from datetime import datetime, date
import pandas as pd
import numpy as np

def analyze_losing_trades():
    proc_5m_path = Path("data/processed/xau_5m_5y.parquet")
    if not proc_5m_path.exists():
        print("[ERROR] 5m dataset missing!")
        return

    df_5m = pd.read_parquet(proc_5m_path)
    df_5m['timestamp'] = pd.to_datetime(df_5m['timestamp'])

    start_date = date(2026, 8, 3)
    end_date = date(2026, 8, 10)
    target_dates = sorted([d for d in df_5m['timestamp'].dt.date.unique() if start_date <= d <= end_date])

    closes_5m = df_5m['close'].values
    highs_5m = df_5m['high'].values
    lows_5m = df_5m['low'].values
    times_5m = df_5m['timestamp'].dt.strftime('%Y-%m-%d %H:%M UTC').values
    hours_5m = df_5m['timestamp'].dt.hour.values
    dates_5m = df_5m['timestamp'].dt.date.values
    n = len(df_5m)

    ema50_1h = pd.Series(closes_5m).ewm(span=144, adjust=False).mean().values

    losing_trades = []
    winning_trades = []

    for d in target_dates:
        df_day = df_5m[df_5m['timestamp'].dt.date == d].sort_values('timestamp').reset_index(drop=True)
        if df_day.empty or len(df_day) < 20:
            continue

        for i in range(20, len(df_5m) - 12):
            if dates_5m[i] != d:
                continue

            hour = hours_5m[i]
            session = "LONDON" if (7 <= hour < 10) else ("OVERLAP" if (12 <= hour < 16) else ("NY" if (16 <= hour < 21) else "ASIA"))

            range_high = np.max(highs_5m[i-10:i])
            range_low = np.min(lows_5m[i-10:i])
            range_size = range_high - range_low

            if not (1.50 <= range_size <= 12.00):
                continue

            c_high = highs_5m[i]
            c_low = lows_5m[i]
            c_close = closes_5m[i]

            htf_bull = c_close > ema50_1h[i]

            # Bullish Range Sweep Entry
            if c_low < range_low and c_close > range_low:
                sweep_depth = range_low - c_low
                if 0.40 <= sweep_depth <= 3.00:
                    sl = c_low - 0.50
                    risk = c_close - sl

                    if risk >= 0.80 and (range_high > c_close):
                        fut_highs = highs_5m[i+1:min(i+10, len(df_5m))]
                        fut_lows = lows_5m[i+1:min(i+10, len(df_5m))]

                        max_h = np.max(fut_highs)
                        min_l = np.min(fut_lows)

                        # Did price event hit SL?
                        if min_l <= sl:
                            # Root Cause Diagnosis:
                            # 1. Counter-Trend: Entering BUY when HTF trend is BEARISH
                            # 2. 2nd Sweep: Did price sweep again lower before expanding up?
                            # 3. Macro Expansion: Price broke out and continued down.
                            post_sl_max_h = np.max(highs_5m[i+1:min(i+20, len(df_5m))])
                            recovered_to_target = (post_sl_max_h >= range_high)

                            if not htf_bull:
                                cause = "COUNTER-TREND REVERSAL (Traded against 1H Bearish Trend)"
                            elif recovered_to_target:
                                cause = "STOP LOSS WHIPSAW / DOUBLE-SWEEP (SL hit, then ran to Target)"
                            else:
                                cause = "MACRO BREAKOUT CONTINOUS EXPANSION (Range failed)"

                            losing_trades.append({
                                'date': str(d),
                                'time': times_5m[i],
                                'session': session,
                                'type': 'BUY',
                                'entry': c_close,
                                'sl': sl,
                                'target': range_high,
                                'htf_trend': 'BULLISH' if htf_bull else 'BEARISH',
                                'cause': cause
                            })

            # Bearish Range Sweep Entry
            elif c_high > range_high and c_close < range_high:
                sweep_depth = c_high - range_high
                if 0.40 <= sweep_depth <= 3.00:
                    sl = c_high + 0.50
                    risk = sl - c_close

                    if risk >= 0.80 and (range_low < c_close):
                        fut_highs = highs_5m[i+1:min(i+10, len(df_5m))]
                        fut_lows = lows_5m[i+1:min(i+10, len(df_5m))]

                        max_h = np.max(fut_highs)
                        min_l = np.min(fut_lows)

                        if max_h >= sl:
                            post_sl_min_l = np.min(lows_5m[i+1:min(i+20, len(df_5m))])
                            recovered_to_target = (post_sl_min_l <= range_low)

                            if htf_bull:
                                cause = "COUNTER-TREND REVERSAL (Traded against 1H Bullish Trend)"
                            elif recovered_to_target:
                                cause = "STOP LOSS WHIPSAW / DOUBLE-SWEEP (SL hit, then ran to Target)"
                            else:
                                cause = "MACRO BREAKOUT CONTINOUS EXPANSION (Range failed)"

                            losing_trades.append({
                                'date': str(d),
                                'time': times_5m[i],
                                'session': session,
                                'type': 'SELL',
                                'entry': c_close,
                                'sl': sl,
                                'target': range_low,
                                'htf_trend': 'BULLISH' if htf_bull else 'BEARISH',
                                'cause': cause
                            })

    df_l = pd.DataFrame(losing_trades)
    print("=" * 95)
    print(f" DIAGNOSTIC REPORT: ANALYSIS OF {len(df_l)} LOSING TRADES (PAST WEEK: AUG 3 - AUG 10)")
    print("=" * 95)

    if df_l.empty:
        print("No losing trades found.")
        return

    cause_summary = df_l.groupby('cause').size().reset_index(name='count')
    cause_summary['percentage'] = (cause_summary['count'] / len(df_l)) * 100.0

    print("\n ROOT CAUSES WHY STOP LOSS WAS HIT:")
    print("-" * 95)
    for idx, r in cause_summary.iterrows():
        print(f"   {idx+1}. {r['cause']:<65}: {r['count']:<3} Losses ({r['percentage']:.1f}%)")

    print("\n DETAILED SAMPLE LOSING TRADE DIAGNOSTICS:")
    print("-" * 95)
    for idx, r in df_l.head(12).iterrows():
        print(f" Loss #{idx+1:02d} [{r['date']}] [{r['time']}] [{r['session']:<7}] {r['type']} | Entry:${r['entry']:.2f} | SL:${r['sl']:.2f} | Target:${r['target']:.2f}")
        print(f"         HTF Trend: {r['htf_trend']:<7} | Primary Cause: {r['cause']}\n")

if __name__ == "__main__":
    analyze_losing_trades()
