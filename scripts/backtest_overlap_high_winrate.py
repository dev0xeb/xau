"""
High-Win-Rate London/NY Overlap Micro-Intraday Strategy Engine for Gold (XAU/USD).

Applies 1m/5m Market Structure Shift (MSS/CHoCH) + Strong 5m FVG Displacement Gap (>= $1.20)
instead of lagging EMA trend filters.
"""

import sys
from pathlib import Path
from datetime import datetime, date
import pandas as pd
import numpy as np

def run_overlap_high_winrate():
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

    trades = []
    account_balance = 10000.0
    risk_pct = 0.01  # 1% Risk ($100 per trade)

    for d in target_dates:
        traded_today = False

        for i in range(15, n - 12):
            if dates_5m[i] != d:
                continue

            if traded_today:
                break

            hour = hours_5m[i]
            minute = minutes_5m[i]

            # OVERLAP HIGH-WINRATE WINDOW: 12:25 UTC to 15:30 UTC ONLY
            if not ((hour == 12 and minute >= 25) or (13 <= hour <= 15)):
                continue

            c_open = opens_5m[i]
            c_high = highs_5m[i]
            c_low = lows_5m[i]
            c_close = closes_5m[i]

            prev_15m_high = np.max(highs_5m[max(0, i-6):i])
            prev_15m_low = np.min(lows_5m[max(0, i-6):i])

            # Strong 5m Displacement FVG Gap Filter (>= $1.20 gap)
            bull_fvg_gap = (lows_5m[i] - highs_5m[i-2]) if (lows_5m[i] > highs_5m[i-2]) else 0.0
            bear_fvg_gap = (lows_5m[i-2] - highs_5m[i]) if (highs_5m[i] < lows_5m[i-2]) else 0.0

            bull_sweep = (c_low < prev_15m_low) and (c_close > c_open) and (bull_fvg_gap >= 1.20 or c_close > prev_15m_low + 0.80)
            bear_sweep = (c_high > prev_15m_high) and (c_close < c_open) and (bear_fvg_gap >= 1.20 or c_close < prev_15m_high - 0.80)

            if bull_sweep:
                sl = c_low - 1.20
                risk_dist = c_close - sl

                opposing_target = np.max(highs_5m[max(0, i-12):i])
                if opposing_target <= c_close + 2.50:
                    opposing_target = c_close + (3.0 * risk_dist)

                if risk_dist >= 0.80:
                    risk_amount = account_balance * risk_pct
                    lots = risk_amount / (risk_dist * 100.0)

                    fut_highs = highs_5m[i+1:min(i+12, n)]
                    fut_lows = lows_5m[i+1:min(i+12, n)]

                    max_h = np.max(fut_highs)
                    min_l = np.min(fut_lows)

                    traded_today = True

                    if min_l <= sl:
                        trades.append({'date': str(d), 'time': times_5m[i], 'type': 'BUY', 'entry': c_close, 'sl': sl, 'tp': opposing_target, 'risk_dist': risk_dist, 'lots': lots, 'pnl_dollar': -risk_amount, 'win': False, 'pips': (sl - c_close) * 10})
                    elif max_h >= opposing_target:
                        profit_amount = lots * (opposing_target - c_close) * 100.0
                        trades.append({'date': str(d), 'time': times_5m[i], 'type': 'BUY', 'entry': c_close, 'sl': sl, 'tp': opposing_target, 'risk_dist': risk_dist, 'lots': lots, 'pnl_dollar': profit_amount, 'win': True, 'pips': (opposing_target - c_close) * 10})
                    else:
                        exit_p = closes_5m[min(i+8, n-1)]
                        pnl = lots * (exit_p - c_close) * 100.0
                        trades.append({'date': str(d), 'time': times_5m[i], 'type': 'BUY', 'entry': c_close, 'sl': sl, 'tp': opposing_target, 'risk_dist': risk_dist, 'lots': lots, 'pnl_dollar': pnl, 'win': (exit_p > c_close), 'pips': (exit_p - c_close) * 10})

            elif bear_sweep:
                sl = c_high + 1.20
                risk_dist = sl - c_close

                opposing_target = np.min(lows_5m[max(0, i-12):i])
                if opposing_target >= c_close - 2.50:
                    opposing_target = c_close - (3.0 * risk_dist)

                if risk_dist >= 0.80:
                    risk_amount = account_balance * risk_pct
                    lots = risk_amount / (risk_dist * 100.0)

                    fut_highs = highs_5m[i+1:min(i+12, n)]
                    fut_lows = lows_5m[i+1:min(i+12, n)]

                    max_h = np.max(fut_highs)
                    min_l = np.min(fut_lows)

                    traded_today = True

                    if max_h >= sl:
                        trades.append({'date': str(d), 'time': times_5m[i], 'type': 'SELL', 'entry': c_close, 'sl': sl, 'tp': opposing_target, 'risk_dist': risk_dist, 'lots': lots, 'pnl_dollar': -risk_amount, 'win': False, 'pips': (c_close - sl) * 10})
                    elif min_l <= opposing_target:
                        profit_amount = lots * (c_close - opposing_target) * 100.0
                        trades.append({'date': str(d), 'time': times_5m[i], 'type': 'SELL', 'entry': c_close, 'sl': sl, 'tp': opposing_target, 'risk_dist': risk_dist, 'lots': lots, 'pnl_dollar': profit_amount, 'win': True, 'pips': (c_close - opposing_target) * 10})
                    else:
                        exit_p = closes_5m[min(i+8, n-1)]
                        pnl = lots * (c_close - exit_p) * 100.0
                        trades.append({'date': str(d), 'time': times_5m[i], 'type': 'SELL', 'entry': c_close, 'sl': sl, 'tp': opposing_target, 'risk_dist': risk_dist, 'lots': lots, 'pnl_dollar': pnl, 'win': (c_close > exit_p), 'pips': (c_close - exit_p) * 10})

    df_t = pd.DataFrame(trades)
    print("=" * 95)
    print(" HIGH-WIN-RATE OVERLAP MICRO-INTRADAY REPORT (AUG 3 - AUG 10, 2026)")
    print("=" * 95)

    if df_t.empty:
        print("No trades triggered.")
        return

    total_trades = len(df_t)
    wins = len(df_t[df_t['win'] == True])
    win_rate = (wins / total_trades) * 100.0

    avg_lots = df_t['lots'].mean()

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

    print("\n" + "-" * 95)
    print(" EXECUTED HIGH-WIN-RATE TRADES LOG:")
    print("-" * 95)
    for idx, r in df_t.iterrows():
        res_str = "WIN" if r['win'] else "LOSS"
        print(f" Trade #{idx+1:02d} [{r['date']}] [{r['time']}] {r['type']:<4} | Lots:{r['lots']:.2f}L | Entry:${r['entry']:.2f} | Target:${r['tp']:.2f} | Pips:{r['pips']:+6.1f} | Result:{res_str:<4} (${r['pnl_dollar']:+.2f})")

if __name__ == "__main__":
    run_overlap_high_winrate()
