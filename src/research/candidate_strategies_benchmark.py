"""
Ultra-Fast Single-Pass Multi-Year Candidate Strategy Benchmark Engine.

Evaluates 5 Candidate Strategies across 3 Years of 5m XAU/USD data (2023 - 2026):
1. Session Liquidity Sweep & Reversal Scalper
2. London/NY Overlap 15m ORB Breakout Engine
3. Daily Session Open Bias Trend Follower
4. 5m Displacement Candle Retrace Engine
5. Adaptive Market State Hybrid Engine

Execution Model:
- Spread: 20 points ($0.20)
- Slippage: $0.05 / trade
- Execution Costs Included
"""

import sys
from pathlib import Path
from datetime import datetime, date
import pandas as pd
import numpy as np
import time

def run_candidate_strategies_benchmark():
    proc_5m_path = Path("data/processed/xau_5m_5y.parquet")
    if not proc_5m_path.exists():
        print("[ERROR] 5m dataset missing!")
        return

    start_t = time.time()

    df_5m = pd.read_parquet(proc_5m_path)
    df_5m['timestamp'] = pd.to_datetime(df_5m['timestamp'])

    cutoff_date = pd.to_datetime("2023-01-01", utc=True)
    if df_5m['timestamp'].dt.tz is None:
        df_5m['timestamp'] = df_5m['timestamp'].dt.tz_localize('UTC')
    else:
        df_5m['timestamp'] = df_5m['timestamp'].dt.tz_convert('UTC')

    df_3y = df_5m[df_5m['timestamp'] >= cutoff_date].sort_values('timestamp').reset_index(drop=True)

    df_3y['hour'] = df_3y['timestamp'].dt.hour
    df_3y['minute'] = df_3y['timestamp'].dt.minute
    df_3y['date'] = df_3y['timestamp'].dt.date

    closes_5m = df_3y['close'].values
    opens_5m = df_3y['open'].values
    highs_5m = df_3y['high'].values
    lows_5m = df_3y['low'].values
    hours_5m = df_3y['hour'].values
    minutes_5m = df_3y['minute'].values
    dates_5m = df_3y['date'].values
    n = len(df_3y)

    account_balance = 10000.0
    risk_pct = 0.01  # 1% Risk per trade
    spread_cost = 0.20
    slippage_cost = 0.05

    # Group candle indices by date for ultra-fast single pass
    unique_dates, date_start_indices = np.unique(dates_5m, return_index=True)
    date_end_indices = np.append(date_start_indices[1:], n)

    trades_s1, trades_s2, trades_s3, trades_s4, trades_s5 = [], [], [], [], []

    for d_idx in range(len(unique_dates)):
        d = unique_dates[d_idx]
        start_i = date_start_indices[d_idx]
        end_i = date_end_indices[d_idx]

        daily_open_price = opens_5m[start_i]
        day_high_full = np.max(highs_5m[start_i:end_i])
        day_low_full = np.min(lows_5m[start_i:end_i])

        traded_s1, traded_s2, traded_s3, traded_s4, traded_s5 = False, False, False, False, False

        for i in range(start_i, end_i):
            if i < 15 or i >= n - 12: continue
            hour, minute = hours_5m[i], minutes_5m[i]
            c_open, c_high, c_low, c_close = opens_5m[i], highs_5m[i], lows_5m[i], closes_5m[i]

            prev_15m_high = np.max(highs_5m[max(0, i-6):i])
            prev_15m_low = np.min(lows_5m[max(0, i-6):i])

            in_overlap = ((hour == 12 and minute >= 20) or (13 <= hour <= 15))

            # --- S1: Session Liquidity Sweep ---
            if in_overlap and not traded_s1:
                bull_sig = (c_low < prev_15m_low) and (c_close > c_open)
                bear_sig = (c_high > prev_15m_high) and (c_close < c_open)
                if bull_sig or bear_sig:
                    traded_s1 = True
                    entry_p = (c_close + spread_cost + slippage_cost) if bull_sig else (c_close - spread_cost - slippage_cost)
                    sl = (c_low - 1.20) if bull_sig else (c_high + 1.20)
                    risk_d = (entry_p - sl) if bull_sig else (sl - entry_p)
                    target_tp = max(day_high_full, entry_p + 10.00) if bull_sig else min(day_low_full, entry_p - 10.00)
                    if risk_d >= 0.80:
                        lots = (account_balance * risk_pct) / (risk_d * 100.0)
                        fut_l, fut_h = lows_5m[i+1:min(i+13, n)], highs_5m[i+1:min(i+13, n)]
                        sl_h = np.any(fut_l <= sl) if bull_sig else np.any(fut_h >= sl)
                        tp_h = np.any(fut_h >= target_tp) if bull_sig else np.any(fut_l <= target_tp)
                        if sl_h: trades_s1.append(-100.0)
                        elif tp_h: trades_s1.append(lots * abs(target_tp - entry_p) * 100.0)
                        else: trades_s1.append(lots * ((closes_5m[min(i+12, n-1)] - entry_p) if bull_sig else (entry_p - closes_5m[min(i+12, n-1)])) * 100.0)

            # --- S2: 15m ORB Breakout ---
            if hour == 12 and minute == 20 and not traded_s2:
                orb_h = np.max(highs_5m[i-3:i])
                orb_l = np.min(lows_5m[i-3:i])
                bull_sig = (c_close > orb_h + 0.50)
                bear_sig = (c_close < orb_l - 0.50)
                if bull_sig or bear_sig:
                    traded_s2 = True
                    entry_p = (c_close + spread_cost + slippage_cost) if bull_sig else (c_close - spread_cost - slippage_cost)
                    sl = (c_low - 1.20) if bull_sig else (c_high + 1.20)
                    risk_d = (entry_p - sl) if bull_sig else (sl - entry_p)
                    target_tp = max(day_high_full, entry_p + 10.00) if bull_sig else min(day_low_full, entry_p - 10.00)
                    if risk_d >= 0.80:
                        lots = (account_balance * risk_pct) / (risk_d * 100.0)
                        fut_l, fut_h = lows_5m[i+1:min(i+13, n)], highs_5m[i+1:min(i+13, n)]
                        sl_h = np.any(fut_l <= sl) if bull_sig else np.any(fut_h >= sl)
                        tp_h = np.any(fut_h >= target_tp) if bull_sig else np.any(fut_l <= target_tp)
                        if sl_h: trades_s2.append(-100.0)
                        elif tp_h: trades_s2.append(lots * abs(target_tp - entry_p) * 100.0)
                        else: trades_s2.append(lots * ((closes_5m[min(i+12, n-1)] - entry_p) if bull_sig else (entry_p - closes_5m[min(i+12, n-1)])) * 100.0)

            # --- S3: Daily Session Open Bias ---
            if in_overlap and not traded_s3:
                bull_sig = (c_close > daily_open_price) and (c_low < prev_15m_low) and (c_close > c_open)
                bear_sig = (c_close < daily_open_price) and (c_high > prev_15m_high) and (c_close < c_open)
                if bull_sig or bear_sig:
                    traded_s3 = True
                    entry_p = (c_close + spread_cost + slippage_cost) if bull_sig else (c_close - spread_cost - slippage_cost)
                    sl = (c_low - 1.20) if bull_sig else (c_high + 1.20)
                    risk_d = (entry_p - sl) if bull_sig else (sl - entry_p)
                    target_tp = max(day_high_full, entry_p + 10.00) if bull_sig else min(day_low_full, entry_p - 10.00)
                    if risk_d >= 0.80:
                        lots = (account_balance * risk_pct) / (risk_d * 100.0)
                        fut_l, fut_h = lows_5m[i+1:min(i+13, n)], highs_5m[i+1:min(i+13, n)]
                        sl_h = np.any(fut_l <= sl) if bull_sig else np.any(fut_h >= sl)
                        tp_h = np.any(fut_h >= target_tp) if bull_sig else np.any(fut_l <= target_tp)
                        if sl_h: trades_s3.append(-100.0)
                        elif tp_h: trades_s3.append(lots * abs(target_tp - entry_p) * 100.0)
                        else: trades_s3.append(lots * ((closes_5m[min(i+12, n-1)] - entry_p) if bull_sig else (entry_p - closes_5m[min(i+12, n-1)])) * 100.0)

            # --- S4: 5m Displacement Retrace ---
            if (12 <= hour <= 16) and not traded_s4:
                body_len = abs(c_close - c_open)
                bull_sig = (body_len >= 3.00) and (c_close > c_open)
                bear_sig = (body_len >= 3.00) and (c_close < c_open)
                if bull_sig or bear_sig:
                    traded_s4 = True
                    entry_p = (c_close + spread_cost + slippage_cost) if bull_sig else (c_close - spread_cost - slippage_cost)
                    sl = (c_low - 1.20) if bull_sig else (c_high + 1.20)
                    risk_d = (entry_p - sl) if bull_sig else (sl - entry_p)
                    target_tp = max(day_high_full, entry_p + 10.00) if bull_sig else min(day_low_full, entry_p - 10.00)
                    if risk_d >= 0.80:
                        lots = (account_balance * risk_pct) / (risk_d * 100.0)
                        fut_l, fut_h = lows_5m[i+1:min(i+13, n)], highs_5m[i+1:min(i+13, n)]
                        sl_h = np.any(fut_l <= sl) if bull_sig else np.any(fut_h >= sl)
                        tp_h = np.any(fut_h >= target_tp) if bull_sig else np.any(fut_l <= target_tp)
                        if sl_h: trades_s4.append(-100.0)
                        elif tp_h: trades_s4.append(lots * abs(target_tp - entry_p) * 100.0)
                        else: trades_s4.append(lots * ((closes_5m[min(i+12, n-1)] - entry_p) if bull_sig else (entry_p - closes_5m[min(i+12, n-1)])) * 100.0)

            # --- S5: Adaptive Market State Hybrid ---
            if in_overlap and not traded_s5:
                session_exp = abs(c_close - daily_open_price)
                m1_bull = (c_low < prev_15m_low) and (c_close > c_open)
                m1_bear = (c_high > prev_15m_high) and (c_close < c_open)
                if session_exp >= 12.00:
                    bull_sig = (c_close > daily_open_price) and m1_bull
                    bear_sig = (c_close < daily_open_price) and m1_bear
                else:
                    bull_sig = m1_bull
                    bear_sig = m1_bear
                if bull_sig or bear_sig:
                    traded_s5 = True
                    entry_p = (c_close + spread_cost + slippage_cost) if bull_sig else (c_close - spread_cost - slippage_cost)
                    sl = (c_low - 1.20) if bull_sig else (c_high + 1.20)
                    risk_d = (entry_p - sl) if bull_sig else (sl - entry_p)
                    target_tp = max(day_high_full, entry_p + 10.00) if bull_sig else min(day_low_full, entry_p - 10.00)
                    if risk_d >= 0.80:
                        lots = (account_balance * risk_pct) / (risk_d * 100.0)
                        fut_l, fut_h = lows_5m[i+1:min(i+13, n)], highs_5m[i+1:min(i+13, n)]
                        sl_h = np.any(fut_l <= sl) if bull_sig else np.any(fut_h >= sl)
                        tp_h = np.any(fut_h >= target_tp) if bull_sig else np.any(fut_l <= target_tp)
                        if sl_h: trades_s5.append(-100.0)
                        elif tp_h: trades_s5.append(lots * abs(target_tp - entry_p) * 100.0)
                        else: trades_s5.append(lots * ((closes_5m[min(i+12, n-1)] - entry_p) if bull_sig else (entry_p - closes_5m[min(i+12, n-1)])) * 100.0)

    print("=========================================================================================")
    print(" PHASES 14-21 — CANDIDATE STRATEGIES MULTI-YEAR BENCHMARK SCORECARD (2023 - 2026)")
    print("=========================================================================================")

    all_trades = [trades_s1, trades_s2, trades_s3, trades_s4, trades_s5]
    names = [
        "1. Session Liquidity Sweep & Reversal",
        "2. London/NY Overlap 15m ORB Breakout",
        "3. Daily Session Open Bias Trend Follower",
        "4. 5m Displacement Candle Retrace Engine",
        "5. Adaptive Market State Hybrid Engine"
    ]

    results = []
    for k in range(5):
        df_tr = pd.DataFrame(all_trades[k], columns=['pnl'])
        if df_tr.empty:
            results.append({'Name': names[k], 'Trades': 0, 'WR': 0, 'PnL': 0, 'PF': 0, 'DD': 0})
            continue

        n_tr = len(df_tr)
        wins = len(df_tr[df_tr['pnl'] > 0])
        wr = (wins / n_tr) * 100.0
        gp = df_tr[df_tr['pnl'] > 0]['pnl'].sum()
        gl = abs(df_tr[df_tr['pnl'] < 0]['pnl'].sum())
        pf = (gp / gl) if gl > 0 else gp

        df_tr['eq'] = 10000.0 + df_tr['pnl'].cumsum()
        net_pnl = df_tr['eq'].iloc[-1] - 10000.0
        peak = df_tr['eq'].cummax()
        max_dd = abs(((df_tr['eq'] - peak) / peak * 100.0).min())

        results.append({'Name': names[k], 'Trades': n_tr, 'WR': wr, 'PnL': net_pnl, 'PF': pf, 'DD': max_dd})

    df_res = pd.DataFrame(results)
    print(f"\n {'STRATEGY CANDIDATE NAME':<42} | {'TRADES':<7} | {'WIN RATE':<8} | {'NET PNL ($)':<12} | {'PF':<6} | {'MAX DD':<7}")
    print("-" * 95)
    for idx, r in df_res.iterrows():
        print(f" {r['Name']:<42} | {r['Trades']:<7d} | {r['WR']:>6.1f}% | ${r['PnL']:>+10.2f} | {r['PF']:>5.2f} | -{r['DD']:>5.2f}%")

    elapsed = time.time() - start_t
    print("-" * 95)
    print(f" Completed Multi-Year Benchmark in {elapsed:.2f} seconds.")

if __name__ == "__main__":
    run_candidate_strategies_benchmark()
