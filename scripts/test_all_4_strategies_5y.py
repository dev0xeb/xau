"""
Unified 5-Year Full Quantitative Backtest for All 4 Master Gold Scalping Strategies:
- Strategy A: 5m FVG Retrace Engine
- Strategy B: London/NY Overlap Volatility Engine (12:00 - 16:00 UTC)
- Strategy C: 15m Double-Sweep Reversal Engine
- Strategy D: Opening Range Breakout (ORB) Engine

Executes across full 5-year dataset (1.98M bars / 396k 5m bars) concurrently in ~2 seconds.
"""

import sys
from pathlib import Path
from datetime import datetime, date, timedelta
import pandas as pd
import numpy as np
from concurrent.futures import ProcessPoolExecutor
import time

def evaluate_strat_a_5y(df_5m):
    """Strategy A: 5m FVG Retrace Engine (Full 5Y)"""
    trades = []
    highs = df_5m['high'].values
    lows = df_5m['low'].values
    closes = df_5m['close'].values
    hours = df_5m['hour'].values
    n = len(df_5m)

    ema1h = pd.Series(closes).ewm(span=144, adjust=False).mean().values

    for i in range(5, n - 12):
        h = hours[i]
        if not ((7 <= h < 10) or (12 <= h < 16)):
            continue

        trend_bull = closes[i] > ema1h[i]
        trend_bear = closes[i] < ema1h[i]

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

    return compile_metrics("Strategy A (5m FVG Retrace)", trades)


def evaluate_strat_b_5y(df_5m):
    """Strategy B: London/NY Overlap Volatility Engine (12:00 - 16:00 UTC)"""
    trades = []
    highs = df_5m['high'].values
    lows = df_5m['low'].values
    closes = df_5m['close'].values
    hours = df_5m['hour'].values
    n = len(df_5m)

    ema1h = pd.Series(closes).ewm(span=144, adjust=False).mean().values

    for i in range(5, n - 12):
        h = hours[i]
        if not (12 <= h < 16):
            continue

        trend_bull = closes[i] > ema1h[i]
        trend_bear = closes[i] < ema1h[i]

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

    return compile_metrics("Strategy B (Overlap Volatility)", trades)


def evaluate_strat_c_5y(df_5m):
    """Strategy C: 15m Double-Sweep Reversal Engine"""
    trades = []
    highs = df_5m['high'].values
    lows = df_5m['low'].values
    closes = df_5m['close'].values
    hours = df_5m['hour'].values
    n = len(df_5m)

    ema1h = pd.Series(closes).ewm(span=144, adjust=False).mean().values

    for i in range(15, n - 8):
        h = hours[i]
        if not ((7 <= h < 10) or (12 <= h < 16)):
            continue

        trend_bull = closes[i] > ema1h[i]
        trend_bear = closes[i] < ema1h[i]

        swing_high = np.max(highs[i-15:i])
        swing_low = np.min(lows[i-15:i])

        # Bullish Sweep: Low < swing_low, Close > swing_low
        if trend_bull and lows[i] < swing_low and closes[i] > swing_low:
            sweep_depth = swing_low - lows[i]
            if 0.50 <= sweep_depth <= 2.50:
                sl = swing_low - 1.20
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
                sl = swing_high + 1.20
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

    return compile_metrics("Strategy C (15m Double Sweep)", trades)


def evaluate_strat_d_5y(df_5m):
    """Strategy D: Opening Range Breakout (ORB) Engine (07:00 & 13:30 UTC Opens)"""
    trades = []
    highs = df_5m['high'].values
    lows = df_5m['low'].values
    closes = df_5m['close'].values
    hours = df_5m['hour'].values
    minutes = df_5m['minute'].values
    n = len(df_5m)

    for i in range(3, n - 12):
        is_london_orb = (hours[i] == 7 and minutes[i] == 15)
        is_ny_orb = (hours[i] == 13 and minutes[i] == 45)

        if not (is_london_orb or is_ny_orb):
            continue

        orb_high = np.max(highs[i-3:i])
        orb_low = np.min(lows[i-3:i])
        orb_range = orb_high - orb_low

        if 1.00 <= orb_range <= 8.00:
            c = closes[i]

            if c > orb_high:
                sl = (orb_high + orb_low) / 2.0
                risk = c - sl
                if 0.80 <= risk <= 4.00:
                    tp1 = c + (1.5 * risk)
                    tp2 = c + (2.5 * risk)

                    fut_h = highs[i+1:i+13]
                    fut_l = lows[i+1:i+13]

                    if np.max(fut_h) >= tp2:
                        trades.append({'pnl': 2.0, 'win': True})
                    elif np.max(fut_h) >= tp1:
                        trades.append({'pnl': 0.75, 'win': True})
                    elif np.min(fut_l) <= sl:
                        trades.append({'pnl': -1.0, 'win': False})

            elif c < orb_low:
                sl = (orb_high + orb_low) / 2.0
                risk = sl - c
                if 0.80 <= risk <= 4.00:
                    tp1 = c - (1.5 * risk)
                    tp2 = c - (2.5 * risk)

                    fut_h = highs[i+1:i+13]
                    fut_l = lows[i+1:i+13]

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
    print(" UNIFIED FULL 5-YEAR MULTI-STRATEGY BENCHMARK (2021-2026)")
    print("=" * 85)

    start_t = time.time()

    df_5m = pd.read_parquet(proc_5m_path)
    df_5m['timestamp'] = pd.to_datetime(df_5m['timestamp'])
    df_5m = df_5m.sort_values('timestamp').reset_index(drop=True)

    df_5m['hour'] = df_5m['timestamp'].dt.hour
    df_5m['minute'] = df_5m['timestamp'].dt.minute

    print(f" Loaded Full 5-Year Parquet Dataset: {len(df_5m):,} 5m Bars.")
    print(" Executing All 4 Master Strategies Simultaneously in Parallel...\n")

    results = []
    with ProcessPoolExecutor() as executor:
        f_a = executor.submit(evaluate_strat_a_5y, df_5m)
        f_b = executor.submit(evaluate_strat_b_5y, df_5m)
        f_c = executor.submit(evaluate_strat_c_5y, df_5m)
        f_d = executor.submit(evaluate_strat_d_5y, df_5m)

        results = [f_a.result(), f_b.result(), f_c.result(), f_d.result()]

    elapsed = time.time() - start_t

    print("=" * 85)
    print(f" FULL 5-YEAR BENCHMARK COMPLETE IN {elapsed:.2f} SECONDS!")
    print("=" * 85)

    df_res = pd.DataFrame(results)
    
    print("\n" + "-" * 85)
    print(f" {'STRATEGY NAME':<30} | {'TRADES':<7} | {'WIN RATE':<9} | {'NET PROFIT ($)':<14} | {'PF':<6} | {'MAX DD':<8}")
    print("-" * 85)

    for idx, r in df_res.iterrows():
        pnl_str = f"+${r['net_profit_dollars']:,.2f} ({r['net_profit_pct']:+.1f}%)" if r['net_profit_dollars'] >= 0 else f"-${abs(r['net_profit_dollars']):,.2f} ({r['net_profit_pct']:+.1f}%)"
        print(f" {r['name']:<30} | {r['total_trades']:<7} | {r['win_rate']:>7.1f}% | {pnl_str:<14} | {r['profit_factor']:>5.2f} | {r['max_dd_pct']:>6.1f}%")

    print("-" * 85 + "\n")

if __name__ == "__main__":
    main()
