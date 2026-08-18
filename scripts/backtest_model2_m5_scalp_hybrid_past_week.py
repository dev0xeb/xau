"""
Model 2: M5 Scalp Hybrid Strategy Engine Backtest (Past Week Data: Aug 3 - Aug 7, 2026).

Implements the exact step-by-step Technical Blueprint:
1. Closed Candle Indexing (iloc[-2])
2. Commercial Session Window Filter (06:00 - 20:00 UTC)
3. H1 Macro Trend Alignment Filter (H1 Close > H1 EMA21 > H1 EMA50 for BUY; H1 Close < H1 EMA21 < H1 EMA50 for SELL)
4. M5 Fair Value Gap (FVG) Displacement (>= 1.5 pips / $0.15)
5. Institutional Liquidity Sweep (preceding 5-bar low <= M5 EMA21 for BUY; high >= M5 EMA21 for SELL)
6. Micro-Structure Close Confirmation (M5 Close > M5 EMA21 for BUY; M5 Close < M5 EMA21 for SELL)
7. Structural Entry, Dynamic SL & 3-Burst Target Matrix (TP1 = 1.0x, TP2 = 2.0x, TP3 = 3.0x)
"""

import sys
from pathlib import Path
from datetime import datetime, date
import pandas as pd
import numpy as np
import time

def run_model2_past_week():
    raw_1m_path = Path("data/raw/xau_1m_5y.parquet")
    proc_5m_path = Path("data/processed/xau_5m_5y.parquet")

    if not proc_5m_path.exists():
        print("[ERROR] 5m parquet file not found!")
        return

    start_t = time.time()

    # Load 5m dataset
    df_5m = pd.read_parquet(proc_5m_path)
    df_5m['timestamp'] = pd.to_datetime(df_5m['timestamp'])
    if df_5m['timestamp'].dt.tz is None:
        df_5m['timestamp'] = df_5m['timestamp'].dt.tz_localize('UTC')
    else:
        df_5m['timestamp'] = df_5m['timestamp'].dt.tz_convert('UTC')

    df_5m = df_5m.sort_values('timestamp').reset_index(drop=True)

    # Filter for target research week: Aug 3, 2026 to Aug 7, 2026
    start_week = pd.to_datetime("2026-08-03 00:00:00", utc=True)
    end_week = pd.to_datetime("2026-08-07 23:59:59", utc=True)

    df_week_5m = df_5m[(df_5m['timestamp'] >= start_week) & (df_5m['timestamp'] <= end_week)].copy().reset_index(drop=True)

    # Resample 5m to 1H to compute H1 EMAs cleanly
    df_1h = df_week_5m.set_index('timestamp').resample('1h').agg({
        'open': 'first',
        'high': 'max',
        'low': 'min',
        'close': 'last'
    }).dropna().reset_index()

    # Compute H1 EMA(21) and H1 EMA(50)
    df_1h['h1_ema21'] = df_1h['close'].ewm(span=21, adjust=False).mean()
    df_1h['h1_ema50'] = df_1h['close'].ewm(span=50, adjust=False).mean()

    # Determine H1 Trend Alignment
    df_1h['h1_trend'] = 'NEUTRAL'
    df_1h.loc[(df_1h['close'] > df_1h['h1_ema21']) & (df_1h['h1_ema21'] > df_1h['h1_ema50']), 'h1_trend'] = 'BULLISH'
    df_1h.loc[(df_1h['close'] < df_1h['h1_ema21']) & (df_1h['h1_ema21'] < df_1h['h1_ema50']), 'h1_trend'] = 'BEARISH'

    # Merge H1 Trend into 5m data using merge_asof
    df_week_5m = pd.merge_asof(
        df_week_5m.sort_values('timestamp'),
        df_1h[['timestamp', 'h1_ema21', 'h1_ema50', 'h1_trend']].sort_values('timestamp'),
        on='timestamp',
        direction='backward'
    )

    # Compute M5 EMA(21)
    df_week_5m['m5_ema21'] = df_week_5m['close'].ewm(span=21, adjust=False).mean()

    df_week_5m['hour'] = df_week_5m['timestamp'].dt.hour
    df_week_5m['date'] = df_week_5m['timestamp'].dt.date

    closes = df_week_5m['close'].values
    opens = df_week_5m['open'].values
    highs = df_week_5m['high'].values
    lows = df_week_5m['low'].values
    times = df_week_5m['timestamp'].dt.strftime('%Y-%m-%d %H:%M UTC').values
    hours = df_week_5m['hour'].values
    h1_trends = df_week_5m['h1_trend'].values
    m5_ema21 = df_week_5m['m5_ema21'].values
    n = len(df_week_5m)

    spread_estimate = 0.15  # $0.15 spread estimate (1.5 pips)
    pip_size = 0.10        # $0.10 per pip on Gold ($1.00 move = 10 pips)
    account_balance = 10000.0
    risk_pct = 0.01        # 1% Account Risk ($100) per trade split into 3 tickets

    trades = []
    triggered_bars = set()

    for i in range(10, n - 24):
        # STEP 1: Closed Candle Indexing (t is the closed candle at index i)
        t = i
        t_time = times[t]
        hr = hours[t]

        # STEP 2: Commercial Session Window Filtering (06:00 - 20:00 UTC)
        if not (6 <= hr <= 20):
            continue

        # STEP 3: H1 Macro Trend Alignment
        h1_trend = h1_trends[t]
        if h1_trend == 'NEUTRAL':
            continue

        # STEP 4: M5 FVG Displacement Calculation across [t-2, t-1, t]
        # Bullish FVG: Low[t] - High[t-2] >= $0.15
        # Bearish FVG: Low[t-2] - High[t] >= $0.15
        bull_fvg_pips = (lows[t] - highs[t-2]) / pip_size
        bear_fvg_pips = (lows[t-2] - highs[t]) / pip_size

        is_bull_fvg = (lows[t] > highs[t-2]) and (bull_fvg_pips >= 1.5)
        is_bear_fvg = (highs[t] < lows[t-2]) and (bear_fvg_pips >= 1.5)

        # STEP 5: Institutional Liquidity Sweep (prior 5-bar low/high relative to M5 EMA21)
        prior_5_low = np.min(lows[max(0, t-5):t])
        prior_5_high = np.max(highs[max(0, t-5):t])

        bull_sweep = (prior_5_low <= m5_ema21[t])
        bear_sweep = (prior_5_high >= m5_ema21[t])

        # STEP 6: Micro-Structure Close Confirmation
        bull_signal = (h1_trend == 'BULLISH') and is_bull_fvg and bull_sweep and (closes[t] > m5_ema21[t])
        bear_signal = (h1_trend == 'BEARISH') and is_bear_fvg and bear_sweep and (closes[t] < m5_ema21[t])

        if not (bull_signal or bear_signal):
            continue

        # STEP 9: Same-Candle Bar Cooldown Guard
        if t in triggered_bars:
            continue
        triggered_bars.add(t)

        # STEP 7: Structural Entry, Stop Loss & 3-Burst Target Matrix
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

            # Ticket lot sizing (1/3 risk each ticket)
            risk_dist = entry_price - sl_price
            lots_total = (account_balance * risk_pct) / (risk_dist * 100.0)
            lot_per_ticket = lots_total / 3.0

            # Simulate 3-Burst Exits over next 24 bars (2 hours)
            t1_hit, t2_hit, t3_hit = False, False, False
            sl_hit = False
            exit_p = closes[min(t+24, n-1)]

            for k in range(t+1, min(t+25, n)):
                if lows[k] <= sl_price:
                    sl_hit = True
                    exit_p = sl_price
                    break
                
                if not t1_hit and highs[k] >= tp1: t1_hit = True
                if not t2_hit and highs[k] >= tp2: t2_hit = True
                if not t3_hit and highs[k] >= tp3: t3_hit = True

                if t1_hit and t2_hit and t3_hit:
                    break

            # Calculate total dollar PnL across 3 tickets
            pnl_t1 = (-lot_per_ticket * (entry_price - sl_price) * 100.0) if sl_hit else ((lot_per_ticket * (tp1 - entry_price) * 100.0) if t1_hit else (lot_per_ticket * (exit_p - entry_price) * 100.0))
            pnl_t2 = (-lot_per_ticket * (entry_price - sl_price) * 100.0) if sl_hit else ((lot_per_ticket * (tp2 - entry_price) * 100.0) if t2_hit else (lot_per_ticket * (exit_p - entry_price) * 100.0))
            pnl_t3 = (-lot_per_ticket * (entry_price - sl_price) * 100.0) if sl_hit else ((lot_per_ticket * (tp3 - entry_price) * 100.0) if t3_hit else (lot_per_ticket * (exit_p - entry_price) * 100.0))

            total_trade_pnl = pnl_t1 + pnl_t2 + pnl_t3
            win = (total_trade_pnl > 0)

            trades.append({
                'time': t_time, 'dir': 'BUY', 'entry': entry_price, 'sl': sl_price,
                'sl_pips': sl_pips, 'tp1': tp1, 'tp2': tp2, 'tp3': tp3,
                't1_hit': t1_hit, 't2_hit': t2_hit, 't3_hit': t3_hit, 'sl_hit': sl_hit,
                'pnl': total_trade_pnl, 'win': win
            })

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
                if highs[k] >= sl_price:
                    sl_hit = True
                    exit_p = sl_price
                    break

                if not t1_hit and lows[k] <= tp1: t1_hit = True
                if not t2_hit and lows[k] <= tp2: t2_hit = True
                if not t3_hit and lows[k] <= tp3: t3_hit = True

                if t1_hit and t2_hit and t3_hit:
                    break

            pnl_t1 = (-lot_per_ticket * (sl_price - entry_price) * 100.0) if sl_hit else ((lot_per_ticket * (entry_price - tp1) * 100.0) if t1_hit else (lot_per_ticket * (entry_price - exit_p) * 100.0))
            pnl_t2 = (-lot_per_ticket * (sl_price - entry_price) * 100.0) if sl_hit else ((lot_per_ticket * (entry_price - tp2) * 100.0) if t2_hit else (lot_per_ticket * (entry_price - exit_p) * 100.0))
            pnl_t3 = (-lot_per_ticket * (sl_price - entry_price) * 100.0) if sl_hit else ((lot_per_ticket * (entry_price - tp3) * 100.0) if t3_hit else (lot_per_ticket * (entry_price - exit_p) * 100.0))

            total_trade_pnl = pnl_t1 + pnl_t2 + pnl_t3
            win = (total_trade_pnl > 0)

            trades.append({
                'time': t_time, 'dir': 'SELL', 'entry': entry_price, 'sl': sl_price,
                'sl_pips': sl_pips, 'tp1': tp1, 'tp2': tp2, 'tp3': tp3,
                't1_hit': t1_hit, 't2_hit': t2_hit, 't3_hit': t3_hit, 'sl_hit': sl_hit,
                'pnl': total_trade_pnl, 'win': win
            })

    elapsed = time.time() - start_t

    df_tr = pd.DataFrame(trades)

    print("=========================================================================================")
    print(f" MODEL 2: M5 SCALP HYBRID Strategy REPORT (PAST WEEK: AUG 3 - AUG 7, 2026) [{elapsed:.2f}s]")
    print("=========================================================================================")

    if df_tr.empty:
        print("  No trades triggered under strict H1 trend & M5 FVG/Sweep rules.")
        return

    n_tr = len(df_tr)
    wins = len(df_tr[df_tr['win'] == True])
    wr = (wins / n_tr) * 100.0

    gp = df_tr[df_tr['pnl'] > 0]['pnl'].sum()
    gl = abs(df_tr[df_tr['pnl'] < 0]['pnl'].sum())
    pf = (gp / gl) if gl > 0 else gp

    df_tr['eq'] = 10000.0 + df_tr['pnl'].cumsum()
    net_pnl = df_tr['eq'].iloc[-1] - 10000.0
    net_pct = (net_pnl / 10000.0) * 100.0
    peak = df_tr['eq'].cummax()
    max_dd = abs(((df_tr['eq'] - peak) / peak * 100.0).min())

    print(f"  Initial Balance:          $10,000.00")
    print(f"  Final Equity:             ${df_tr['eq'].iloc[-1]:,.2f}")
    print(f"  Net Profit:               ${net_pnl:,.2f} ({net_pct:+.2f}%)")
    print(f"  Total Executed Trades:    {n_tr} Trades")
    print(f"  Win Rate:                 {wr:.1f}% ({wins} Wins / {n_tr - wins} Losses)")
    print(f"  Profit Factor:            {pf:.2f}")
    print(f"  Max Drawdown:             -{max_dd:.2f}%")

    print("\n  DETAILED TRADE LOG:")
    print("-" * 95)
    for idx, r in df_tr.iterrows():
        t1_str = "TP1 WIN" if r['t1_hit'] else ("SL HIT " if r['sl_hit'] else "EXPIRE ")
        t2_str = "TP2 WIN" if r['t2_hit'] else ("SL HIT " if r['sl_hit'] else "EXPIRE ")
        t3_str = "TP3 WIN" if r['t3_hit'] else ("SL HIT " if r['sl_hit'] else "EXPIRE ")
        print(f"  {r['time']} | {r['dir']:<4} | Entry: ${r['entry']:7.2f} | SL: ${r['sl']:7.2f} ({r['sl_pips']:4.1f} p) | {t1_str} | {t2_str} | {t3_str} | PnL: ${r['pnl']:>+7.2f}")

if __name__ == "__main__":
    run_model2_past_week()
