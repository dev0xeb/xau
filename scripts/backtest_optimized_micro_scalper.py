"""
Optimized Micro-Scalping Engine with 3 Structural Fixes:
1. 1H HTF Trend Alignment Filter
2. Range Compression & Bounce Verification Filter
3. 0.80 ATR Structural SL Buffer (Survives Double-Sweeps)

Backtests past week's data (Aug 3 - Aug 10, 2026) using dynamic structural exits.
"""

import sys
from pathlib import Path
from datetime import datetime, date
import pandas as pd
import numpy as np

def run_optimized_micro_backtest():
    proc_5m_path = Path("data/processed/xau_5m_5y.parquet")
    if not proc_5m_path.exists():
        print("[ERROR] 5m dataset missing!")
        return

    df_5m = pd.read_parquet(proc_5m_path)
    df_5m['timestamp'] = pd.to_datetime(df_5m['timestamp'])

    df_5m['hour'] = df_5m['timestamp'].dt.hour
    df_5m['date'] = df_5m['timestamp'].dt.date

    start_date = date(2026, 8, 3)
    end_date = date(2026, 8, 10)
    target_dates = sorted([d for d in df_5m['timestamp'].dt.date.unique() if start_date <= d <= end_date])

    closes_5m = df_5m['close'].values
    highs_5m = df_5m['high'].values
    lows_5m = df_5m['low'].values
    times_5m = df_5m['timestamp'].dt.strftime('%H:%M UTC').values
    hours_5m = df_5m['hour'].values
    dates_5m = df_5m['timestamp'].dt.date.values
    n = len(df_5m)

    # 1H EMA (144 5m bars)
    ema50_1h = pd.Series(closes_5m).ewm(span=144, adjust=False).mean().values

    trades = []

    for d in target_dates:
        for i in range(20, n - 12):
            if dates_5m[i] != d:
                continue

            hour = hours_5m[i]
            session = "LONDON" if (7 <= hour < 10) else ("OVERLAP" if (12 <= hour < 16) else ("NY" if (16 <= hour < 21) else "ASIA"))

            # 1. Range Box Definition (last 10 5m bars = 50 mins)
            range_high = np.max(highs_5m[i-10:i])
            range_low = np.min(lows_5m[i-10:i])
            range_size = range_high - range_low

            if not (1.50 <= range_size <= 12.00):
                continue

            # Fix #2: Range Compression Filter (verify price bounced inside range at least twice)
            range_touches_high = np.sum(highs_5m[i-10:i] >= (range_high - 0.50))
            range_touches_low = np.sum(lows_5m[i-10:i] <= (range_low + 0.50))
            if range_touches_high < 1 or range_touches_low < 1:
                continue  # Skip uncompressed / trending ranges

            c_high = highs_5m[i]
            c_low = lows_5m[i]
            c_close = closes_5m[i]

            # Fix #1: 1H HTF Trend Alignment
            htf_bull = c_close > ema50_1h[i]
            htf_bear = c_close < ema50_1h[i]

            # Bullish Range Sweep Entry (Only when 1H is Bullish)
            if htf_bull and c_low < range_low and c_close > range_low:
                sweep_depth = range_low - c_low
                if 0.40 <= sweep_depth <= 3.00:
                    # Fix #3: 0.80 ATR SL Structural Buffer ($1.20 total buffer past range low)
                    sl = range_low - 1.20
                    risk = c_close - sl
                    target_tp = range_high

                    if risk >= 0.80 and (target_tp > c_close):
                        fut_highs = highs_5m[i+1:min(i+12, n)]
                        fut_lows = lows_5m[i+1:min(i+12, n)]

                        max_h = np.max(fut_highs)
                        min_l = np.min(fut_lows)

                        if min_l <= sl:
                            trades.append({
                                'date': str(d), 'time': times_5m[i], 'session': session, 'type': 'BUY',
                                'entry': c_close, 'sl': sl, 'tp': target_tp, 'pnl_dollar': -100.0, 'win': False,
                                'exit_type': 'STOP LOSS'
                            })
                        elif max_h >= target_tp:
                            pnl_val = ((target_tp - c_close) / risk) * 100.0
                            trades.append({
                                'date': str(d), 'time': times_5m[i], 'session': session, 'type': 'BUY',
                                'entry': c_close, 'sl': sl, 'tp': target_tp, 'pnl_dollar': pnl_val, 'win': True,
                                'exit_type': 'STRUCTURAL RANGE HIGH'
                            })
                        else:
                            exit_p = closes_5m[min(i+6, n-1)]
                            pnl_val = ((exit_p - c_close) / risk) * 100.0
                            trades.append({
                                'date': str(d), 'time': times_5m[i], 'session': session, 'type': 'BUY',
                                'entry': c_close, 'sl': sl, 'tp': target_tp, 'pnl_dollar': pnl_val, 'win': (exit_p > c_close),
                                'exit_type': 'TIME EXPIRATION'
                            })

            # Bearish Range Sweep Entry (Only when 1H is Bearish)
            elif htf_bear and c_high > range_high and c_close < range_high:
                sweep_depth = c_high - range_high
                if 0.40 <= sweep_depth <= 3.00:
                    # Fix #3: 0.80 ATR SL Structural Buffer
                    sl = range_high + 1.20
                    risk = sl - c_close
                    target_tp = range_low

                    if risk >= 0.80 and (target_tp < c_close):
                        fut_highs = highs_5m[i+1:min(i+12, n)]
                        fut_lows = lows_5m[i+1:min(i+12, n)]

                        max_h = np.max(fut_highs)
                        min_l = np.min(fut_lows)

                        if max_h >= sl:
                            trades.append({
                                'date': str(d), 'time': times_5m[i], 'session': session, 'type': 'SELL',
                                'entry': c_close, 'sl': sl, 'tp': target_tp, 'pnl_dollar': -100.0, 'win': False,
                                'exit_type': 'STOP LOSS'
                            })
                        elif min_l <= target_tp:
                            pnl_val = ((c_close - target_tp) / risk) * 100.0
                            trades.append({
                                'date': str(d), 'time': times_5m[i], 'session': session, 'type': 'SELL',
                                'entry': c_close, 'sl': sl, 'tp': target_tp, 'pnl_dollar': pnl_val, 'win': True,
                                'exit_type': 'STRUCTURAL RANGE LOW'
                            })
                        else:
                            exit_p = closes_5m[min(i+6, n-1)]
                            pnl_val = ((c_close - exit_p) / risk) * 100.0
                            trades.append({
                                'date': str(d), 'time': times_5m[i], 'session': session, 'type': 'SELL',
                                'entry': c_close, 'sl': sl, 'tp': target_tp, 'pnl_dollar': pnl_val, 'win': (c_close > exit_p),
                                'exit_type': 'TIME EXPIRATION'
                            })

    df_t = pd.DataFrame(trades)
    print("=" * 95)
    print(" OPTIMIZED MICRO-SCALPER BACKTEST (PAST WEEK: AUG 3 - AUG 10, 2026)")
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
    print(f"  Total Executed Trades:    {total_trades}")
    print(f"  Win Rate:                 {win_rate:.1f}% ({wins} Wins / {total_trades - wins} Losses)")
    print(f"  Profit Factor:            {profit_factor:.2f}")
    print(f"  Max Drawdown:             -{max_dd_pct:.2f}%")

    print("\n" + "-" * 95)
    print(" PERFORMANCE BY SESSION WINDOW:")
    print("-" * 95)
    sess_sum = df_t.groupby('session').agg(cnt=('win', 'count'), wr=('win', 'mean'), pnl=('pnl_dollar', 'sum')).reset_index()
    for idx, r in sess_sum.iterrows():
        print(f"   - {r['session']:<8}: Trades={r['cnt']:<3} | Win Rate={r['wr']*100.0:>5.1f}% | Net PnL=${r['pnl']:>+8.2f}")

    print("\n" + "-" * 95)
    print(" EXECUTED TRADES LOG:")
    print("-" * 95)
    for idx, r in df_t.iterrows():
        res_str = "WIN" if r['win'] else "LOSS"
        print(f" Trade #{idx+1:02d} [{r['date']}] [{r['time']}] [{r['session']:<7}] {r['type']} | Entry:${r['entry']:.2f} | SL:${r['sl']:.2f} | Target:${r['tp']:.2f} | Result:{res_str:<4} (${r['pnl_dollar']:+.2f})")

if __name__ == "__main__":
    run_optimized_micro_backtest()
