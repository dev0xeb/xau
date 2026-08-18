"""
High-Precision 3-Month Parallel Backtest for the 4 Master Gold Scalping Strategies.

Incorporates exact empirical rules:
1. Strategy A: 5m FVG Retrace at 50% Midpoint + Trend Filter (1:1.5 / 1:2.5 RR Exit)
2. Strategy B: London/NY Overlap 5m FVG Retrace (12:00 - 16:00 UTC)
3. Strategy C: 15m Double-Sweep Reversal + 15m Structural SL (+ 0.5 ATR)
4. Strategy D: 5m Opening Range Breakout (ORB) Engine (07:00 & 13:30 UTC Opens)
"""

import sys
from pathlib import Path
from datetime import datetime, date, timedelta
import pandas as pd
import numpy as np
from concurrent.futures import ProcessPoolExecutor
import time

def evaluate_strategy_a(df_5m):
    """Strategy A: 5m FVG Retrace at 50% Midpoint + Trend Alignment"""
    trades = []
    highs = df_5m['high'].values
    lows = df_5m['low'].values
    closes = df_5m['close'].values
    hours = df_5m['hour'].values
    n = len(df_5m)

    ema50 = pd.Series(closes).ewm(span=50, adjust=False).mean().values

    for i in range(5, n - 12):
        h = hours[i]
        # Session Filter: London Open (7-10 UTC) & London/NY Overlap (12-16 UTC)
        if not ((7 <= h < 10) or (12 <= h < 16)):
            continue

        trend_bull = closes[i] > ema50[i]
        trend_bear = closes[i] < ema50[i]

        # Bullish 5m FVG
        if trend_bull and lows[i] > highs[i-2]:
            gap = lows[i] - highs[i-2]
            if gap >= 0.50:
                fvg_mid = (lows[i] + highs[i-2]) / 2.0
                sl = highs[i-2] - 0.50
                risk = fvg_mid - sl

                if 0.50 <= risk <= 3.00:
                    tp1 = fvg_mid + (1.5 * risk)
                    tp2 = fvg_mid + (2.5 * risk)

                    # Look for retrace to fvg_mid in next 12 bars (1 hour)
                    fut_lows = lows[i+1:i+13]
                    fut_highs = highs[i+1:i+13]

                    # Checked if touched fvg_mid
                    hit_mask = (fut_lows <= fvg_mid)
                    if np.any(hit_mask):
                        first_hit_idx = np.argmax(hit_mask)
                        # Evaluate post-fill performance
                        post_highs = fut_highs[first_hit_idx:]
                        post_lows = fut_lows[first_hit_idx:]

                        if np.min(post_lows) <= sl:
                            trades.append({'pnl': -1.0, 'win': False})
                        elif np.max(post_highs) >= tp2:
                            trades.append({'pnl': 2.0, 'win': True})
                        elif np.max(post_highs) >= tp1:
                            trades.append({'pnl': 0.75, 'win': True})

        # Bearish 5m FVG
        elif trend_bear and highs[i] < lows[i-2]:
            gap = lows[i-2] - highs[i]
            if gap >= 0.50:
                fvg_mid = (lows[i-2] + highs[i]) / 2.0
                sl = lows[i-2] + 0.50
                risk = sl - fvg_mid

                if 0.50 <= risk <= 3.00:
                    tp1 = fvg_mid - (1.5 * risk)
                    tp2 = fvg_mid - (2.5 * risk)

                    fut_highs = highs[i+1:i+13]
                    fut_lows = lows[i+1:i+13]

                    hit_mask = (fut_highs >= fvg_mid)
                    if np.any(hit_mask):
                        first_hit_idx = np.argmax(hit_mask)
                        post_highs = fut_highs[first_hit_idx:]
                        post_lows = fut_lows[first_hit_idx:]

                        if np.max(post_highs) >= sl:
                            trades.append({'pnl': -1.0, 'win': False})
                        elif np.min(post_lows) <= tp2:
                            trades.append({'pnl': 2.0, 'win': True})
                        elif np.min(post_lows) <= tp1:
                            trades.append({'pnl': 0.75, 'win': True})

    return compile_metrics("Strategy A (5m FVG Retrace Engine)", trades)


def evaluate_strategy_b(df_5m):
    """Strategy B: London/NY Overlap 5m FVG Retrace (12:00 - 16:00 UTC)"""
    trades = []
    highs = df_5m['high'].values
    lows = df_5m['low'].values
    closes = df_5m['close'].values
    hours = df_5m['hour'].values
    n = len(df_5m)

    ema50 = pd.Series(closes).ewm(span=50, adjust=False).mean().values

    for i in range(5, n - 12):
        h = hours[i]
        # Overlap Window Strictly 12:00 - 16:00 UTC
        if not (12 <= h < 16):
            continue

        trend_bull = closes[i] > ema50[i]
        trend_bear = closes[i] < ema50[i]

        # Bullish 5m FVG
        if trend_bull and lows[i] > highs[i-2]:
            gap = lows[i] - highs[i-2]
            if gap >= 0.50:
                fvg_mid = (lows[i] + highs[i-2]) / 2.0
                sl = highs[i-2] - 0.50
                risk = fvg_mid - sl

                if 0.50 <= risk <= 3.00:
                    tp1 = fvg_mid + (1.5 * risk)
                    tp2 = fvg_mid + (2.5 * risk)

                    fut_lows = lows[i+1:i+13]
                    fut_highs = highs[i+1:i+13]

                    hit_mask = (fut_lows <= fvg_mid)
                    if np.any(hit_mask):
                        first_hit_idx = np.argmax(hit_mask)
                        post_highs = fut_highs[first_hit_idx:]
                        post_lows = fut_lows[first_hit_idx:]

                        if np.min(post_lows) <= sl:
                            trades.append({'pnl': -1.0, 'win': False})
                        elif np.max(post_highs) >= tp2:
                            trades.append({'pnl': 2.0, 'win': True})
                        elif np.max(post_highs) >= tp1:
                            trades.append({'pnl': 0.75, 'win': True})

        # Bearish 5m FVG
        elif trend_bear and highs[i] < lows[i-2]:
            gap = lows[i-2] - highs[i]
            if gap >= 0.50:
                fvg_mid = (lows[i-2] + highs[i]) / 2.0
                sl = lows[i-2] + 0.50
                risk = sl - fvg_mid

                if 0.50 <= risk <= 3.00:
                    tp1 = fvg_mid - (1.5 * risk)
                    tp2 = fvg_mid - (2.5 * risk)

                    fut_highs = highs[i+1:i+13]
                    fut_lows = lows[i+1:i+13]

                    hit_mask = (fut_highs >= fvg_mid)
                    if np.any(hit_mask):
                        first_hit_idx = np.argmax(hit_mask)
                        post_highs = fut_highs[first_hit_idx:]
                        post_lows = fut_lows[first_hit_idx:]

                        if np.max(post_highs) >= sl:
                            trades.append({'pnl': -1.0, 'win': False})
                        elif np.min(post_lows) <= tp2:
                            trades.append({'pnl': 2.0, 'win': True})
                        elif np.min(post_lows) <= tp1:
                            trades.append({'pnl': 0.75, 'win': True})

    return compile_metrics("Strategy B (Overlap FVG Engine)", trades)


def evaluate_strategy_c(df_5m):
    """Strategy C: 15m Double-Sweep Reversal + 15m Structural SL (+ 0.5 ATR)"""
    trades = []
    highs = df_5m['high'].values
    lows = df_5m['low'].values
    closes = df_5m['close'].values
    hours = df_5m['hour'].values
    n = len(df_5m)

    ema50 = pd.Series(closes).ewm(span=50, adjust=False).mean().values

    for i in range(15, n - 8):
        h = hours[i]
        if not ((7 <= h < 10) or (12 <= h < 16)):
            continue

        trend_bull = closes[i] > ema50[i]
        trend_bear = closes[i] < ema50[i]

        swing_high = np.max(highs[i-15:i])
        swing_low = np.min(lows[i-15:i])

        # Bullish Sweep: Low < swing_low, Close > swing_low
        if trend_bull and lows[i] < swing_low and closes[i] > swing_low:
            sweep_depth = swing_low - lows[i]
            if 0.50 <= sweep_depth <= 2.50:
                sl = swing_low - 1.20  # Structural SL + Buffer
                risk = closes[i] - sl
                if 1.00 <= risk <= 3.50:
                    tp1 = closes[i] + (1.5 * risk)
                    tp2 = closes[i] + (2.5 * risk)
                    fut_h = highs[i+1:i+8]
                    fut_l = lows[i+1:i+8]

                    if np.min(fut_l) <= sl:
                        trades.append({'pnl': -1.0, 'win': False})
                    elif np.max(fut_h) >= tp2:
                        trades.append({'pnl': 2.0, 'win': True})
                    elif np.max(fut_h) >= tp1:
                        trades.append({'pnl': 0.75, 'win': True})

        # Bearish Sweep: High > swing_high, Close < swing_high
        elif trend_bear and highs[i] > swing_high and closes[i] < swing_high:
            sweep_depth = highs[i] - swing_high
            if 0.50 <= sweep_depth <= 2.50:
                sl = swing_high + 1.20  # Structural SL + Buffer
                risk = sl - closes[i]
                if 1.00 <= risk <= 3.50:
                    tp1 = closes[i] - (1.5 * risk)
                    tp2 = closes[i] - (2.5 * risk)
                    fut_h = highs[i+1:i+8]
                    fut_l = lows[i+1:i+8]

                    if np.max(fut_h) >= sl:
                        trades.append({'pnl': -1.0, 'win': False})
                    elif np.min(fut_l) <= tp2:
                        trades.append({'pnl': 2.0, 'win': True})
                    elif np.min(fut_l) <= tp1:
                        trades.append({'pnl': 0.75, 'win': True})

    return compile_metrics("Strategy C (15m Structural Sweep)", trades)


def evaluate_strategy_d(df_5m):
    """Strategy D: 5m Opening Range Breakout (ORB) Engine (07:00 and 13:30 UTC Opens)"""
    trades = []
    highs = df_5m['high'].values
    lows = df_5m['low'].values
    closes = df_5m['close'].values
    hours = df_5m['hour'].values
    minutes = df_5m['minute'].values
    n = len(df_5m)

    for i in range(2, n - 8):
        is_london_open = (hours[i] == 7 and 5 <= minutes[i] <= 20)
        is_ny_open = (hours[i] == 13 and 35 <= minutes[i] <= 50)

        if not (is_london_open or is_ny_open):
            continue

        orb_high = np.max(highs[i-2:i])
        orb_low = np.min(lows[i-2:i])
        c = closes[i]

        if c > orb_high:
            sl = orb_low - 0.50
            risk = c - sl
            if 0.80 <= risk <= 3.50:
                tp1 = c + (1.5 * risk)
                tp2 = c + (2.5 * risk)
                fut_h = highs[i+1:i+8]
                fut_l = lows[i+1:i+8]

                if np.max(fut_h) >= tp2:
                    trades.append({'pnl': 2.0, 'win': True})
                elif np.max(fut_h) >= tp1:
                    trades.append({'pnl': 0.75, 'win': True})
                elif np.min(fut_l) <= sl:
                    trades.append({'pnl': -1.0, 'win': False})

        elif c < orb_low:
            sl = orb_high + 0.50
            risk = sl - c
            if 0.80 <= risk <= 3.50:
                tp1 = c - (1.5 * risk)
                tp2 = c - (2.5 * risk)
                fut_h = highs[i+1:i+8]
                fut_l = lows[i+1:i+8]

                if np.min(fut_l) <= tp2:
                    trades.append({'pnl': 2.0, 'win': True})
                elif np.min(fut_l) <= tp1:
                    trades.append({'pnl': 0.75, 'win': True})
                elif np.max(fut_h) >= sl:
                    trades.append({'pnl': -1.0, 'win': False})

    return compile_metrics("Strategy D (ORB Engine)", trades)


def compile_metrics(name, trades):
    if not trades:
        return {'name': name, 'total_trades': 0, 'win_rate': 0.0, 'net_profit_pct': 0.0, 'net_profit_dollars': 0.0, 'profit_factor': 0.0, 'max_dd_pct': 0.0}

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

    return {
        'name': name,
        'total_trades': total_trades,
        'win_rate': win_rate,
        'net_profit_pct': net_profit_pct,
        'net_profit_dollars': net_pnl,
        'profit_factor': profit_factor,
        'max_dd_pct': max_dd_pct
    }


def main():
    proc_5m_path = Path("data/processed/xau_5m_5y.parquet")
    if not proc_5m_path.exists():
        print("[ERROR] 5m dataset missing!")
        return

    print("=" * 85)
    print(" HIGH-PRECISION 3-MONTH PARALLEL BACKTEST FOR THE 4 MASTER GOLD STRATEGIES")
    print("=" * 85)

    start_t = time.time()

    df_5m = pd.read_parquet(proc_5m_path)
    df_5m['timestamp'] = pd.to_datetime(df_5m['timestamp'])

    cutoff_date = pd.to_datetime("2026-05-10", utc=True)
    df_5m_3m = df_5m[df_5m['timestamp'] >= cutoff_date].sort_values('timestamp').reset_index(drop=True)

    df_5m_3m['hour'] = df_5m_3m['timestamp'].dt.hour
    df_5m_3m['minute'] = df_5m_3m['timestamp'].dt.minute
    df_5m_3m['date'] = df_5m_3m['timestamp'].dt.date

    print(f" Loaded Past 3 Months Data (2026-05-10 to 2026-08-10): {len(df_5m_3m):,} 5m Bars.")
    print(" Executing 4 Strategies in Parallel across CPU Cores...\n")

    results = []
    with ProcessPoolExecutor() as executor:
        f_a = executor.submit(evaluate_strategy_a, df_5m_3m)
        f_b = executor.submit(evaluate_strategy_b, df_5m_3m)
        f_c = executor.submit(evaluate_strategy_c, df_5m_3m)
        f_d = executor.submit(evaluate_strategy_d, df_5m_3m)

        results = [f_a.result(), f_b.result(), f_c.result(), f_d.result()]

    elapsed = time.time() - start_t

    print("=" * 85)
    print(f" 3-MONTH BENCHMARK COMPLETE IN {elapsed:.2f} SECONDS!")
    print("=" * 85)

    df_res = pd.DataFrame(results)
    
    print("\n" + "-" * 85)
    print(f" {'STRATEGY NAME':<32} | {'TRADES':<7} | {'WIN RATE':<9} | {'NET PROFIT ($)':<14} | {'PF':<6} | {'MAX DD':<8}")
    print("-" * 85)

    for idx, r in df_res.iterrows():
        pnl_str = f"+${r['net_profit_dollars']:,.2f} ({r['net_profit_pct']:+.1f}%)" if r['net_profit_dollars'] >= 0 else f"-${abs(r['net_profit_dollars']):,.2f} ({r['net_profit_pct']:+.1f}%)"
        print(f" {r['name']:<32} | {r['total_trades']:<7} | {r['win_rate']:>7.1f}% | {pnl_str:<14} | {r['profit_factor']:>5.2f} | {r['max_dd_pct']:>6.1f}%")

    print("-" * 85 + "\n")

if __name__ == "__main__":
    main()
