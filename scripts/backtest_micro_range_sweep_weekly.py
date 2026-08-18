"""
Backtest Engine for the 1m/5m/15m Micro Range Sweep & Dynamic Structural Exit Model.

Evaluates the past week's data (Aug 3 - Aug 10, 2026) using:
1. Dynamic Structural Exits (Opposite Range Boundary / Opposing Order Block) instead of fixed R:R.
2. Range Liquidity Sweep Entries (Wick past Range High/Low with close back inside).
3. Invalidation Stop Loss ($0.50 past sweep wick).
"""

import sys
from pathlib import Path
from datetime import datetime, date
import pandas as pd
import numpy as np

def run_micro_range_sweep_backtest():
    proc_5m_path = Path("data/processed/xau_5m_5y.parquet")
    proc_15m_path = Path("data/processed/xau_15m_5y.parquet")

    if not (proc_5m_path.exists() and proc_15m_path.exists()):
        print("[ERROR] Datasets missing!")
        return

    df_5m = pd.read_parquet(proc_5m_path)
    df_15m = pd.read_parquet(proc_15m_path)

    df_5m['timestamp'] = pd.to_datetime(df_5m['timestamp'])
    df_15m['timestamp'] = pd.to_datetime(df_15m['timestamp'])

    # Past week: Aug 3 to Aug 10, 2026
    start_date = date(2026, 8, 3)
    end_date = date(2026, 8, 10)

    target_dates = [d for d in df_5m['timestamp'].dt.date.unique() if start_date <= d <= end_date]
    target_dates = sorted(target_dates)

    print("=" * 95)
    print(f" BACKTEST: MICRO RANGE SWEEP & DYNAMIC STRUCTURAL EXIT MODEL ({target_dates[0]} to {target_dates[-1]})")
    print("=" * 95)

    trades = []

    for d in target_dates:
        df_5m_day = df_5m[df_5m['timestamp'].dt.date == d].sort_values('timestamp').reset_index(drop=True)
        if df_5m_day.empty or len(df_5m_day) < 20:
            continue

        highs_5 = df_5m_day['high'].values
        lows_5 = df_5m_day['low'].values
        closes_5 = df_5m_day['close'].values
        times_5 = df_5m_day['timestamp'].dt.strftime('%H:%M UTC').values
        hours_5 = df_5m_day['timestamp'].dt.hour.values
        n_5 = len(df_5m_day)

        for i in range(10, n_5 - 8):
            hour = hours_5[i]
            session = "LONDON" if (7 <= hour < 10) else ("OVERLAP" if (12 <= hour < 16) else ("NY" if (16 <= hour < 21) else "ASIA"))

            # 1. 5m Consolidation Range Box (last 10 5m bars = 50 mins)
            range_high = np.max(highs_5[i-10:i])
            range_low = np.min(lows_5[i-10:i])
            range_size = range_high - range_low

            if not (1.50 <= range_size <= 12.00):
                continue

            c_high = highs_5[i]
            c_low = lows_5[i]
            c_close = closes_5[i]

            # Bullish Range Sweep Entry
            if c_low < range_low and c_close > range_low:
                sweep_depth = range_low - c_low
                if 0.40 <= sweep_depth <= 3.00:
                    sl = c_low - 0.50
                    risk = c_close - sl

                    # Dynamic Target 1: Opposite Range High
                    target_tp = range_high

                    if risk >= 0.80 and (target_tp > c_close):
                        fut_highs = highs_5[i+1:min(i+10, n_5)]
                        fut_lows = lows_5[i+1:min(i+10, n_5)]

                        max_h = np.max(fut_highs)
                        min_l = np.min(fut_lows)

                        if min_l <= sl:
                            trades.append({
                                'date': str(d), 'time': times_5[i], 'session': session, 'type': 'BUY',
                                'entry': c_close, 'sl': sl, 'tp': target_tp, 'pnl_dollar': -100.0, 'win': False,
                                'exit_type': 'STOP LOSS', 'pips': (sl - c_close) * 10
                            })
                        elif max_h >= target_tp:
                            pnl_val = ((target_tp - c_close) / risk) * 100.0
                            trades.append({
                                'date': str(d), 'time': times_5[i], 'session': session, 'type': 'BUY',
                                'entry': c_close, 'sl': sl, 'tp': target_tp, 'pnl_dollar': pnl_val, 'win': True,
                                'exit_type': 'STRUCTURAL TARGET (RANGE HIGH)', 'pips': (target_tp - c_close) * 10
                            })
                        else:
                            # Partial expansion exit
                            exit_p = closes_5[min(i+6, n_5-1)]
                            pnl_val = ((exit_p - c_close) / risk) * 100.0
                            trades.append({
                                'date': str(d), 'time': times_5[i], 'session': session, 'type': 'BUY',
                                'entry': c_close, 'sl': sl, 'tp': target_tp, 'pnl_dollar': pnl_val, 'win': (exit_p > c_close),
                                'exit_type': 'TIME EXPIRATION EXIT', 'pips': (exit_p - c_close) * 10
                            })

            # Bearish Range Sweep Entry
            elif c_high > range_high and c_close < range_high:
                sweep_depth = c_high - range_high
                if 0.40 <= sweep_depth <= 3.00:
                    sl = c_high + 0.50
                    risk = sl - c_close

                    # Dynamic Target 1: Opposite Range Low
                    target_tp = range_low

                    if risk >= 0.80 and (target_tp < c_close):
                        fut_highs = highs_5[i+1:min(i+10, n_5)]
                        fut_lows = lows_5[i+1:min(i+10, n_5)]

                        max_h = np.max(fut_highs)
                        min_l = np.min(fut_lows)

                        if max_h >= sl:
                            trades.append({
                                'date': str(d), 'time': times_5[i], 'session': session, 'type': 'SELL',
                                'entry': c_close, 'sl': sl, 'tp': target_tp, 'pnl_dollar': -100.0, 'win': False,
                                'exit_type': 'STOP LOSS', 'pips': (c_close - sl) * 10
                            })
                        elif min_l <= target_tp:
                            pnl_val = ((c_close - target_tp) / risk) * 100.0
                            trades.append({
                                'date': str(d), 'time': times_5[i], 'session': session, 'type': 'SELL',
                                'entry': c_close, 'sl': sl, 'tp': target_tp, 'pnl_dollar': pnl_val, 'win': True,
                                'exit_type': 'STRUCTURAL TARGET (RANGE LOW)', 'pips': (c_close - target_tp) * 10
                            })
                        else:
                            exit_p = closes_5[min(i+6, n_5-1)]
                            pnl_val = ((c_close - exit_p) / risk) * 100.0
                            trades.append({
                                'date': str(d), 'time': times_5[i], 'session': session, 'type': 'SELL',
                                'entry': c_close, 'sl': sl, 'tp': target_tp, 'pnl_dollar': pnl_val, 'win': (exit_p < c_close),
                                'exit_type': 'TIME EXPIRATION EXIT', 'pips': (c_close - exit_p) * 10
                            })

    df_t = pd.DataFrame(trades)
    print("\n" + "=" * 95)
    print(" WEEKLY BACKTEST PERFORMANCE REPORT (AUG 3 - AUG 10, 2026)")
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
    print(" SAMPLE EXECUTED SCALPING TRADES (PAST WEEK):")
    print("-" * 95)
    for idx, r in df_t.head(10).iterrows():
        res_str = "WIN" if r['win'] else "LOSS"
        print(f" Trade #{idx+1:02d} [{r['date']}] [{r['time']}] [{r['session']:<7}] {r['type']} | Entry:${r['entry']:.2f} | SL:${r['sl']:.2f} | Target:${r['tp']:.2f} | Result:{res_str:<4} (${r['pnl_dollar']:+.2f})")

if __name__ == "__main__":
    run_micro_range_sweep_backtest()
