"""
Asian Session Specialist Micro-Scalper 3-Month Backtest Engine.

Restricts 5m Range Sweep entries strictly to the Asian Session (21:00 - 07:00 UTC).
Capitalizes on clean range consolidations while avoiding London/NY trend breakout noise.
"""

import sys
from pathlib import Path
from datetime import datetime, date
import pandas as pd
import numpy as np
import time

def run_asia_specialist_3m_backtest():
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
    df_5m_3m['date'] = df_5m_3m['timestamp'].dt.date

    closes_5m = df_5m_3m['close'].values
    highs_5m = df_5m_3m['high'].values
    lows_5m = df_5m_3m['low'].values
    times_5m = df_5m_3m['timestamp'].dt.strftime('%Y-%m-%d %H:%M UTC').values
    hours_5m = df_5m_3m['hour'].values
    dates_5m = df_5m_3m['date'].values
    n = len(df_5m_3m)

    ema50_1h = pd.Series(closes_5m).ewm(span=144, adjust=False).mean().values

    trades = []
    account_balance = 10000.0
    risk_pct = 0.01

    last_trade_bar = -999

    for i in range(20, n - 12):
        if (i - last_trade_bar) < 6:
            continue

        hour = hours_5m[i]
        # STRICT ASIAN SESSION FILTER: 21:00 - 07:00 UTC ONLY
        if not (hour >= 21 or hour < 7):
            continue

        range_high = np.max(highs_5m[i-10:i])
        range_low = np.min(lows_5m[i-10:i])
        range_size = range_high - range_low

        if not (1.50 <= range_size <= 12.00):
            continue

        range_touches_high = np.sum(highs_5m[i-10:i] >= (range_high - 0.50))
        range_touches_low = np.sum(lows_5m[i-10:i] <= (range_low + 0.50))
        if range_touches_high < 1 or range_touches_low < 1:
            continue

        c_high = highs_5m[i]
        c_low = lows_5m[i]
        c_close = closes_5m[i]

        htf_bull = c_close > ema50_1h[i]
        htf_bear = c_close < ema50_1h[i]

        # Bullish Range Sweep
        if htf_bull and c_low < range_low and c_close > range_low:
            sweep_depth = range_low - c_low
            if 0.40 <= sweep_depth <= 3.00:
                sl = range_low - 1.20
                risk_dist = c_close - sl
                target_tp = range_high

                if risk_dist >= 0.80 and (target_tp > c_close):
                    risk_amount = account_balance * risk_pct
                    lots = risk_amount / (risk_dist * 100.0)

                    fut_highs = highs_5m[i+1:min(i+12, n)]
                    fut_lows = lows_5m[i+1:min(i+12, n)]

                    max_h = np.max(fut_highs)
                    min_l = np.min(fut_lows)

                    last_trade_bar = i

                    if min_l <= sl:
                        trades.append({'date': str(dates_5m[i]), 'time': times_5m[i], 'type': 'BUY', 'entry': c_close, 'sl': sl, 'tp': target_tp, 'risk_dist': risk_dist, 'lots': lots, 'pnl_dollar': -risk_amount, 'win': False})
                    elif max_h >= target_tp:
                        profit_amount = lots * (target_tp - c_close) * 100.0
                        trades.append({'date': str(dates_5m[i]), 'time': times_5m[i], 'type': 'BUY', 'entry': c_close, 'sl': sl, 'tp': target_tp, 'risk_dist': risk_dist, 'lots': lots, 'pnl_dollar': profit_amount, 'win': True})
                    else:
                        exit_p = closes_5m[min(i+6, n-1)]
                        pnl = lots * (exit_p - c_close) * 100.0
                        trades.append({'date': str(dates_5m[i]), 'time': times_5m[i], 'type': 'BUY', 'entry': c_close, 'sl': sl, 'tp': target_tp, 'risk_dist': risk_dist, 'lots': lots, 'pnl_dollar': pnl, 'win': (exit_p > c_close)})

        # Bearish Range Sweep
        elif htf_bear and c_high > range_high and c_close < range_high:
            sweep_depth = c_high - range_high
            if 0.40 <= sweep_depth <= 3.00:
                sl = range_high + 1.20
                risk_dist = sl - c_close
                target_tp = range_low

                if risk_dist >= 0.80 and (target_tp < c_close):
                    risk_amount = account_balance * risk_pct
                    lots = risk_amount / (risk_dist * 100.0)

                    fut_highs = highs_5m[i+1:min(i+12, n)]
                    fut_lows = lows_5m[i+1:min(i+12, n)]

                    max_h = np.max(fut_highs)
                    min_l = np.min(fut_lows)

                    last_trade_bar = i

                    if max_h >= sl:
                        trades.append({'date': str(dates_5m[i]), 'time': times_5m[i], 'type': 'SELL', 'entry': c_close, 'sl': sl, 'tp': target_tp, 'risk_dist': risk_dist, 'lots': lots, 'pnl_dollar': -risk_amount, 'win': False})
                    elif min_l <= target_tp:
                        profit_amount = lots * (c_close - target_tp) * 100.0
                        trades.append({'date': str(dates_5m[i]), 'time': times_5m[i], 'type': 'SELL', 'entry': c_close, 'sl': sl, 'tp': target_tp, 'risk_dist': risk_dist, 'lots': lots, 'pnl_dollar': profit_amount, 'win': True})
                    else:
                        exit_p = closes_5m[min(i+6, n-1)]
                        pnl = lots * (c_close - exit_p) * 100.0
                        trades.append({'date': str(dates_5m[i]), 'time': times_5m[i], 'type': 'SELL', 'entry': c_close, 'sl': sl, 'tp': target_tp, 'risk_dist': risk_dist, 'lots': lots, 'pnl_dollar': pnl, 'win': (c_close > exit_p)})

    elapsed = time.time() - start_t

    df_t = pd.DataFrame(trades)
    print("=" * 95)
    print(f" ASIAN SPECIALIST MICRO-SCALPER 3-MONTH REPORT (MAY 10 - AUG 10, 2026) [{elapsed:.2f}s]")
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
    print(f"  Total Executed Trades:    {total_trades} Trades (~{total_trades/90:.1f} trades / day)")
    print(f"  Win Rate:                 {win_rate:.1f}% ({wins} Wins / {total_trades - wins} Losses)")
    print(f"  Profit Factor:            {profit_factor:.2f}")
    print(f"  Max Drawdown:             -{max_dd_pct:.2f}%")
    print(f"  POSITION LOT SIZING:      Avg Lot: {avg_lots:.2f} Lots")

    print("\n" + "-" * 95)
    print(" SAMPLE EXECUTED ASIAN SCALPING TRADES:")
    print("-" * 95)
    for idx, r in df_t.head(10).iterrows():
        res_str = "WIN" if r['win'] else "LOSS"
        print(f" Trade #{idx+1:02d} [{r['date']}] [{r['time']}] {r['type']:<4} | Lots: {r['lots']:.2f} L | Entry:${r['entry']:.2f} | Target:${r['tp']:.2f} | Result:{res_str:<4} (${r['pnl_dollar']:+.2f})")

if __name__ == "__main__":
    run_asia_specialist_3m_backtest()
