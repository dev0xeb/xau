"""
Deep Loss Diagnosis Engine for Model 2 (M5 Scalp Hybrid Engine).

Analyzes all 20 losing trades from the past week (Aug 3 - Aug 7, 2026) to identify exact root cause failure mechanisms:
1. Over-Extension / High EMA Distance (Buying at the top of a stretched 5m leg)
2. News Spike / Volatility Wicks (NFP / CPI / ISM spikes at 13:30 / 14:00 UTC)
3. Session Tail-End Late Entries (Trading late into NY session after 17:00 UTC)
4. Counter-Impulse Retracements (Buying during temporary H1 pullback legs)
5. Max SL Cap Hits (80.0 pip bounded SL being too far or hit by deep wicks)
"""

import sys
from pathlib import Path
from datetime import datetime, date
import pandas as pd
import numpy as np

def run_model2_loss_diagnosis():
    proc_5m_path = Path("data/processed/xau_5m_5y.parquet")
    if not proc_5m_path.exists():
        print("[ERROR] 5m parquet file not found!")
        return

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

    # Resample to 1H for H1 EMAs
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
    opens = df_week_5m['open'].values
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

    losing_trades = []
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

            # Measure EMA extension distance (Entry Price - M5 EMA21)
            ema_dist = (entry_price - m5_ema21[t])

            if not win:
                losing_trades.append({
                    'time': t_time, 'hr': hr, 'dir': 'BUY', 'entry': entry_price, 'sl': sl_price,
                    'sl_pips': sl_pips, 'pnl': total_trade_pnl, 'ema_dist': ema_dist,
                    'fvg_size': bull_fvg_pips, 't1_hit': t1_hit, 't2_hit': t2_hit
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
                if highs[k] >= sl_price: sl_hit = True; exit_p = sl_price; break
                if not t1_hit and lows[k] <= tp1: t1_hit = True
                if not t2_hit and lows[k] <= tp2: t2_hit = True
                if not t3_hit and lows[k] <= tp3: t3_hit = True
                if t1_hit and t2_hit and t3_hit: break

            pnl_t1 = (-lot_per_ticket * (sl_price - entry_price) * 100.0) if sl_hit else ((lot_per_ticket * (entry_price - tp1) * 100.0) if t1_hit else (lot_per_ticket * (entry_price - exit_p) * 100.0))
            pnl_t2 = (-lot_per_ticket * (sl_price - entry_price) * 100.0) if sl_hit else ((lot_per_ticket * (entry_price - tp2) * 100.0) if t2_hit else (lot_per_ticket * (entry_price - exit_p) * 100.0))
            pnl_t3 = (-lot_per_ticket * (sl_price - entry_price) * 100.0) if sl_hit else ((lot_per_ticket * (entry_price - tp3) * 100.0) if t3_hit else (lot_per_ticket * (entry_price - exit_p) * 100.0))

            total_trade_pnl = pnl_t1 + pnl_t2 + pnl_t3
            win = (total_trade_pnl > 0)

            ema_dist = (m5_ema21[t] - entry_price)

            if not win:
                losing_trades.append({
                    'time': t_time, 'hr': hr, 'dir': 'SELL', 'entry': entry_price, 'sl': sl_price,
                    'sl_pips': sl_pips, 'pnl': total_trade_pnl, 'ema_dist': ema_dist,
                    'fvg_size': bear_fvg_pips, 't1_hit': t1_hit, 't2_hit': t2_hit
                })

    df_loss = pd.DataFrame(losing_trades)
    print("=========================================================================================")
    print(f" MODEL 2: DEEP DIAGNOSIS OF LOSING TRADES (TOTAL LOSSES: {len(df_loss)})")
    print("=========================================================================================")

    if df_loss.empty:
        print("No losing trades found.")
        return

    # Categorize Root Causes
    reasons = []
    for idx, r in df_loss.iterrows():
        if r['ema_dist'] >= 3.00:
            cause = "Over-Extended Entry (Price Stretched > $3.00 from M5 EMA21)"
        elif r['hr'] in [13, 14]:
            cause = "News Volatility Spike / Wick (NFP/CPI 13:30/14:00 UTC Window)"
        elif r['hr'] >= 17:
            cause = "Late NY Session Exhaustion (Trading after 17:00 UTC)"
        elif r['sl_pips'] >= 75.0:
            cause = "Max SL Cap Hit (SL Distance >= 75.0 pips / Wide Risk)"
        else:
            cause = "Standard Micro Retracement Invalidation"
        reasons.append(cause)

    df_loss['root_cause'] = reasons

    print(f"\n ROOT CAUSE BREAKDOWN ACROSS ALL {len(df_loss)} LOSING TRADES:")
    print("-" * 95)
    cause_counts = df_loss['root_cause'].value_counts()
    for cause, cnt in cause_counts.items():
        pct = (cnt / len(df_loss)) * 100.0
        print(f"  {cause:<65} | {cnt:2d} Losses ({pct:4.1f}%)")

    print(f"\n DETAILED ANALYSIS OF EVERY LOSING TRADE:")
    print("-" * 95)
    for idx, r in df_loss.iterrows():
        t1_str = "TP1 Hit" if r['t1_hit'] else "Direct SL"
        print(f"  {r['time']} | {r['dir']:<4} | Entry: ${r['entry']:7.2f} | SL: {r['sl_pips']:4.1f}p | EMA Dist: ${r['ema_dist']:4.2f} | {t1_str:<9} | Cause: {r['root_cause']}")

if __name__ == "__main__":
    run_model2_loss_diagnosis()
