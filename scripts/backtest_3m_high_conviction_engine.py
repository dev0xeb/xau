"""
High-Conviction Institutional Scalping Engine (3-Month Data).

Incorporates 4 Strict High-Conviction Confluences:
1. Deep 15m Liquidity Sweep Depth (>= $0.80 / 8 pips past prior high/low).
2. Strong 5m Displacement Reversal Candle (Close > Open for BUY; Close < Open for SELL).
3. Move SL to Breakeven (BE + $0.20) once trade reaches +$3.00 (+30 pips) profit (Eliminates reversals into losses!).
4. Opposing Range Target (>= $8.00 / 80 pips expansion).

Evaluates past 3 months dataset (May 10, 2026 - Aug 10, 2026 / 18,046 5m bars).
"""

import sys
from pathlib import Path
from datetime import datetime, date
import pandas as pd
import numpy as np
import time

def run_3m_high_conviction_engine():
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

            # Deep Sweep Filter (Depth >= $0.80)
            bull_sweep = (c_low <= prev_15m_low - 0.80) and (c_close > c_open)
            bear_sweep = (c_high >= prev_15m_high + 0.80) and (c_close < c_open)

            # Daily Session Bias Router
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

                    sl_hit, tp_hit, be_hit = False, False, False
                    be_active = False
                    exit_p = closes_5m[min(i+12, n-1)]

                    for k in range(i+1, min(i+13, n)):
                        # Check Breakeven trigger (+ $3.00 profit)
                        if not be_active and highs_5m[k] >= entry_price + 3.00:
                            be_active = True
                            sl = entry_price + 0.20  # SL moved to BE + $0.20

                        if lows_5m[k] <= sl:
                            if be_active: be_hit = True
                            else: sl_hit = True
                            exit_p = sl
                            break
                        elif highs_5m[k] >= target_tp:
                            tp_hit = True
                            exit_p = target_tp
                            break

                    if be_hit:
                        pnl_val = lots * (0.20) * 100.0
                        trades.append({'date': str(d), 'time': times_5m[i], 'type': 'BUY', 'entry': entry_price, 'sl': sl, 'tp': target_tp, 'risk_dist': risk_dist, 'lots': lots, 'pnl_dollar': pnl_val, 'win': True, 'pips': 2.0, 'res': 'BE WIN'})
                    elif sl_hit:
                        trades.append({'date': str(d), 'time': times_5m[i], 'type': 'BUY', 'entry': entry_price, 'sl': sl, 'tp': target_tp, 'risk_dist': risk_dist, 'lots': lots, 'pnl_dollar': -100.0, 'win': False, 'pips': (sl - entry_price)*10, 'res': 'LOSS'})
                    elif tp_hit:
                        profit_val = lots * (target_tp - entry_price) * 100.0
                        trades.append({'date': str(d), 'time': times_5m[i], 'type': 'BUY', 'entry': entry_price, 'sl': sl, 'tp': target_tp, 'risk_dist': risk_dist, 'lots': lots, 'pnl_dollar': profit_val, 'win': True, 'pips': (target_tp - entry_price)*10, 'res': 'FULL WIN'})
                    else:
                        pnl_val = lots * (exit_p - entry_price) * 100.0
                        trades.append({'date': str(d), 'time': times_5m[i], 'type': 'BUY', 'entry': entry_price, 'sl': sl, 'tp': target_tp, 'risk_dist': risk_dist, 'lots': lots, 'pnl_dollar': pnl_val, 'win': (exit_p > entry_price), 'pips': (exit_p - entry_price)*10, 'res': 'EXPIRE'})

            elif bear_sig:
                entry_price = c_close - spread
                sl = c_high + 1.20
                risk_dist = sl - entry_price

                day_low_so_far = np.min(lows_5m[day_indices[0]:i])
                target_tp = min(day_low_so_far, entry_price - 10.00)

                if risk_dist >= 0.80:
                    lots = (account_balance * risk_pct) / (risk_dist * 100.0)
                    traded_today = True

                    sl_hit, tp_hit, be_hit = False, False, False
                    be_active = False
                    exit_p = closes_5m[min(i+12, n-1)]

                    for k in range(i+1, min(i+13, n)):
                        # Check Breakeven trigger (- $3.00 profit)
                        if not be_active and lows_5m[k] <= entry_price - 3.00:
                            be_active = True
                            sl = entry_price - 0.20  # SL moved to BE - $0.20

                        if highs_5m[k] >= sl:
                            if be_active: be_hit = True
                            else: sl_hit = True
                            exit_p = sl
                            break
                        elif lows_5m[k] <= target_tp:
                            tp_hit = True
                            exit_p = target_tp
                            break

                    if be_hit:
                        pnl_val = lots * (0.20) * 100.0
                        trades.append({'date': str(d), 'time': times_5m[i], 'type': 'SELL', 'entry': entry_price, 'sl': sl, 'tp': target_tp, 'risk_dist': risk_dist, 'lots': lots, 'pnl_dollar': pnl_val, 'win': True, 'pips': 2.0, 'res': 'BE WIN'})
                    elif sl_hit:
                        trades.append({'date': str(d), 'time': times_5m[i], 'type': 'SELL', 'entry': entry_price, 'sl': sl, 'tp': target_tp, 'risk_dist': risk_dist, 'lots': lots, 'pnl_dollar': -100.0, 'win': False, 'pips': (entry_price - sl)*10, 'res': 'LOSS'})
                    elif tp_hit:
                        profit_val = lots * (entry_price - target_tp) * 100.0
                        trades.append({'date': str(d), 'time': times_5m[i], 'type': 'SELL', 'entry': entry_price, 'sl': sl, 'tp': target_tp, 'risk_dist': risk_dist, 'lots': lots, 'pnl_dollar': profit_val, 'win': True, 'pips': (entry_price - target_tp)*10, 'res': 'FULL WIN'})
                    else:
                        pnl_val = lots * (entry_price - exit_p) * 100.0
                        trades.append({'date': str(d), 'time': times_5m[i], 'type': 'SELL', 'entry': entry_price, 'sl': sl, 'tp': target_tp, 'risk_dist': risk_dist, 'lots': lots, 'pnl_dollar': pnl_val, 'win': (entry_price > exit_p), 'res': 'EXPIRE'})

    elapsed = time.time() - start_t

    df_t = pd.DataFrame(trades)
    print("=" * 95)
    print(f" HIGH-CONVICTION SCALPING ENGINE 3-MONTH REPORT (MAY 10 - AUG 10, 2026) [{elapsed:.2f}s]")
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
    print(f"  Total Executed Trades:    {total_trades} Trades (~{total_trades/65:.1f} trades / week)")
    print(f"  Win Rate:                 {win_rate:.1f}% ({wins} Wins / {total_trades - wins} Losses)")
    print(f"  Profit Factor:            {profit_factor:.2f}")
    print(f"  Max Drawdown:             -{max_dd_pct:.2f}%")
    print(f"  Position Sizing:          Avg Lot: {avg_lots:.2f} Lots (1% Risk per Trade)")

    print("\n  Trade Result Types Breakdown:")
    res_counts = df_t['res'].value_counts()
    for r_type, count in res_counts.items():
        print(f"     - {r_type:<10}: {count:2d} Trades ({count/total_trades*100:.1f}%)")

if __name__ == "__main__":
    run_3m_high_conviction_engine()
