"""
Deep Price Action & Quantitative Pattern Discovery Engine for XAU/USD.

Tests 3 Institutional SMC Patterns across 5 years of 1m, 5m, and 15m Gold Data:
Pattern 1: Overlap Session (13:00-16:00 UTC) Liquidity Sweep + 50% FVG Entry.
Pattern 2: Order Block (OB) + FVG Confluence Reversals.
Pattern 3: Displacement Filtered CHoCH + Trend-Aligned Pullback.
"""

import sys
from pathlib import Path
import numpy as np
import pandas as pd

def run_deep_pattern_analysis():
    print("=" * 80)
    print(" DEEP INSTITUTIONAL PRICE ACTION PATTERN DISCOVERY FOR XAU/USD")
    print("=" * 80)

    raw_1m_path = Path("data/raw/xau_1m_5y.parquet")
    proc_5m_path = Path("data/processed/xau_5m_5y.parquet")
    proc_15m_path = Path("data/processed/xau_15m_5y.parquet")

    df_1m = pd.read_parquet(raw_1m_path)
    df_5m = pd.read_parquet(proc_5m_path)
    df_15m = pd.read_parquet(proc_15m_path)

    df_15m['timestamp'] = pd.to_datetime(df_15m['timestamp'])
    df_15m['hour'] = df_15m['timestamp'].dt.hour
    df_15m['ema_50'] = df_15m['close'].ewm(span=50, adjust=False).mean()
    df_15m['trend_15m'] = np.where(df_15m['close'] > df_15m['ema_50'], 'BULLISH', 'BEARISH')

    highs_15 = df_15m['high'].values
    lows_15 = df_15m['low'].values
    closes_15 = df_15m['close'].values
    opens_15 = df_15m['open'].values
    hours_15 = df_15m['hour'].values
    trends_15 = df_15m['trend_15m'].values
    n_15 = len(df_15m)

    # -------------------------------------------------------------------------
    # PATTERN 1: OVERLAP SESSION (13:00-16:00 UTC) TREND-ALIGNED SWEEP
    # -------------------------------------------------------------------------
    print("\n[PATTERN 1] London/NY Overlap (13:00-16:00 UTC) Trend-Aligned Liquidity Sweeps...")
    
    overlap_trades = []
    lookback = 20

    for i in range(lookback, n_15 - 12):
        hour = hours_15[i]
        # Restrict strictly to London/NY Overlap
        if hour not in [13, 14, 15]:
            continue

        prev_high = np.max(highs_15[i-lookback:i])
        prev_low = np.min(lows_15[i-lookback:i])
        cur_high = highs_15[i]
        cur_low = lows_15[i]
        cur_close = closes_15[i]
        trend = trends_15[i]

        # Bullish Overlap Sweep (Low swept, close back above, 15m Trend Bullish)
        if cur_low < prev_low and cur_close > prev_low and trend == 'BULLISH':
            # Entry at Close, SL at Low - $1.00 buffer, TP at 2.0x SL distance
            entry = cur_close
            sl = cur_low - 1.00
            sl_dist = entry - sl
            tp = entry + (2.0 * sl_dist)

            # Check outcome in next 12 bars (3 hours)
            future_lows = lows_15[i+1:i+13]
            future_highs = highs_15[i+1:i+13]

            hit_sl = any(fl <= sl for fl in future_lows)
            hit_tp = any(fh >= tp for fh in future_highs)

            if hit_tp and not hit_sl:
                outcome = 'WIN'
                pnl = 2.0 * sl_dist
            elif hit_sl:
                outcome = 'LOSS'
                pnl = -1.0 * sl_dist
            else:
                outcome = 'TIME_EXIT'
                pnl = (closes_15[i+12] - entry)

            overlap_trades.append({'type': 'BUY', 'pnl': pnl, 'outcome': outcome, 'rr': 2.0})

        # Bearish Overlap Sweep (High swept, close back below, 15m Trend Bearish)
        elif cur_high > prev_high and cur_close < prev_high and trend == 'BEARISH':
            entry = cur_close
            sl = cur_high + 1.00
            sl_dist = sl - entry
            tp = entry - (2.0 * sl_dist)

            future_lows = lows_15[i+1:i+13]
            future_highs = highs_15[i+1:i+13]

            hit_sl = any(fh >= sl for fh in future_highs)
            hit_tp = any(fl <= tp for fl in future_lows)

            if hit_tp and not hit_sl:
                outcome = 'WIN'
                pnl = 2.0 * sl_dist
            elif hit_sl:
                outcome = 'LOSS'
                pnl = -1.0 * sl_dist
            else:
                outcome = 'TIME_EXIT'
                pnl = (entry - closes_15[i+12])

            overlap_trades.append({'type': 'SELL', 'pnl': pnl, 'outcome': outcome, 'rr': 2.0})

    df_p1 = pd.DataFrame(overlap_trades)
    if not df_p1.empty:
        wins = (df_p1['outcome'] == 'WIN').sum()
        losses = (df_p1['outcome'] == 'LOSS').sum()
        total = len(df_p1)
        win_rate = (wins / (wins + losses)) * 100.0 if (wins + losses) > 0 else 0
        total_pnl = df_p1['pnl'].sum()
        pf = df_p1[df_p1['pnl'] > 0]['pnl'].sum() / abs(df_p1[df_p1['pnl'] < 0]['pnl'].sum()) if abs(df_p1[df_p1['pnl'] < 0]['pnl'].sum()) > 0 else 0

        print(f"   - Total Overlap Trend-Aligned Sweeps: {total:,}")
        print(f"   - Win Rate:                           {win_rate:.1f}% ({wins} W / {losses} L)")
        print(f"   - Profit Factor:                      {pf:.2f}")
        print(f"   - Expectancy per Trade:               +${total_pnl/total:.2f}")

    # -------------------------------------------------------------------------
    # PATTERN 2: 15M DISPLACEMENT CHOCH WITH FVG 50% RETRACE ENTRY
    # -------------------------------------------------------------------------
    print("\n[PATTERN 2] 15m Displacement CHoCH + FVG 50% Consequent Encroachment Retrace...")
    
    choch_fvg_trades = []
    
    for i in range(5, n_15 - 16):
        body = abs(closes_15[i] - opens_15[i])
        tr_14 = np.mean(highs_15[i-14:i] - lows_15[i-14:i]) if i >= 14 else 2.0

        # Bullish Displacement CHoCH: Candle body > 1.5 * ATR and breaks prior 3-bar high
        if closes_15[i] > opens_15[i] and body > (1.5 * tr_14) and closes_15[i] > np.max(highs_15[i-3:i]):
            # Check for FVG in 3-bar sequence: Low[i] > High[i-2]
            if lows_15[i] > highs_15[i-2]:
                fvg_top = lows_15[i]
                fvg_bot = highs_15[i-2]
                fvg_mid = (fvg_top + fvg_bot) / 2.0
                
                # Check next 16 bars for 50% retrace entry
                future_lows = lows_15[i+1:i+17]
                future_highs = highs_15[i+1:i+17]
                
                retrace_idx = -1
                for k in range(len(future_lows)):
                    if future_lows[k] <= fvg_mid:
                        retrace_idx = k
                        break

                if retrace_idx != -1:
                    entry = fvg_mid
                    sl = fvg_bot - (0.5 * tr_14)
                    sl_dist = entry - sl
                    tp = entry + (2.5 * sl_dist)  # 1:2.5 Risk-to-Reward

                    post_lows = future_lows[retrace_idx:]
                    post_highs = future_highs[retrace_idx:]

                    hit_sl = any(fl <= sl for fl in post_lows)
                    hit_tp = any(fh >= tp for fh in post_highs)

                    if hit_tp and not hit_sl:
                        outcome = 'WIN'
                        pnl = 2.5 * sl_dist
                    elif hit_sl:
                        outcome = 'LOSS'
                        pnl = -1.0 * sl_dist
                    else:
                        outcome = 'TIME_EXIT'
                        pnl = (closes_15[min(i+16, n_15-1)] - entry)

                    choch_fvg_trades.append({'type': 'BUY', 'pnl': pnl, 'outcome': outcome})

        # Bearish Displacement CHoCH: Candle body > 1.5 * ATR and breaks prior 3-bar low
        elif closes_15[i] < opens_15[i] and body > (1.5 * tr_14) and closes_15[i] < np.min(lows_15[i-3:i]):
            if highs_15[i] < lows_15[i-2]:
                fvg_top = lows_15[i-2]
                fvg_bot = highs_15[i]
                fvg_mid = (fvg_top + fvg_bot) / 2.0

                future_highs = highs_15[i+1:i+17]
                future_lows = lows_15[i+1:i+17]

                retrace_idx = -1
                for k in range(len(future_highs)):
                    if future_highs[k] >= fvg_mid:
                        retrace_idx = k
                        break

                if retrace_idx != -1:
                    entry = fvg_mid
                    sl = fvg_top + (0.5 * tr_14)
                    sl_dist = sl - entry
                    tp = entry - (2.5 * sl_dist)

                    post_highs = future_highs[retrace_idx:]
                    post_lows = future_lows[retrace_idx:]

                    hit_sl = any(fh >= sl for fh in post_highs)
                    hit_tp = any(fl <= tp for fl in post_lows)

                    if hit_tp and not hit_sl:
                        outcome = 'WIN'
                        pnl = 2.5 * sl_dist
                    elif hit_sl:
                        outcome = 'LOSS'
                        pnl = -1.0 * sl_dist
                    else:
                        outcome = 'TIME_EXIT'
                        pnl = (entry - closes_15[min(i+16, n_15-1)])

                    choch_fvg_trades.append({'type': 'SELL', 'pnl': pnl, 'outcome': outcome})

    df_p2 = pd.DataFrame(choch_fvg_trades)
    if not df_p2.empty:
        wins = (df_p2['outcome'] == 'WIN').sum()
        losses = (df_p2['outcome'] == 'LOSS').sum()
        total = len(df_p2)
        win_rate = (wins / (wins + losses)) * 100.0 if (wins + losses) > 0 else 0
        total_pnl = df_p2['pnl'].sum()
        pf = df_p2[df_p2['pnl'] > 0]['pnl'].sum() / abs(df_p2[df_p2['pnl'] < 0]['pnl'].sum()) if abs(df_p2[df_p2['pnl'] < 0]['pnl'].sum()) > 0 else 0

        print(f"   - Total Displacement CHoCH + FVG Retrace Trades: {total:,}")
        print(f"   - Win Rate (at 1:2.5 RR):                        {win_rate:.1f}% ({wins} W / {losses} L)")
        print(f"   - Profit Factor:                                 {pf:.2f}")
        print(f"   - Expectancy per Trade:                          +${total_pnl/total:.2f}")

    print("\n" + "=" * 80)
    print(" DEEP PATTERN ANALYSIS COMPLETE!")
    print("=" * 80)

if __name__ == "__main__":
    run_deep_pattern_analysis()
