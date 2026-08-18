"""
Past Week Simulation & Comparative Benchmark (Aug 3 - Aug 7, 2026):
1. Baseline Model 2 (Fixed Structural SL throughout trade)
2. Baseline Model 2 + Breakeven Trailing at TP1 (SL on T2 & T3 moves to Entry after TP1)
"""

import sys
from pathlib import Path
from datetime import datetime, date
import pandas as pd
import numpy as np
import time

def run_be_simulation_past_week():
    proc_5m_path = Path("data/processed/xau_5m_5y.parquet")
    if not proc_5m_path.exists():
        print("[ERROR] 5m parquet file not found!")
        return

    start_t = time.time()

    df_5m = pd.read_parquet(proc_5m_path)
    df_5m['timestamp'] = pd.to_datetime(df_5m['timestamp'])
    if df_5m['timestamp'].dt.tz is None:
        df_5m['timestamp'] = df_5m['timestamp'].dt.tz_localize('UTC')
    else:
        df_5m['timestamp'] = df_5m['timestamp'].dt.tz_convert('UTC')

    df_5m = df_5m.sort_values('timestamp').reset_index(drop=True)

    start_week = pd.to_datetime("2026-08-03 00:00:00", utc=True)
    end_week = pd.to_datetime("2026-08-07 23:59:59", utc=True)

    df_week_5m = df_5m[(df_5m['timestamp'] >= start_week) & (df_5m['timestamp'] <= end_week)].copy().reset_index(drop=True)

    df_1h = df_week_5m.set_index('timestamp').resample('1h').agg({
        'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last'
    }).dropna().reset_index()

    df_1h['h1_ema21'] = df_1h['close'].ewm(span=21, adjust=False).mean()
    df_1h['h1_ema50'] = df_1h['close'].ewm(span=50, adjust=False).mean()

    df_1h['h1_trend'] = 'NEUTRAL'
    df_1h.loc[(df_1h['close'] > df_1h['h1_ema21']) & (df_1h['h1_ema21'] > df_1h['h1_ema50']), 'h1_trend'] = 'BULLISH'
    df_1h.loc[(df_1h['close'] < df_1h['h1_ema21']) & (df_1h['h1_ema21'] < df_1h['h1_ema50']), 'h1_trend'] = 'BEARISH'

    df_week_5m = pd.merge_asof(
        df_week_5m.sort_values('timestamp'),
        df_1h[['timestamp', 'h1_ema21', 'h1_ema50', 'h1_trend']].sort_values('timestamp'),
        on='timestamp',
        direction='backward'
    )

    df_week_5m['m5_ema21'] = df_week_5m['close'].ewm(span=21, adjust=False).mean()
    df_week_5m['hour'] = df_week_5m['timestamp'].dt.hour

    closes = df_week_5m['close'].values
    highs = df_week_5m['high'].values
    lows = df_week_5m['low'].values
    times = df_week_5m['timestamp'].dt.strftime('%Y-%m-%d %H:%M UTC').values
    hours = df_week_5m['hour'].values
    h1_trends = df_week_5m['h1_trend'].values
    m5_ema21 = df_week_5m['m5_ema21'].values
    n = len(df_week_5m)

    spread_estimate = 0.15
    pip_size = 0.10
    account_balance = 10000.0
    risk_pct = 0.01

    def backtest_engine(use_be_trailing=False):
        trades = []
        triggered_bars = set()
        premature_be_stops = 0

        for i in range(10, n - 24):
            t = i
            t_time = times[t]
            hr = hours[t]

            if not (6 <= hr <= 20): continue
            h1_trend = h1_trends[t]
            if h1_trend == 'NEUTRAL': continue

            bull_fvg_pips = (lows[t] - highs[t-2]) / pip_size
            bear_fvg_pips = (lows[t-2] - highs[t]) / pip_size

            is_bull_fvg = (lows[t] > highs[t-2]) and (bull_fvg_pips >= 1.5)
            is_bear_fvg = (highs[t] < lows[t-2]) and (bear_fvg_pips >= 1.5)

            prior_5_low = np.min(lows[max(0, t-5):t])
            prior_5_high = np.max(highs[max(0, t-5):t])

            bull_sweep = (prior_5_low <= m5_ema21[t])
            bear_sweep = (prior_5_high >= m5_ema21[t])

            bull_signal = (h1_trend == 'BULLISH') and is_bull_fvg and bull_sweep and (closes[t] > m5_ema21[t])
            bear_signal = (h1_trend == 'BEARISH') and is_bear_fvg and bear_sweep and (closes[t] < m5_ema21[t])

            if not (bull_signal or bear_signal): continue
            if t in triggered_bars: continue
            triggered_bars.add(t)

            recent_3_low = np.min(lows[t-2:t+1])
            recent_3_high = np.max(highs[t-2:t+1])

            if bull_signal:
                entry_price = highs[t-2] + spread_estimate
                raw_sl_pips = (entry_price - (recent_3_low - 0.50)) / pip_size
                sl_pips = max(min(raw_sl_pips, 80.0), 15.0)
                sl_price = entry_price - (sl_pips * pip_size)

                tp1 = entry_price + (sl_pips * 1.0 * pip_size)
                tp2 = entry_price + (sl_pips * 2.0 * pip_size)
                tp3 = entry_price + (sl_pips * 3.0 * pip_size)

                risk_dist = entry_price - sl_price
                lots_total = (account_balance * risk_pct) / (risk_dist * 100.0)
                lot_per_ticket = lots_total / 3.0

                current_sl_t2 = sl_price
                current_sl_t3 = sl_price
                t1_hit, t2_hit, t3_hit = False, False, False
                t2_be_stopped, t3_be_stopped = False, False
                sl_hit = False
                exit_p = closes[min(t+24, n-1)]

                for k in range(t+1, min(t+25, n)):
                    if not t1_hit and highs[k] >= tp1:
                        t1_hit = True
                        if use_be_trailing:
                            current_sl_t2 = entry_price
                            current_sl_t3 = entry_price

                    if t1_hit and not t2_hit and highs[k] >= tp2: t2_hit = True
                    if t2_hit and not t3_hit and highs[k] >= tp3: t3_hit = True

                    if t1_hit and use_be_trailing:
                        if not t2_hit and lows[k] <= current_sl_t2: t2_be_stopped = True
                        if not t3_hit and lows[k] <= current_sl_t3: t3_be_stopped = True

                    if not t1_hit and lows[k] <= sl_price:
                        sl_hit = True
                        exit_p = sl_price
                        break

                    if t1_hit and t2_hit and t3_hit: break

                if use_be_trailing and (t2_be_stopped or t3_be_stopped):
                    fut_high = np.max(highs[t+1:min(t+25, n)])
                    if fut_high >= tp2:
                        premature_be_stops += 1

                if sl_hit:
                    pnl_t1 = -lot_per_ticket * (entry_price - sl_price) * 100.0
                    pnl_t2 = -lot_per_ticket * (entry_price - sl_price) * 100.0
                    pnl_t3 = -lot_per_ticket * (entry_price - sl_price) * 100.0
                else:
                    pnl_t1 = (lot_per_ticket * (tp1 - entry_price) * 100.0) if t1_hit else (lot_per_ticket * (exit_p - entry_price) * 100.0)
                    pnl_t2 = 0.0 if t2_be_stopped else ((lot_per_ticket * (tp2 - entry_price) * 100.0) if t2_hit else (lot_per_ticket * (exit_p - entry_price) * 100.0))
                    pnl_t3 = 0.0 if t3_be_stopped else ((lot_per_ticket * (tp3 - entry_price) * 100.0) if t3_hit else (lot_per_ticket * (exit_p - entry_price) * 100.0))

                total_trade_pnl = pnl_t1 + pnl_t2 + pnl_t3
                win = (total_trade_pnl > 0)
                trades.append({'pnl': total_trade_pnl, 'win': win})

            elif bear_signal:
                entry_price = lows[t-2]
                raw_sl_pips = ((recent_3_high + 0.50) - entry_price) / pip_size
                sl_pips = max(min(raw_sl_pips, 80.0), 15.0)
                sl_price = entry_price + (sl_pips * pip_size)

                tp1 = entry_price - (sl_pips * 1.0 * pip_size)
                tp2 = entry_price - (sl_pips * 2.0 * pip_size)
                tp3 = entry_price - (sl_pips * 3.0 * pip_size)

                risk_dist = sl_price - entry_price
                lots_total = (account_balance * risk_pct) / (risk_dist * 100.0)
                lot_per_ticket = lots_total / 3.0

                current_sl_t2 = sl_price
                current_sl_t3 = sl_price
                t1_hit, t2_hit, t3_hit = False, False, False
                t2_be_stopped, t3_be_stopped = False, False
                sl_hit = False
                exit_p = closes[min(t+24, n-1)]

                for k in range(t+1, min(t+25, n)):
                    if not t1_hit and lows[k] <= tp1:
                        t1_hit = True
                        if use_be_trailing:
                            current_sl_t2 = entry_price
                            current_sl_t3 = entry_price

                    if t1_hit and not t2_hit and lows[k] <= tp2: t2_hit = True
                    if t2_hit and not t3_hit and lows[k] <= tp3: t3_hit = True

                    if t1_hit and use_be_trailing:
                        if not t2_hit and highs[k] >= current_sl_t2: t2_be_stopped = True
                        if not t3_hit and highs[k] >= current_sl_t3: t3_be_stopped = True

                    if not t1_hit and highs[k] >= sl_price:
                        sl_hit = True
                        exit_p = sl_price
                        break

                    if t1_hit and t2_hit and t3_hit: break

                if use_be_trailing and (t2_be_stopped or t3_be_stopped):
                    fut_low = np.min(lows[t+1:min(t+25, n)])
                    if fut_low <= tp2:
                        premature_be_stops += 1

                if sl_hit:
                    pnl_t1 = -lot_per_ticket * (sl_price - entry_price) * 100.0
                    pnl_t2 = -lot_per_ticket * (sl_price - entry_price) * 100.0
                    pnl_t3 = -lot_per_ticket * (sl_price - entry_price) * 100.0
                else:
                    pnl_t1 = (lot_per_ticket * (entry_price - tp1) * 100.0) if t1_hit else (lot_per_ticket * (entry_price - exit_p) * 100.0)
                    pnl_t2 = 0.0 if t2_be_stopped else ((lot_per_ticket * (entry_price - tp2) * 100.0) if t2_hit else (lot_per_ticket * (entry_price - exit_p) * 100.0))
                    pnl_t3 = 0.0 if t3_be_stopped else ((lot_per_ticket * (entry_price - tp3) * 100.0) if t3_hit else (lot_per_ticket * (entry_price - exit_p) * 100.0))

                total_trade_pnl = pnl_t1 + pnl_t2 + pnl_t3
                win = (total_trade_pnl > 0)
                trades.append({'pnl': total_trade_pnl, 'win': win})

        df_tr = pd.DataFrame(trades)
        if df_tr.empty:
            return {'Trades': 0, 'WR': 0, 'PnL': 0, 'PF': 0, 'DD': 0, 'BE_Stops': 0}

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

        return {'Trades': n_tr, 'WR': wr, 'PnL': net_pnl, 'PF': pf, 'DD': max_dd, 'BE_Stops': premature_be_stops}

    res_fixed = backtest_engine(use_be_trailing=False)
    res_be = backtest_engine(use_be_trailing=True)

    elapsed = time.time() - start_t

    print("=========================================================================================")
    print(f" PAST WEEK MODEL 2 COMPARISON (AUG 3 - AUG 7, 2026) [{elapsed:.2f}s]")
    print("=========================================================================================")
    print(f" {'METRIC PARAMETER':<35} | {'FIXED SL (YOUR BLUEPRINT)':<25} | {'BE TRAILING AT TP1'}")
    print("-" * 95)
    print(f" {'Initial Balance':<35} | ${10000.00:<24,.2f} | ${10000.00:,.2f}")
    print(f" {'Final Equity':<35} | ${10000.0 + res_fixed['PnL']:<24,.2f} | ${10000.0 + res_be['PnL']:,.2f}")
    print(f" {'Net Profit ($ / %)':<35} | ${res_fixed['PnL']:>+10.2f} ({(res_fixed['PnL']/100):>+6.2f}%)   | ${res_be['PnL']:>+10.2f} ({(res_be['PnL']/100):>+6.2f}%)")
    print(f" {'Executed Trades':<35} | {res_fixed['Trades']:<25d} | {res_be['Trades']} Trades")
    print(f" {'Win Rate (%)':<35} | {res_fixed['WR']:>6.1f}%                     | {res_be['WR']:>6.1f}%")
    print(f" {'Profit Factor':<35} | {res_fixed['PF']:>6.2f}                      | {res_be['PF']:>6.2f}")
    print(f" {'Max Drawdown (%)':<35} | -{res_fixed['DD']:>5.2f}%                     | -{res_be['DD']:>5.2f}%")
    print(f" {'Premature BE Stopped Trades':<35} | 0 Trades                  | {res_be['BE_Stops']} Trades ({res_be['BE_Stops']/65*100:.1f}%)")
    print("-" * 95)

if __name__ == "__main__":
    run_be_simulation_past_week()
