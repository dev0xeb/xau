"""
Week-by-Week Empirical Audit for Model 2 (2021 - 2026 / 5 Full Years Data).

Answers the exact question:
"Was it profitable in every week of the 5 years?"

Evaluates:
1. Total Calendar Weeks
2. Number of Profitable Weeks vs Losing Weeks
3. Weekly Win Rate (%)
4. Worst Weekly Loss ($) & Best Weekly Gain ($)
5. Distribution of Weekly PnL
"""

import sys
from pathlib import Path
from datetime import datetime, date
import pandas as pd
import numpy as np
import time

def run_weekly_audit_5y():
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

    cutoff_date = pd.to_datetime("2021-01-01 00:00:00", utc=True)
    df_5y_5m = df_5m[df_5m['timestamp'] >= cutoff_date].copy().reset_index(drop=True)

    df_1h = df_5y_5m.set_index('timestamp').resample('1h').agg({
        'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last'
    }).dropna().reset_index()

    df_1h['h1_ema21'] = df_1h['close'].ewm(span=21, adjust=False).mean()
    df_1h['h1_ema50'] = df_1h['close'].ewm(span=50, adjust=False).mean()

    df_1h['h1_trend'] = 'NEUTRAL'
    df_1h.loc[(df_1h['close'] > df_1h['h1_ema21']) & (df_1h['h1_ema21'] > df_1h['h1_ema50']), 'h1_trend'] = 'BULLISH'
    df_1h.loc[(df_1h['close'] < df_1h['h1_ema21']) & (df_1h['h1_ema21'] < df_1h['h1_ema50']), 'h1_trend'] = 'BEARISH'

    df_5y_5m = pd.merge_asof(
        df_5y_5m.sort_values('timestamp'),
        df_1h[['timestamp', 'h1_ema21', 'h1_ema50', 'h1_trend']].sort_values('timestamp'),
        on='timestamp',
        direction='backward'
    )

    df_5y_5m['m5_ema21'] = df_5y_5m['close'].ewm(span=21, adjust=False).mean()
    df_5y_5m['hour'] = df_5y_5m['timestamp'].dt.hour
    df_5y_5m['date'] = df_5y_5m['timestamp'].dt.date
    df_5y_5m['year'] = df_5y_5m['timestamp'].dt.year
    df_5y_5m['year_week'] = df_5y_5m['timestamp'].dt.strftime('%Y-W%U')

    closes = df_5y_5m['close'].values
    highs = df_5y_5m['high'].values
    lows = df_5y_5m['low'].values
    times = df_5y_5m['timestamp'].dt.strftime('%Y-%m-%d %H:%M UTC').values
    hours = df_5y_5m['hour'].values
    h1_trends = df_5y_5m['h1_trend'].values
    m5_ema21 = df_5y_5m['m5_ema21'].values
    year_weeks = df_5y_5m['year_week'].values
    n = len(df_5y_5m)

    spread_estimate = 0.15
    pip_size = 0.10
    account_balance = 10000.0
    risk_pct = 0.01

    trades = []
    triggered_bars = set()

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

            t1_hit, t2_hit, t3_hit = False, False, False
            sl_hit = False
            exit_p = closes[min(t+24, n-1)]

            for k in range(t+1, min(t+25, n)):
                if lows[k] <= sl_price: sl_hit = True; exit_p = sl_price; break
                if not t1_hit and highs[k] >= tp1: t1_hit = True
                if not t2_hit and highs[k] >= tp2: t2_hit = True
                if not t3_hit and highs[k] >= tp3: t3_hit = True
                if t1_hit and t2_hit and t3_hit: break

            pnl_t1 = (-lot_per_ticket * (entry_price - sl_price) * 100.0) if sl_hit else ((lot_per_ticket * (tp1 - entry_price) * 100.0) if t1_hit else (lot_per_ticket * (exit_p - entry_price) * 100.0))
            pnl_t2 = (-lot_per_ticket * (entry_price - sl_price) * 100.0) if sl_hit else ((lot_per_ticket * (tp2 - entry_price) * 100.0) if t2_hit else (lot_per_ticket * (exit_p - entry_price) * 100.0))
            pnl_t3 = (-lot_per_ticket * (entry_price - sl_price) * 100.0) if sl_hit else ((lot_per_ticket * (tp3 - entry_price) * 100.0) if t1_hit else (lot_per_ticket * (exit_p - entry_price) * 100.0))

            total_trade_pnl = pnl_t1 + pnl_t2 + pnl_t3
            win = (total_trade_pnl > 0)
            trades.append({'pnl': total_trade_pnl, 'win': win, 'week': year_weeks[t]})

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

            t1_hit, t2_hit, t3_hit = False, False, False
            sl_hit = False
            exit_p = closes[min(t+24, n-1)]

            for k in range(t+1, min(t+25, n)):
                if highs[k] >= sl_price: sl_hit = True; exit_p = sl_price; break
                if not t1_hit and lows[k] <= tp1: t1_hit = True
                if not t2_hit and lows[k] <= tp2: t2_hit = True
                if not t3_hit and lows[k] <= tp3: t3_hit = True
                if t1_hit and t2_hit and t3_hit: break

            pnl_t1 = (-lot_per_ticket * (sl_price - entry_price) * 100.0) if sl_hit else ((lot_per_ticket * (entry_price - tp1) * 100.0) if t1_hit else (lot_per_ticket * (entry_price - exit_p) * 100.0))
            pnl_t2 = (-lot_per_ticket * (sl_price - entry_price) * 100.0) if sl_hit else ((lot_per_ticket * (entry_price - tp2) * 100.0) if t2_hit else (lot_per_ticket * (entry_price - exit_p) * 100.0))
            pnl_t3 = (-lot_per_ticket * (sl_price - entry_price) * 100.0) if sl_hit else ((lot_per_ticket * (entry_price - tp3) * 100.0) if t1_hit else (lot_per_ticket * (entry_price - exit_p) * 100.0))

            total_trade_pnl = pnl_t1 + pnl_t2 + pnl_t3
            win = (total_trade_pnl > 0)
            trades.append({'pnl': total_trade_pnl, 'win': win, 'week': year_weeks[t]})

    df_tr = pd.DataFrame(trades)
    elapsed = time.time() - start_t

    print("=========================================================================================")
    print(f" WEEK-BY-WEEK AUDIT REPORT FOR MODEL 2 (2021 - 2026) [{elapsed:.2f}s]")
    print("=========================================================================================")

    if df_tr.empty:
        print("No trades found.")
        return

    # Group trades by calendar week
    weekly_grp = df_tr.groupby('week').agg(
        trades=('pnl', 'count'),
        wins=('win', lambda x: x.sum()),
        pnl=('pnl', 'sum')
    ).reset_index()

    total_weeks = len(weekly_grp)
    prof_weeks = len(weekly_grp[weekly_grp['pnl'] > 0])
    loss_weeks = len(weekly_grp[weekly_grp['pnl'] < 0])
    be_weeks = len(weekly_grp[weekly_grp['pnl'] == 0])

    weekly_win_rate = (prof_weeks / total_weeks) * 100.0
    best_week = weekly_grp['pnl'].max()
    worst_week = weekly_grp['pnl'].min()
    avg_weekly_pnl = weekly_grp['pnl'].mean()
    med_weekly_pnl = weekly_grp['pnl'].median()

    print(f"  Total Calendar Weeks Evaluated:    {total_weeks} Weeks (2021 to 2026)")
    print(f"  Profitable Weeks:                  {prof_weeks} Weeks ({weekly_win_rate:.1f}%)")
    print(f"  Losing Weeks:                      {loss_weeks} Weeks ({(loss_weeks/total_weeks)*100.0:.1f}%)")
    print(f"  Breakeven ($0) Weeks:              {be_weeks} Weeks")
    print(f"  -------------------------------------------------------------------------")
    print(f"  Average Weekly Net Profit:         ${avg_weekly_pnl:>+10.2f} (+{avg_weekly_pnl/100:+.2f}%)")
    print(f"  Median Weekly Net Profit:          ${med_weekly_pnl:>+10.2f} (+{med_weekly_pnl/100:+.2f}%)")
    print(f"  Best Single Week (Max Gain):       ${best_week:>+10.2f} (+{best_week/100:+.2f}%)")
    print(f"  Worst Single Week (Max Loss):      ${worst_week:>+10.2f} ({worst_week/100:+.2f}%)")

    if loss_weeks > 0:
        print(f"\n  LIST OF LOSING WEEKS (ALL {loss_weeks} WEEKS):")
        print("-" * 80)
        l_df = weekly_grp[weekly_grp['pnl'] < 0].sort_values('pnl')
        for idx, r in l_df.iterrows():
            w_wr = (r['wins'] / r['trades']) * 100.0
            print(f"   Week {r['week']} | Trades: {r['trades']:2d} | Win Rate: {w_wr:5.1f}% | Net Weekly PnL: ${r['pnl']:>+8.2f}")
    else:
        print("\n  AMAZING RESULT: Model 2 was 100% PROFITABLE IN EVERY SINGLE WEEK across 5 years!")

if __name__ == "__main__":
    run_weekly_audit_5y()
