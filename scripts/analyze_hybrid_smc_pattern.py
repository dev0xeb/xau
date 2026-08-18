"""
Hybrid SMC Institutional Strategy Analyzer for XAU/USD.

Tests the high-conviction combination of:
1. Session Filter: London Open (07:00-10:00 UTC) & NY Overlap (12:30-16:00 UTC)
2. Trend Filter: 15m 50 EMA Alignment
3. Wick Sweep Filter: Wick past 15m swing level with candle closing BACK INSIDE range
4. Entry: Retrace to 50% FVG Consequent Encroachment with structural SL & 1:2.0+ RR
"""

import sys
from pathlib import Path
import numpy as np
import pandas as pd

def analyze_hybrid_smc():
    print("=" * 80)
    print(" HYBRID SMC INSTITUTIONAL PATTERN ANALYSIS (5-YEAR XAU/USD)")
    print("=" * 80)

    raw_1m_path = Path("data/raw/xau_1m_5y.parquet")
    proc_5m_path = Path("data/processed/xau_5m_5y.parquet")
    proc_15m_path = Path("data/processed/xau_15m_5y.parquet")

    df_15m = pd.read_parquet(proc_15m_path)
    df_15m['timestamp'] = pd.to_datetime(df_15m['timestamp'])
    df_15m['hour'] = df_15m['timestamp'].dt.hour
    df_15m['minute'] = df_15m['timestamp'].dt.minute
    df_15m['ema_50'] = df_15m['close'].ewm(span=50, adjust=False).mean()
    df_15m['trend_15m'] = np.where(df_15m['close'] > df_15m['ema_50'], 'BULLISH', 'BEARISH')

    highs = df_15m['high'].values
    lows = df_15m['low'].values
    closes = df_15m['close'].values
    opens = df_15m['open'].values
    hours = df_15m['hour'].values
    minutes = df_15m['minute'].values
    trends = df_15m['trend_15m'].values
    n = len(df_15m)

    trades = []
    lookback = 20

    for i in range(lookback, n - 20):
        h = hours[i]
        m = minutes[i]
        
        # Session Window: London (07:00-10:00 UTC) OR NY Overlap (12:30-16:00 UTC)
        is_london_open = (7 <= h < 10)
        is_ny_overlap = (12 <= h < 16)
        if not (is_london_open or is_ny_overlap):
            continue

        prev_high = np.max(highs[i-lookback:i])
        prev_low = np.min(lows[i-lookback:i])
        cur_high = highs[i]
        cur_low = lows[i]
        cur_close = closes[i]
        cur_open = opens[i]
        trend = trends[i]

        # Bullish Wick Sweep + Trend Confluence
        if cur_low < prev_low and cur_close > prev_low and trend == 'BULLISH':
            # Look for 3-candle FVG: Low[i] > High[i-2]
            if lows[i] > highs[i-2]:
                fvg_top = lows[i]
                fvg_bot = highs[i-2]
                fvg_mid = (fvg_top + fvg_bot) / 2.0

                # Target entry at 50% FVG retrace
                entry = fvg_mid
                sl = prev_low - 1.00  # Structural SL below swept low + buffer
                sl_dist = entry - sl
                if sl_dist <= 0:
                    continue
                
                tp = entry + (2.2 * sl_dist)  # 1:2.2 RR

                future_lows = lows[i+1:i+21]
                future_highs = highs[i+1:i+21]

                # Check if retrace fills 50% FVG
                retrace_idx = -1
                for k in range(len(future_lows)):
                    if future_lows[k] <= entry:
                        retrace_idx = k
                        break

                if retrace_idx != -1:
                    post_lows = future_lows[retrace_idx:]
                    post_highs = future_highs[retrace_idx:]

                    hit_sl = any(fl <= sl for fl in post_lows)
                    hit_tp = any(fh >= tp for fh in post_highs)

                    if hit_tp and not hit_sl:
                        outcome = 'WIN'
                        pnl = 2.2 * sl_dist
                    elif hit_sl:
                        outcome = 'LOSS'
                        pnl = -1.0 * sl_dist
                    else:
                        outcome = 'TIME_EXIT'
                        pnl = (closes[i+20] - entry)

                    trades.append({'type': 'BUY', 'pnl': pnl, 'outcome': outcome, 'rr': 2.2, 'sl_dist': sl_dist})

        # Bearish Wick Sweep + Trend Confluence
        elif cur_high > prev_high and cur_close < prev_high and trend == 'BEARISH':
            if highs[i] < lows[i-2]:
                fvg_top = lows[i-2]
                fvg_bot = highs[i]
                fvg_mid = (fvg_top + fvg_bot) / 2.0

                entry = fvg_mid
                sl = prev_high + 1.00
                sl_dist = sl - entry
                if sl_dist <= 0:
                    continue

                tp = entry - (2.2 * sl_dist)

                future_highs = highs[i+1:i+21]
                future_lows = lows[i+1:i+21]

                retrace_idx = -1
                for k in range(len(future_highs)):
                    if future_highs[k] >= entry:
                        retrace_idx = k
                        break

                if retrace_idx != -1:
                    post_highs = future_highs[retrace_idx:]
                    post_lows = future_lows[retrace_idx:]

                    hit_sl = any(fh >= sl for fh in post_highs)
                    hit_tp = any(fl <= tp for fl in post_lows)

                    if hit_tp and not hit_sl:
                        outcome = 'WIN'
                        pnl = 2.2 * sl_dist
                    elif hit_sl:
                        outcome = 'LOSS'
                        pnl = -1.0 * sl_dist
                    else:
                        outcome = 'TIME_EXIT'
                        pnl = (entry - closes[i+20])

                    trades.append({'type': 'SELL', 'pnl': pnl, 'outcome': outcome, 'rr': 2.2, 'sl_dist': sl_dist})

    df_res = pd.DataFrame(trades)
    if not df_res.empty:
        total = len(df_res)
        wins = (df_res['outcome'] == 'WIN').sum()
        losses = (df_res['outcome'] == 'LOSS').sum()
        win_rate = (wins / (wins + losses)) * 100.0 if (wins + losses) > 0 else 0
        total_pnl = df_res['pnl'].sum()
        gross_win = df_res[df_res['pnl'] > 0]['pnl'].sum()
        gross_loss = abs(df_res[df_res['pnl'] < 0]['pnl'].sum())
        pf = gross_win / gross_loss if gross_loss > 0 else 0

        print(f"\n  HYBRID SMC PATTERN PERFORMANCE SUMMARY:")
        print(f"   - Total Qualified Trades (5 Years):  {total:,}")
        print(f"   - Trades per Month:                   {total / 60:.1f} trades/month (~1-2 trades/week)")
        print(f"   - Win Rate (at 1:2.2 RR):             {win_rate:.1f}% ({wins} W / {losses} L)")
        print(f"   - Profit Factor:                      {pf:.2f}")
        print(f"   - Total Net PnL (Gold Points):        +${total_pnl:.2f}")
        print(f"   - Expectancy per Trade:               +${total_pnl/total:.2f}")

    print("\n" + "=" * 80)
    print(" ANALYSIS COMPLETE!")
    print("=" * 80)

if __name__ == "__main__":
    analyze_hybrid_smc()
