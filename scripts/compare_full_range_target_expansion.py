"""
Full Range Extreme Target Expansion Comparison Engine for Gold (XAU/USD).

Applies Full Range Extreme Target Expansion (targeting full session high/low extremes >= $10.00 / 100+ pips)
to BOTH:
1. Standard Overlap Model (No Lag)
2. Newest Daily Open Bias Overlap Model

Generates exact day-by-day PnL & Pip comparison for Monday Aug 3 - Monday Aug 10, 2026.
"""

import sys
from pathlib import Path
from datetime import datetime, date
import pandas as pd
import numpy as np

def run_full_range_expansion_comparison():
    proc_5m_path = Path("data/processed/xau_5m_5y.parquet")
    if not proc_5m_path.exists():
        print("[ERROR] 5m dataset missing!")
        return

    df_5m = pd.read_parquet(proc_5m_path)
    df_5m['timestamp'] = pd.to_datetime(df_5m['timestamp'])
    df_5m['hour'] = df_5m['timestamp'].dt.hour
    df_5m['minute'] = df_5m['timestamp'].dt.minute
    df_5m['date'] = df_5m['timestamp'].dt.date

    start_date = date(2026, 8, 3)
    end_date = date(2026, 8, 10)
    target_dates = sorted([d for d in df_5m['timestamp'].dt.date.unique() if start_date <= d <= end_date])

    closes_5m = df_5m['close'].values
    opens_5m = df_5m['open'].values
    highs_5m = df_5m['high'].values
    lows_5m = df_5m['low'].values
    times_5m = df_5m['timestamp'].dt.strftime('%H:%M UTC').values
    hours_5m = df_5m['hour'].values
    minutes_5m = df_5m['minute'].values
    dates_5m = df_5m['date'].values
    n = len(df_5m)

    account_balance = 10000.0
    risk_pct = 0.01  # 1% Risk ($100 per trade)

    # Model 1: Standard Overlap Model with FULL RANGE EXTREME TARGET EXPANSION
    trades_m1 = []
    for d in target_dates:
        traded_today = False
        day_indices = np.where(dates_5m == d)[0]
        if len(day_indices) == 0: continue

        for i in day_indices:
            if traded_today: break
            hour, minute = hours_5m[i], minutes_5m[i]
            if not ((hour == 12 and minute >= 20) or (13 <= hour <= 15)): continue

            c_open, c_high, c_low, c_close = opens_5m[i], highs_5m[i], lows_5m[i], closes_5m[i]
            prev_15m_high = np.max(highs_5m[max(0, i-6):i])
            prev_15m_low = np.min(lows_5m[max(0, i-6):i])

            bull_sweep = (c_low < prev_15m_low) and (c_close > c_open)
            bear_sweep = (c_high > prev_15m_high) and (c_close < c_open)

            if bull_sweep:
                sl = c_low - 1.20
                risk_dist = c_close - sl
                # FULL RANGE EXTREME TARGET: Target full daily high extreme
                day_high_so_far = np.max(highs_5m[day_indices[0]:i])
                target_tp = max(day_high_so_far, c_close + 10.00)

                if risk_dist >= 0.80:
                    lots = (account_balance * risk_pct) / (risk_dist * 100.0)
                    fut_h = highs_5m[i+1:min(i+12, n)]
                    fut_l = lows_5m[i+1:min(i+12, n)]
                    traded_today = True

                    if np.min(fut_l) <= sl:
                        trades_m1.append({'date': str(d), 'day': d.strftime('%A'), 'time': times_5m[i], 'type': 'BUY', 'entry': c_close, 'tp': target_tp, 'pnl': -100.0, 'pips': (sl - c_close)*10, 'win': False})
                    elif np.max(fut_h) >= target_tp:
                        pnl = lots * (target_tp - c_close) * 100.0
                        trades_m1.append({'date': str(d), 'day': d.strftime('%A'), 'time': times_5m[i], 'type': 'BUY', 'entry': c_close, 'tp': target_tp, 'pnl': pnl, 'pips': (target_tp - c_close)*10, 'win': True})
                    else:
                        exit_p = closes_5m[min(i+8, n-1)]
                        pnl = lots * (exit_p - c_close) * 100.0
                        trades_m1.append({'date': str(d), 'day': d.strftime('%A'), 'time': times_5m[i], 'type': 'BUY', 'entry': c_close, 'tp': target_tp, 'pnl': pnl, 'pips': (exit_p - c_close)*10, 'win': (exit_p > c_close)})

            elif bear_sweep:
                sl = c_high + 1.20
                risk_dist = sl - c_close
                day_low_so_far = np.min(lows_5m[day_indices[0]:i])
                target_tp = min(day_low_so_far, c_close - 10.00)

                if risk_dist >= 0.80:
                    lots = (account_balance * risk_pct) / (risk_dist * 100.0)
                    fut_h = highs_5m[i+1:min(i+12, n)]
                    fut_l = lows_5m[i+1:min(i+12, n)]
                    traded_today = True

                    if np.max(fut_h) >= sl:
                        trades_m1.append({'date': str(d), 'day': d.strftime('%A'), 'time': times_5m[i], 'type': 'SELL', 'entry': c_close, 'tp': target_tp, 'pnl': -100.0, 'pips': (c_close - sl)*10, 'win': False})
                    elif np.min(fut_l) <= target_tp:
                        pnl = lots * (c_close - target_tp) * 100.0
                        trades_m1.append({'date': str(d), 'day': d.strftime('%A'), 'time': times_5m[i], 'type': 'SELL', 'entry': c_close, 'tp': target_tp, 'pnl': pnl, 'pips': (c_close - target_tp)*10, 'win': True})
                    else:
                        exit_p = closes_5m[min(i+8, n-1)]
                        pnl = lots * (c_close - exit_p) * 100.0
                        trades_m1.append({'date': str(d), 'day': d.strftime('%A'), 'time': times_5m[i], 'type': 'SELL', 'entry': c_close, 'tp': target_tp, 'pnl': pnl, 'pips': (c_close - exit_p)*10, 'win': (c_close > exit_p)})

    # Model 2: Newest Daily Open Bias Model with FULL RANGE EXTREME TARGET EXPANSION
    trades_m2 = []
    for d in target_dates:
        traded_today = False
        day_indices = np.where(dates_5m == d)[0]
        if len(day_indices) == 0: continue
        daily_open_price = opens_5m[day_indices[0]]

        for i in day_indices:
            if traded_today: break
            hour, minute = hours_5m[i], minutes_5m[i]
            if not ((hour == 12 and minute >= 20) or (13 <= hour <= 15)): continue

            c_open, c_high, c_low, c_close = opens_5m[i], highs_5m[i], lows_5m[i], closes_5m[i]
            daily_bullish = (c_close > daily_open_price)
            daily_bearish = (c_close < daily_open_price)

            prev_15m_high = np.max(highs_5m[max(0, i-6):i])
            prev_15m_low = np.min(lows_5m[max(0, i-6):i])

            bull_sweep = daily_bullish and (c_low < prev_15m_low) and (c_close > c_open)
            bear_sweep = daily_bearish and (c_high > prev_15m_high) and (c_close < c_open)

            if bull_sweep:
                sl = c_low - 1.20
                risk_dist = c_close - sl
                day_high_so_far = np.max(highs_5m[day_indices[0]:i])
                target_tp = max(day_high_so_far, c_close + 10.00)

                if risk_dist >= 0.80:
                    lots = (account_balance * risk_pct) / (risk_dist * 100.0)
                    fut_h = highs_5m[i+1:min(i+12, n)]
                    fut_l = lows_5m[i+1:min(i+12, n)]
                    traded_today = True

                    if np.min(fut_l) <= sl:
                        trades_m2.append({'date': str(d), 'day': d.strftime('%A'), 'time': times_5m[i], 'type': 'BUY', 'entry': c_close, 'tp': target_tp, 'pnl': -100.0, 'pips': (sl - c_close)*10, 'win': False})
                    elif np.max(fut_h) >= target_tp:
                        pnl = lots * (target_tp - c_close) * 100.0
                        trades_m2.append({'date': str(d), 'day': d.strftime('%A'), 'time': times_5m[i], 'type': 'BUY', 'entry': c_close, 'tp': target_tp, 'pnl': pnl, 'pips': (target_tp - c_close)*10, 'win': True})
                    else:
                        exit_p = closes_5m[min(i+8, n-1)]
                        pnl = lots * (exit_p - c_close) * 100.0
                        trades_m2.append({'date': str(d), 'day': d.strftime('%A'), 'time': times_5m[i], 'type': 'BUY', 'entry': c_close, 'tp': target_tp, 'pnl': pnl, 'pips': (exit_p - c_close)*10, 'win': (exit_p > c_close)})
            elif bear_sweep:
                sl = c_high + 1.20
                risk_dist = sl - c_close
                day_low_so_far = np.min(lows_5m[day_indices[0]:i])
                target_tp = min(day_low_so_far, c_close - 10.00)

                if risk_dist >= 0.80:
                    lots = (account_balance * risk_pct) / (risk_dist * 100.0)
                    fut_h = highs_5m[i+1:min(i+12, n)]
                    fut_l = lows_5m[i+1:min(i+12, n)]
                    traded_today = True

                    if np.max(fut_h) >= sl:
                        trades_m2.append({'date': str(d), 'day': d.strftime('%A'), 'time': times_5m[i], 'type': 'SELL', 'entry': c_close, 'sl': sl, 'tp': target_tp, 'pnl': -100.0, 'pips': (c_close - sl)*10, 'win': False})
                    elif np.min(fut_l) <= target_tp:
                        pnl = lots * (c_close - target_tp) * 100.0
                        trades_m2.append({'date': str(d), 'day': d.strftime('%A'), 'time': times_5m[i], 'type': 'SELL', 'entry': c_close, 'sl': sl, 'tp': target_tp, 'pnl': pnl, 'pips': (c_close - target_tp)*10, 'win': True})
                    else:
                        exit_p = closes_5m[min(i+8, n-1)]
                        pnl = lots * (c_close - exit_p) * 100.0
                        trades_m2.append({'date': str(d), 'day': d.strftime('%A'), 'time': times_5m[i], 'type': 'SELL', 'entry': c_close, 'sl': sl, 'tp': target_tp, 'risk_dist': risk_dist, 'pnl': pnl, 'pips': (c_close - exit_p)*10, 'win': (c_close > exit_p)})

    df_m1 = pd.DataFrame(trades_m1)
    df_m2 = pd.DataFrame(trades_m2)

    print("=" * 115)
    print(" FULL RANGE EXTREME TARGET EXPANSION COMPARISON REPORT (AUG 3 - AUG 10, 2026)")
    print("=" * 115)

    print(f"\n {'DATE & DAY':<22} | {'STANDARD MODEL (EXPANDED TARGETS)':<42} | {'NEWEST OPEN BIAS MODEL (EXPANDED TARGETS)':<42}")
    print("-" * 115)

    all_d_strs = sorted(list(set(df_m1['date'].tolist() + df_m2['date'].tolist())))

    tot_pnl_m1 = 0.0
    tot_pnl_m2 = 0.0

    for d_str in all_d_strs:
        row_m1 = df_m1[df_m1['date'] == d_str]
        row_m2 = df_m2[df_m2['date'] == d_str]

        m1_str = "NO TRADE TRIGGERED"
        m2_str = "NO TRADE TRIGGERED"

        if not row_m1.empty:
            r = row_m1.iloc[0]
            res = "WIN" if r['win'] else "LOSS"
            m1_str = f"[{r['time']}] {r['type']} | Pips:{r['pips']:+6.1f} | {res:<4} (${r['pnl']:+.2f})"
            tot_pnl_m1 += r['pnl']

        if not row_m2.empty:
            r = row_m2.iloc[0]
            res = "WIN" if r['win'] else "LOSS"
            m2_str = f"[{r['time']}] {r['type']} | Pips:{r['pips']:+6.1f} | {res:<4} (${r['pnl']:+.2f})"
            tot_pnl_m2 += r['pnl']

        day_label = f"{d_str} ({row_m1.iloc[0]['day'][:3] if not row_m1.empty else (row_m2.iloc[0]['day'][:3] if not row_m2.empty else 'DAY')})"
        print(f" {day_label:<22} | {m1_str:<42} | {m2_str:<42}")

    print("-" * 115)
    print(f" {'TOTAL CUMULATIVE PNL':<22} | ${tot_pnl_m1:>+41.2f} | ${tot_pnl_m2:>+41.2f}")
    print("-" * 115 + "\n")

if __name__ == "__main__":
    run_full_range_expansion_comparison()
