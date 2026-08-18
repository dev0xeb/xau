"""
Full 5-Year High-Speed Backtest for Strategy 2: Opening Range Breakout (ORB) Engine.

Evaluates 15-minute Opening Range Box at London Open (07:00 UTC) and NY Open (13:30 UTC).
Executes across 5-year parquet dataset in ~1.5 seconds.
"""

import sys
from pathlib import Path
from datetime import datetime, date, timedelta
import pandas as pd
import numpy as np
import time

def run_orb_5y_backtest():
    proc_5m_path = Path("data/processed/xau_5m_5y.parquet")
    if not proc_5m_path.exists():
        print("[ERROR] 5m dataset missing!")
        return

    start_t = time.time()

    df_5m = pd.read_parquet(proc_5m_path)
    df_5m['timestamp'] = pd.to_datetime(df_5m['timestamp'])
    df_5m = df_5m.sort_values('timestamp').reset_index(drop=True)

    df_5m['hour'] = df_5m['timestamp'].dt.hour
    df_5m['minute'] = df_5m['timestamp'].dt.minute

    closes_5m = df_5m['close'].values
    highs_5m = df_5m['high'].values
    lows_5m = df_5m['low'].values
    hours_5m = df_5m['hour'].values
    minutes_5m = df_5m['minute'].values
    n = len(df_5m)

    trades = []

    for i in range(3, n - 12):
        # 07:15 (London ORB complete) or 13:45 (NY ORB complete)
        is_london_orb = (hours_5m[i] == 7 and minutes_5m[i] == 15)
        is_ny_orb = (hours_5m[i] == 13 and minutes_5m[i] == 45)

        if not (is_london_orb or is_ny_orb):
            continue

        orb_high = np.max(highs_5m[i-3:i])
        orb_low = np.min(lows_5m[i-3:i])
        orb_range = orb_high - orb_low

        if 1.00 <= orb_range <= 8.00:
            c = closes_5m[i]

            # Bullish Breakout
            if c > orb_high:
                sl = (orb_high + orb_low) / 2.0
                risk = c - sl
                if 0.80 <= risk <= 4.00:
                    tp1 = c + (1.5 * risk)
                    tp2 = c + (2.5 * risk)

                    fut_highs = highs_5m[i+1:i+13]
                    fut_lows = lows_5m[i+1:i+13]

                    if np.max(fut_highs) >= tp2:
                        trades.append({'pnl': 2.0, 'win': True, 'type': 'BUY'})
                    elif np.max(fut_highs) >= tp1:
                        trades.append({'pnl': 0.75, 'win': True, 'type': 'BUY'})
                    elif np.min(fut_lows) <= sl:
                        trades.append({'pnl': -1.0, 'win': False, 'type': 'BUY'})

            # Bearish Breakout
            elif c < orb_low:
                sl = (orb_high + orb_low) / 2.0
                risk = sl - c
                if 0.80 <= risk <= 4.00:
                    tp1 = c - (1.5 * risk)
                    tp2 = c - (2.5 * risk)

                    fut_highs = highs_5m[i+1:i+13]
                    fut_lows = lows_5m[i+1:i+13]

                    if np.min(fut_lows) <= tp2:
                        trades.append({'pnl': 2.0, 'win': True, 'type': 'SELL'})
                    elif np.min(fut_lows) <= tp1:
                        trades.append({'pnl': 0.75, 'win': True, 'type': 'SELL'})
                    elif np.max(fut_highs) >= sl:
                        trades.append({'pnl': -1.0, 'win': False, 'type': 'SELL'})

    elapsed = time.time() - start_t

    print("=" * 85)
    print(f" FULL 5-YEAR STRATEGY 2 (ORB ENGINE) BACKTEST COMPLETED IN {elapsed:.2f} SECONDS!")
    print("=" * 85)

    if not trades:
        print("No trades triggered.")
        return

    df_t = pd.DataFrame(trades)
    total_trades = len(df_t)
    wins = len(df_t[df_t['win'] == True])
    win_rate = (wins / total_trades) * 100.0

    gross_profit = df_t[df_t['pnl'] > 0]['pnl'].sum()
    gross_loss = abs(df_t[df_t['pnl'] < 0]['pnl'].sum())
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else gross_profit

    df_t['equity'] = 10000.0 + (df_t['pnl'].cumsum() * 100.0)
    net_pnl = df_t['equity'].iloc[-1] - 10000.0
    net_profit_pct = (net_pnl / 10000.0) * 100.0

    peak = df_t['equity'].cummax()
    dd = (df_t['equity'] - peak) / peak * 100.0
    max_dd_pct = abs(dd.min())

    print(f"  Initial Balance:          $10,000.00")
    print(f"  Final Equity:             ${df_t['equity'].iloc[-1]:,.2f}")
    print(f"  Net Profit:               ${net_pnl:,.2f} ({net_profit_pct:+.2f}%)")
    print(f"  Total Executed Trades:    {total_trades}")
    print(f"  Win Rate:                 {win_rate:.1f}% ({wins} Wins / {total_trades - wins} Losses)")
    print(f"  Profit Factor:            {profit_factor:.2f}")
    print(f"  Max Drawdown:             -{max_dd_pct:.2f}%")
    print("=" * 85)

if __name__ == "__main__":
    run_orb_5y_backtest()
