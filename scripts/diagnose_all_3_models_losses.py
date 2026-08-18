"""
Deep Empirical Loss Analysis Engine for All 3 Models (May 10 - Aug 10, 2026).

Analyzes:
1. Model 1 (Standard Sweep): 41 Losses
2. Model 2 (Daily Open Bias): 39 Losses
3. Master Hybrid Engine: 40 Losses

Extracts:
- Day of Week Loss Distribution
- Time Window Loss Distribution
- Volatility Range State (Low Chop < $15 vs High Spike > $35)
- Directional Loss Bias (BUY losses vs SELL losses)
- Structural Cause Breakdown
"""

import sys
from pathlib import Path
from datetime import datetime, date
import pandas as pd
import numpy as np

def run_loss_analysis():
    proc_5m_path = Path("data/processed/xau_5m_5y.parquet")
    if not proc_5m_path.exists():
        print("[ERROR] 5m dataset missing!")
        return

    df_5m = pd.read_parquet(proc_5m_path)
    df_5m['timestamp'] = pd.to_datetime(df_5m['timestamp'])

    cutoff_date = pd.to_datetime("2026-05-10", utc=True)
    df_5m_3m = df_5m[df_5m['timestamp'] >= cutoff_date].sort_values('timestamp').reset_index(drop=True)

    df_5m_3m['hour'] = df_5m_3m['timestamp'].dt.hour
    df_5m_3m['minute'] = df_5m_3m['timestamp'].dt.minute
    df_5m_3m['date'] = df_5m_3m['timestamp'].dt.date

    closes_5m = df_5m_3m['close'].values
    opens_5m = df_5m_3m['open'].values
    highs_5m = df_5m_3m['high'].values
    lows_5m = df_5m_3m['low'].values
    times_5m = df_5m_3m['timestamp'].dt.strftime('%H:%M UTC').values
    hours_5m = df_5m_3m['hour'].values
    minutes_5m = df_5m_3m['minute'].values
    dates_5m = df_5m_3m['date'].values
    n = len(df_5m_3m)

    target_dates = sorted(df_5m_3m['date'].unique())

    # --- MODEL 1 LOSSES ---
    losses_m1 = []
    for d in target_dates:
        traded_today = False
        day_indices = np.where(dates_5m == d)[0]
        if len(day_indices) == 0: continue
        daily_range = np.max(highs_5m[day_indices]) - np.min(lows_5m[day_indices])

        for i in day_indices:
            if traded_today: break
            if i < 15 or i >= n - 12: continue
            hour, minute = hours_5m[i], minutes_5m[i]
            if not ((hour == 12 and minute >= 20) or (13 <= hour <= 15)): continue

            c_open, c_high, c_low, c_close = opens_5m[i], highs_5m[i], lows_5m[i], closes_5m[i]
            prev_15m_high = np.max(highs_5m[max(0, i-6):i])
            prev_15m_low = np.min(lows_5m[max(0, i-6):i])

            bull_sweep = (c_low < prev_15m_low) and (c_close > c_open)
            bear_sweep = (c_high > prev_15m_high) and (c_close < c_open)

            if bull_sweep or bear_sweep:
                sl = (c_low - 1.20) if bull_sweep else (c_high + 1.20)
                risk_dist = (c_close - sl) if bull_sweep else (sl - c_close)
                if risk_dist >= 0.80:
                    traded_today = True
                    target_tp = max(np.max(highs_5m[day_indices[0]:i]), c_close + 10.0) if bull_sweep else min(np.min(lows_5m[day_indices[0]:i]), c_close - 10.0)

                    sl_hit = False
                    for k in range(i+1, min(i+13, n)):
                        if bull_sweep and lows_5m[k] <= sl: sl_hit = True; break
                        elif bear_sweep and highs_5m[k] >= sl: sl_hit = True; break
                        elif bull_sweep and highs_5m[k] >= target_tp: break
                        elif bear_sweep and lows_5m[k] <= target_tp: break

                    if sl_hit or (not sl_hit and ((bull_sweep and closes_5m[min(i+8, n-1)] < c_close) or (bear_sweep and closes_5m[min(i+8, n-1)] > c_close))):
                        losses_m1.append({'date': str(d), 'day': d.strftime('%A'), 'time': times_5m[i], 'type': 'BUY' if bull_sweep else 'SELL', 'range': daily_range, 'sl_dist': risk_dist})

    # --- MODEL 2 LOSSES ---
    losses_m2 = []
    for d in target_dates:
        traded_today = False
        day_indices = np.where(dates_5m == d)[0]
        if len(day_indices) == 0: continue
        daily_open_price = opens_5m[day_indices[0]]
        daily_range = np.max(highs_5m[day_indices]) - np.min(lows_5m[day_indices])

        for i in day_indices:
            if traded_today: break
            if i < 15 or i >= n - 12: continue
            hour, minute = hours_5m[i], minutes_5m[i]
            if not ((hour == 12 and minute >= 20) or (13 <= hour <= 15)): continue

            c_open, c_high, c_low, c_close = opens_5m[i], highs_5m[i], lows_5m[i], closes_5m[i]
            prev_15m_high = np.max(highs_5m[max(0, i-6):i])
            prev_15m_low = np.min(lows_5m[max(0, i-6):i])

            bull_sweep = (c_close > daily_open_price) and (c_low < prev_15m_low) and (c_close > c_open)
            bear_sweep = (c_close < daily_open_price) and (c_high > prev_15m_high) and (c_close < c_open)

            if bull_sweep or bear_sweep:
                sl = (c_low - 1.20) if bull_sweep else (c_high + 1.20)
                risk_dist = (c_close - sl) if bull_sweep else (sl - c_close)
                if risk_dist >= 0.80:
                    traded_today = True
                    target_tp = max(np.max(highs_5m[day_indices[0]:i]), c_close + 10.0) if bull_sweep else min(np.min(lows_5m[day_indices[0]:i]), c_close - 10.0)

                    sl_hit = False
                    for k in range(i+1, min(i+13, n)):
                        if bull_sweep and lows_5m[k] <= sl: sl_hit = True; break
                        elif bear_sweep and highs_5m[k] >= sl: sl_hit = True; break
                        elif bull_sweep and highs_5m[k] >= target_tp: break
                        elif bear_sweep and lows_5m[k] <= target_tp: break

                    if sl_hit or (not sl_hit and ((bull_sweep and closes_5m[min(i+8, n-1)] < c_close) or (bear_sweep and closes_5m[min(i+8, n-1)] > c_close))):
                        losses_m2.append({'date': str(d), 'day': d.strftime('%A'), 'time': times_5m[i], 'type': 'BUY' if bull_sweep else 'SELL', 'range': daily_range, 'sl_dist': risk_dist})

    # --- MASTER HYBRID LOSSES ---
    losses_hyb = []
    for d in target_dates:
        traded_today = False
        day_indices = np.where(dates_5m == d)[0]
        if len(day_indices) == 0: continue
        daily_open_price = opens_5m[day_indices[0]]
        daily_range = np.max(highs_5m[day_indices]) - np.min(lows_5m[day_indices])

        for i in day_indices:
            if traded_today: break
            if i < 15 or i >= n - 12: continue
            hour, minute = hours_5m[i], minutes_5m[i]
            if not ((hour == 12 and minute >= 20) or (13 <= hour <= 15)): continue

            c_open, c_high, c_low, c_close = opens_5m[i], highs_5m[i], lows_5m[i], closes_5m[i]
            session_expansion = abs(c_close - daily_open_price)
            is_trend_expansion = (session_expansion >= 12.00)

            prev_15m_high = np.max(highs_5m[max(0, i-6):i])
            prev_15m_low = np.min(lows_5m[max(0, i-6):i])

            m1_bull = (c_low < prev_15m_low) and (c_close > c_open)
            m1_bear = (c_high > prev_15m_high) and (c_close < c_open)
            m2_bull = (c_close > daily_open_price) and m1_bull
            m2_bear = (c_close < daily_open_price) and m1_bear

            bull_sig = m2_bull if is_trend_expansion else m1_bull
            bear_sig = m2_bear if is_trend_expansion else m1_bear

            if bull_sig or bear_sig:
                sl = (c_low - 1.20) if bull_sig else (c_high + 1.20)
                risk_dist = (c_close - sl) if bull_sig else (sl - c_close)
                if risk_dist >= 0.80:
                    traded_today = True
                    target_tp = max(np.max(highs_5m[day_indices[0]:i]), c_close + 10.0) if bull_sig else min(np.min(lows_5m[day_indices[0]:i]), c_close - 10.0)

                    sl_hit = False
                    for k in range(i+1, min(i+13, n)):
                        if bull_sig and lows_5m[k] <= sl: sl_hit = True; break
                        elif bear_sig and highs_5m[k] >= sl: sl_hit = True; break
                        elif bull_sig and highs_5m[k] >= target_tp: break
                        elif bear_sig and lows_5m[k] <= target_tp: break

                    if sl_hit or (not sl_hit and ((bull_sig and closes_5m[min(i+8, n-1)] < c_close) or (bear_sig and closes_5m[min(i+8, n-1)] > c_close))):
                        losses_hyb.append({'date': str(d), 'day': d.strftime('%A'), 'time': times_5m[i], 'type': 'BUY' if bull_sig else 'SELL', 'range': daily_range, 'sl_dist': risk_dist})

    df_l1 = pd.DataFrame(losses_m1)
    df_l2 = pd.DataFrame(losses_m2)
    df_lh = pd.DataFrame(losses_hyb)

    print("=" * 95)
    print(" DEEP EMPIRICAL LOSS ANALYSIS FOR ALL 3 MODELS (MAY 10 - AUG 10, 2026)")
    print("=" * 95)

    def print_model_loss_stats(name, df_l):
        print(f"\n --- {name} (TOTAL LOSSES: {len(df_l)}) ---")
        print("-" * 95)
        if df_l.empty:
            print("No losses.")
            return

        # 1. Day of Week Breakdown
        dow_cnt = df_l['day'].value_counts()
        print(f"  Day of Week Concentration:")
        for day, cnt in dow_cnt.items():
            print(f"     - {day:<10}: {cnt:2d} Losses ({cnt/len(df_l)*100:.1f}%)")

        # 2. Time Window Breakdown
        early_cnt = len(df_l[df_l['time'] < '13:00 UTC'])
        mid_cnt = len(df_l[(df_l['time'] >= '13:00 UTC') & (df_l['time'] <= '14:30 UTC')])
        late_cnt = len(df_l[df_l['time'] > '14:30 UTC'])
        print(f"  Time Window Concentration:")
        print(f"     - Early (12:20 - 12:55 UTC): {early_cnt:2d} Losses ({early_cnt/len(df_l)*100:.1f}%)")
        print(f"     - Mid   (13:00 - 14:30 UTC): {mid_cnt:2d} Losses ({mid_cnt/len(df_l)*100:.1f}%)")
        print(f"     - Late  (14:35 - 15:30 UTC): {late_cnt:2d} Losses ({late_cnt/len(df_l)*100:.1f}%)")

        # 3. Directional Breakdown
        buy_cnt = len(df_l[df_l['type'] == 'BUY'])
        sell_cnt = len(df_l[df_l['type'] == 'SELL'])
        print(f"  Directional Loss Bias:")
        print(f"     - BUY  Losses: {buy_cnt:2d} ({buy_cnt/len(df_l)*100:.1f}%)")
        print(f"     - SELL Losses: {sell_cnt:2d} ({sell_cnt/len(df_l)*100:.1f}%)")

        # 4. Volatility State Breakdown
        low_vol = len(df_l[df_l['range'] < 20.0])
        med_vol = len(df_l[(df_l['range'] >= 20.0) & (df_l['range'] <= 40.0)])
        high_vol = len(df_l[df_l['range'] > 40.0])
        print(f"  Daily Volatility State:")
        print(f"     - Low Volatility (< $20 Range):   {low_vol:2d} Losses ({low_vol/len(df_l)*100:.1f}%)")
        print(f"     - Medium Volatility ($20-$40):    {med_vol:2d} Losses ({med_vol/len(df_l)*100:.1f}%)")
        print(f"     - High Volatility (> $40 Range):  {high_vol:2d} Losses ({high_vol/len(df_l)*100:.1f}%)")

    print_model_loss_stats("MODEL 1: STANDARD OVERLAP SWEEP", df_l1)
    print_model_loss_stats("MODEL 2: DAILY OPEN BIAS", df_l2)
    print_model_loss_stats("MASTER HYBRID CONFLUENCE ENGINE", df_lh)

if __name__ == "__main__":
    run_loss_analysis()
