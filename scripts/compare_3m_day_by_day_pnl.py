"""
3-Month Day-by-Day PnL Comparison Engine for Gold (XAU/USD).

Runs BOTH Model 1 (Standard Overlap) and Model 2 (Daily Open Bias Overlap)
across the past 3 months data (May 10, 2026 - Aug 10, 2026).
Outputs exact day-by-day PnL comparison table.
"""

import sys
from pathlib import Path
from datetime import datetime, date
import pandas as pd
import numpy as np
import time

def run_3m_day_by_day_comparison():
    proc_5m_path = Path("data/processed/xau_5m_5y.parquet")
    if not proc_5m_path.exists():
        print("[ERROR] 5m dataset missing!")
        return

    start_t = time.time()

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

    account_balance = 10000.0
    risk_pct = 0.01  # 1% Risk ($100 per trade)
    spread = 0.20    # $0.20 spread buffer

    # Model 1: Standard Overlap Model
    trades_m1 = []
    for d in target_dates:
        traded_today = False
        day_indices = np.where(dates_5m == d)[0]
        if len(day_indices) == 0: continue

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

            if bull_sweep:
                entry_price = c_close + spread
                sl = c_low - 1.20
                risk_dist = entry_price - sl
                day_high_so_far = np.max(highs_5m[day_indices[0]:i])
                target_tp = max(day_high_so_far, entry_price + 10.00)

                if risk_dist >= 0.80:
                    lots = (account_balance * risk_pct) / (risk_dist * 100.0)
                    traded_today = True

                    sl_hit, tp_hit = False, False
                    exit_p = closes_5m[min(i+12, n-1)]
                    for k in range(i+1, min(i+13, n)):
                        if lows_5m[k] <= sl:
                            sl_hit = True; exit_p = sl; break
                        elif highs_5m[k] >= target_tp:
                            tp_hit = True; exit_p = target_tp; break

                    if sl_hit:
                        trades_m1.append({'date': str(d), 'day': d.strftime('%a'), 'time': times_5m[i], 'type': 'BUY', 'entry': entry_price, 'sl': sl, 'tp': target_tp, 'pnl': -100.0, 'pips': (sl - entry_price)*10, 'win': False})
                    elif tp_hit:
                        pnl = lots * (target_tp - entry_price) * 100.0
                        trades_m1.append({'date': str(d), 'day': d.strftime('%a'), 'time': times_5m[i], 'type': 'BUY', 'entry': entry_price, 'sl': sl, 'tp': target_tp, 'pnl': pnl, 'pips': (target_tp - entry_price)*10, 'win': True})
                    else:
                        pnl = lots * (exit_p - entry_price) * 100.0
                        trades_m1.append({'date': str(d), 'day': d.strftime('%a'), 'time': times_5m[i], 'type': 'BUY', 'entry': entry_price, 'sl': sl, 'tp': target_tp, 'pnl': pnl, 'pips': (exit_p - entry_price)*10, 'win': (exit_p > entry_price)})

            elif bear_sweep:
                entry_price = c_close - spread
                sl = c_high + 1.20
                risk_dist = sl - entry_price
                day_low_so_far = np.min(lows_5m[day_indices[0]:i])
                target_tp = min(day_low_so_far, entry_price - 10.00)

                if risk_dist >= 0.80:
                    lots = (account_balance * risk_pct) / (risk_dist * 100.0)
                    traded_today = True

                    sl_hit, tp_hit = False, False
                    exit_p = closes_5m[min(i+12, n-1)]
                    for k in range(i+1, min(i+13, n)):
                        if highs_5m[k] >= sl:
                            sl_hit = True; exit_p = sl; break
                        elif lows_5m[k] <= target_tp:
                            tp_hit = True; exit_p = target_tp; break

                    if sl_hit:
                        trades_m1.append({'date': str(d), 'day': d.strftime('%a'), 'time': times_5m[i], 'type': 'SELL', 'entry': entry_price, 'sl': sl, 'tp': target_tp, 'pnl': -100.0, 'pips': (entry_price - sl)*10, 'win': False})
                    elif tp_hit:
                        pnl = lots * (entry_price - target_tp) * 100.0
                        trades_m1.append({'date': str(d), 'day': d.strftime('%a'), 'time': times_5m[i], 'type': 'SELL', 'entry': entry_price, 'sl': sl, 'tp': target_tp, 'pnl': pnl, 'pips': (entry_price - target_tp)*10, 'win': True})
                    else:
                        pnl = lots * (entry_price - exit_p) * 100.0
                        trades_m1.append({'date': str(d), 'day': d.strftime('%a'), 'time': times_5m[i], 'type': 'SELL', 'entry': entry_price, 'sl': sl, 'tp': target_tp, 'pnl': pnl, 'pips': (entry_price - exit_p)*10, 'win': (entry_price > exit_p)})

    # Model 2: Daily Open Bias Model
    trades_m2 = []
    for d in target_dates:
        traded_today = False
        day_indices = np.where(dates_5m == d)[0]
        if len(day_indices) == 0: continue
        daily_open_price = opens_5m[day_indices[0]]

        for i in day_indices:
            if traded_today: break
            if i < 15 or i >= n - 12: continue

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
                entry_price = c_close + spread
                sl = c_low - 1.20
                risk_dist = entry_price - sl
                day_high_so_far = np.max(highs_5m[day_indices[0]:i])
                target_tp = max(day_high_so_far, entry_price + 10.00)

                if risk_dist >= 0.80:
                    lots = (account_balance * risk_pct) / (risk_dist * 100.0)
                    traded_today = True

                    sl_hit, tp_hit = False, False
                    exit_p = closes_5m[min(i+12, n-1)]
                    for k in range(i+1, min(i+13, n)):
                        if lows_5m[k] <= sl:
                            sl_hit = True; exit_p = sl; break
                        elif highs_5m[k] >= target_tp:
                            tp_hit = True; exit_p = target_tp; break

                    if sl_hit:
                        trades_m2.append({'date': str(d), 'day': d.strftime('%a'), 'time': times_5m[i], 'type': 'BUY', 'entry': entry_price, 'sl': sl, 'tp': target_tp, 'pnl': -100.0, 'pips': (sl - entry_price)*10, 'win': False})
                    elif tp_hit:
                        pnl = lots * (target_tp - entry_price) * 100.0
                        trades_m2.append({'date': str(d), 'day': d.strftime('%a'), 'time': times_5m[i], 'type': 'BUY', 'entry': entry_price, 'sl': sl, 'tp': target_tp, 'pnl': pnl, 'pips': (target_tp - entry_price)*10, 'win': True})
                    else:
                        pnl = lots * (exit_p - entry_price) * 100.0
                        trades_m2.append({'date': str(d), 'day': d.strftime('%a'), 'time': times_5m[i], 'type': 'BUY', 'entry': entry_price, 'sl': sl, 'tp': target_tp, 'pnl': pnl, 'pips': (exit_p - entry_price)*10, 'win': (exit_p > entry_price)})

            elif bear_sweep:
                entry_price = c_close - spread
                sl = c_high + 1.20
                risk_dist = sl - entry_price
                day_low_so_far = np.min(lows_5m[day_indices[0]:i])
                target_tp = min(day_low_so_far, entry_price - 10.00)

                if risk_dist >= 0.80:
                    lots = (account_balance * risk_pct) / (risk_dist * 100.0)
                    traded_today = True

                    sl_hit, tp_hit = False, False
                    exit_p = closes_5m[min(i+12, n-1)]
                    for k in range(i+1, min(i+13, n)):
                        if highs_5m[k] >= sl:
                            sl_hit = True; exit_p = sl; break
                        elif lows_5m[k] <= target_tp:
                            tp_hit = True; exit_p = target_tp; break

                    if sl_hit:
                        trades_m2.append({'date': str(d), 'time': times_5m[i], 'type': 'SELL', 'entry': entry_price, 'sl': sl, 'tp': target_tp, 'pnl': -100.0, 'pips': (entry_price - sl)*10, 'win': False})
                    elif tp_hit:
                        pnl = lots * (entry_price - target_tp) * 100.0
                        trades_m2.append({'date': str(d), 'time': times_5m[i], 'type': 'SELL', 'entry': entry_price, 'sl': sl, 'tp': target_tp, 'pnl': pnl, 'pips': (entry_price - target_tp)*10, 'win': True})
                    else:
                        pnl = lots * (entry_price - exit_p) * 100.0
                        trades_m2.append({'date': str(d), 'time': times_5m[i], 'type': 'SELL', 'entry': entry_price, 'sl': sl, 'tp': target_tp, 'pnl': pnl, 'pips': (entry_price - exit_p)*10, 'win': (entry_price > exit_p)})

    df_m1 = pd.DataFrame(trades_m1)
    df_m2 = pd.DataFrame(trades_m2)

    elapsed = time.time() - start_t

    print("=" * 115)
    print(f" 3-MONTH DAY-BY-DAY PNL COMPARISON: MODEL 1 vs. MODEL 2 (MAY 10 - AUG 10, 2026) [{elapsed:.2f}s]")
    print("=" * 115)

    # Master performance summaries:
    n_m1, wins_m1 = len(df_m1), len(df_m1[df_m1['win'] == True])
    wr_m1 = (wins_m1 / n_m1 * 100.0) if n_m1 > 0 else 0
    gp_m1 = df_m1[df_m1['pnl'] > 0]['pnl'].sum() if not df_m1.empty else 0
    gl_m1 = abs(df_m1[df_m1['pnl'] < 0]['pnl'].sum()) if not df_m1.empty else 0
    pf_m1 = (gp_m1 / gl_m1) if gl_m1 > 0 else gp_m1
    net_m1 = df_m1['pnl'].sum() if not df_m1.empty else 0

    n_m2, wins_m2 = len(df_m2), len(df_m2[df_m2['win'] == True])
    wr_m2 = (wins_m2 / n_m2 * 100.0) if n_m2 > 0 else 0
    gp_m2 = df_m2[df_m2['pnl'] > 0]['pnl'].sum() if not df_m2.empty else 0
    gl_m2 = abs(df_m2[df_m2['pnl'] < 0]['pnl'].sum()) if not df_m2.empty else 0
    pf_m2 = (gp_m2 / gl_m2) if gl_m2 > 0 else gp_m2
    net_m2 = df_m2['pnl'].sum() if not df_m2.empty else 0

    print(f"\n  MASTER 3-MONTH BACKTEST SUMMARY:")
    print(f"  -----------------------------------------------------------------------------------------")
    print(f"  MODEL 1 (STANDARD OVERLAP):    Net PnL: ${net_m1:>+8.2f} ({net_m1/100:.2f}%) | Win Rate: {wr_m1:.1f}% ({wins_m1}/{n_m1}) | PF: {pf_m1:.2f}")
    print(f"  MODEL 2 (DAILY OPEN BIAS):    Net PnL: ${net_m2:>+8.2f} ({net_m2/100:.2f}%) | Win Rate: {wr_m2:.1f}% ({wins_m2}/{n_m2}) | PF: {pf_m2:.2f}")
    print(f"  -----------------------------------------------------------------------------------------\n")

    print(f" {'DATE & DAY':<22} | {'MODEL 1 (STANDARD OVERLAP)':<42} | {'MODEL 2 (DAILY OPEN BIAS)':<42}")
    print("-" * 115)

    all_d_strs = sorted(list(set(df_m1['date'].tolist() + df_m2['date'].tolist())))

    for d_str in all_d_strs:
        row_m1 = df_m1[df_m1['date'] == d_str]
        row_m2 = df_m2[df_m2['date'] == d_str]

        m1_str = "NO TRADE TRIGGERED"
        m2_str = "NO TRADE TRIGGERED"

        if not row_m1.empty:
            r = row_m1.iloc[0]
            res = "WIN" if r['win'] else "LOSS"
            m1_str = f"[{r['time']}] {r['type']} | Pips:{r['pips']:+6.1f} | {res:<4} (${r['pnl']:+.2f})"

        if not row_m2.empty:
            r = row_m2.iloc[0]
            res = "WIN" if r['win'] else "LOSS"
            m2_str = f"[{r['time']}] {r['type']} | Pips:{r['pips']:+6.1f} | {res:<4} (${r['pnl']:+.2f})"

        day_label = f"{d_str} ({row_m1.iloc[0]['day'] if not row_m1.empty else (row_m2.iloc[0]['day'] if not row_m2.empty else 'Day')})"
        print(f" {day_label:<22} | {m1_str:<42} | {m2_str:<42}")

    print("-" * 115)
    print(f" {'TOTAL CUMULATIVE PNL':<22} | ${net_m1:>+41.2f} | ${net_m2:>+41.2f}")
    print("-" * 115 + "\n")

if __name__ == "__main__":
    run_3m_day_by_day_comparison()
