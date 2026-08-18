"""
3-Month Backtest for Partial Take-Profit & Trailing Engine (May 10 - Aug 10, 2026).

Execution Strategy:
1. 50% Partial Take-Profit at +$5.00 (+50 pips) -> Instantly locks in +$250 cash (+2.5%).
2. Move SL to BE after 50% TP hit.
3. Remaining 50% runs to Full 15m Range Extreme / Session Target.
"""

import sys
from pathlib import Path
from datetime import datetime, date
import pandas as pd
import numpy as np
import time

def run_3m_partial_tp_engine():
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
    times_5m = df_5m_3m['timestamp'].dt.strftime('%Y-%m-%d %H:%M UTC').values
    hours_5m = df_5m_3m['hour'].values
    minutes_5m = df_5m_3m['minute'].values
    dates_5m = df_5m_3m['date'].values
    n = len(df_5m_3m)

    target_dates = sorted(df_5m_3m['date'].unique())

    trades = []
    account_balance = 10000.0
    risk_pct = 0.01  # 1% Risk ($100 per trade)
    spread = 0.20    # $0.20 spread buffer

    for d in target_dates:
        traded_today = False
        day_indices = np.where(dates_5m == d)[0]
        if len(day_indices) == 0: continue

        daily_open_price = opens_5m[day_indices[0]]

        for i in day_indices:
            if traded_today: break
            if i < 15 or i >= n - 12: continue

            hour, minute = hours_5m[i], minutes_5m[i]
            # OVERLAP WINDOW: 12:20 UTC to 15:30 UTC ONLY
            if not ((hour == 12 and minute >= 20) or (13 <= hour <= 15)): continue

            c_open, c_high, c_low, c_close = opens_5m[i], highs_5m[i], lows_5m[i], closes_5m[i]

            prev_15m_high = np.max(highs_5m[max(0, i-6):i])
            prev_15m_low = np.min(lows_5m[max(0, i-6):i])

            bull_sweep = (c_low < prev_15m_low) and (c_close > c_open)
            bear_sweep = (c_high > prev_15m_high) and (c_close < c_open)

            # Master Router
            session_expansion = abs(c_close - daily_open_price)
            if session_expansion >= 12.00:
                bull_sig = (c_close > daily_open_price) and bull_sweep
                bear_sig = (c_close < daily_open_price) and bear_sweep
            else:
                bull_sig = bull_sweep
                bear_sig = bear_sweep

            if bull_sig:
                entry_price = c_close + spread
                sl = c_low - 1.20
                risk_dist = entry_price - sl

                day_high_so_far = np.max(highs_5m[day_indices[0]:i])
                target_tp = max(day_high_so_far, entry_price + 10.00)

                if risk_dist >= 0.80:
                    lots = (account_balance * risk_pct) / (risk_dist * 100.0)
                    traded_today = True

                    sl_hit, tp_hit = False, False
                    partial_taken = False
                    partial_pnl = 0.0
                    current_sl = sl

                    exit_p = closes_5m[min(i+12, n-1)]

                    for k in range(i+1, min(i+13, n)):
                        # Check Partial 50% TP at + $5.00
                        if not partial_taken and highs_5m[k] >= entry_price + 5.00:
                            partial_taken = True
                            partial_pnl = (lots * 0.5) * (5.00) * 100.0
                            current_sl = entry_price + 0.20  # SL moved to BE

                        if lows_5m[k] <= current_sl:
                            sl_hit = True
                            exit_p = current_sl
                            break
                        elif highs_5m[k] >= target_tp:
                            tp_hit = True
                            exit_p = target_tp
                            break

                    if partial_taken:
                        if tp_hit:
                            rem_pnl = (lots * 0.5) * (target_tp - entry_price) * 100.0
                        else:
                            rem_pnl = (lots * 0.5) * (exit_p - entry_price) * 100.0
                        total_trade_pnl = partial_pnl + rem_pnl
                        trades.append({'date': str(d), 'time': times_5m[i], 'type': 'BUY', 'entry': entry_price, 'pnl_dollar': total_trade_pnl, 'win': True, 'res': 'PARTIAL + WIN'})
                    elif sl_hit:
                        trades.append({'date': str(d), 'time': times_5m[i], 'type': 'BUY', 'entry': entry_price, 'pnl_dollar': -100.0, 'win': False, 'res': 'FULL LOSS'})
                    else:
                        pnl_val = lots * (exit_p - entry_price) * 100.0
                        trades.append({'date': str(d), 'time': times_5m[i], 'type': 'BUY', 'entry': entry_price, 'pnl_dollar': pnl_val, 'win': (exit_p > entry_price), 'res': 'EXPIRE'})

            elif bear_sig:
                entry_price = c_close - spread
                sl = c_high + 1.20
                risk_dist = sl - entry_price

                day_low_so_far = np.min(lows_5m[day_indices[0]:i])
                target_tp = min(day_low_so_far, entry_price - 10.00)

                if risk_dist >= 0.80:
                    lots = (account_balance * risk_pct) / (risk_dist * 100.0)
                    traded_today = True

                    sl_hit, tp_hit = False, False
                    partial_taken = False
                    partial_pnl = 0.0
                    current_sl = sl

                    exit_p = closes_5m[min(i+12, n-1)]

                    for k in range(i+1, min(i+13, n)):
                        # Check Partial 50% TP at - $5.00
                        if not partial_taken and lows_5m[k] <= entry_price - 5.00:
                            partial_taken = True
                            partial_pnl = (lots * 0.5) * (5.00) * 100.0
                            current_sl = entry_price - 0.20

                        if highs_5m[k] >= current_sl:
                            sl_hit = True
                            exit_p = current_sl
                            break
                        elif lows_5m[k] <= target_tp:
                            tp_hit = True
                            exit_p = target_tp
                            break

                    if partial_taken:
                        if tp_hit:
                            rem_pnl = (lots * 0.5) * (entry_price - target_tp) * 100.0
                        else:
                            rem_pnl = (lots * 0.5) * (entry_price - exit_p) * 100.0
                        total_trade_pnl = partial_pnl + rem_pnl
                        trades.append({'date': str(d), 'time': times_5m[i], 'type': 'SELL', 'entry': entry_price, 'pnl_dollar': total_trade_pnl, 'win': True, 'res': 'PARTIAL + WIN'})
                    elif sl_hit:
                        trades.append({'date': str(d), 'time': times_5m[i], 'type': 'SELL', 'entry': entry_price, 'pnl_dollar': -100.0, 'win': False, 'res': 'FULL LOSS'})
                    else:
                        pnl_val = lots * (entry_price - exit_p) * 100.0
                        trades.append({'date': str(d), 'time': times_5m[i], 'type': 'SELL', 'entry': entry_price, 'pnl_dollar': pnl_val, 'win': (entry_price > exit_p), 'res': 'EXPIRE'})

    elapsed = time.time() - start_t

    df_t = pd.DataFrame(trades)
    print("=" * 95)
    print(f" PARTIAL TAKE-PROFIT 3-MONTH REPORT (MAY 10 - AUG 10, 2026) [{elapsed:.2f}s]")
    print("=" * 95)

    if df_t.empty:
        print("No trades triggered.")
        return

    total_trades = len(df_t)
    wins = len(df_t[df_t['win'] == True])
    win_rate = (wins / total_trades) * 100.0

    gross_profit = df_t[df_t['pnl_dollar'] > 0]['pnl_dollar'].sum()
    gross_loss = abs(df_t[df_t['pnl_dollar'] < 0]['pnl_dollar'].sum())
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else gross_profit

    df_t['equity'] = 10000.0 + df_t['pnl_dollar'].cumsum()
    net_pnl = df_t['equity'].iloc[-1] - 10000.0
    net_pct = (net_pnl / 10000.0) * 100.0

    peak = df_t['equity'].cummax()
    dd = (df_t['equity'] - peak) / peak * 100.0
    max_dd_pct = abs(dd.min())

    print(f"  Initial Balance:          $10,000.00")
    print(f"  Final Equity:             ${df_t['equity'].iloc[-1]:,.2f}")
    print(f"  Net Profit:               ${net_pnl:,.2f} ({net_pct:+.2f}%)")
    print(f"  Total Executed Trades:    {total_trades} Trades")
    print(f"  Win Rate:                 {win_rate:.1f}% ({wins} Wins / {total_trades - wins} Losses)")
    print(f"  Profit Factor:            {profit_factor:.2f}")
    print(f"  Max Drawdown:             -{max_dd_pct:.2f}%")

if __name__ == "__main__":
    run_3m_partial_tp_engine()
