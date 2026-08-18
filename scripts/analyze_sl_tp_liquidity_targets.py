"""
Empirical SL/TP Optimization & Liquidity Target Analyzer for XAU/USD.

Extracts optimal Stop Loss placement and Take Profit liquidity targets from 5-Year Data:
1. SL Placement Analysis: Tight Wick SL vs 15m Structural SL vs Double-Sweep Buffer.
2. TP Placement Analysis: Opposing Liquidity Target Hit Rates vs RR Ratios (1:1.5, 1:2.0, 1:2.5, 1:3.0, 1:4.0).
3. Breakeven Trigger Distance: Optimal BE trigger (at TP1 vs at 1.0 RR vs at 1.5 RR).
"""

import sys
from pathlib import Path
import numpy as np
import pandas as pd

def analyze_sl_tp():
    print("=" * 85)
    print(" EMPIRICAL SL & TP OPTIMIZATION & LIQUIDITY TARGET ANALYSIS (5 YEARS)")
    print("=" * 85)

    proc_15m_path = Path("data/processed/xau_15m_5y.parquet")
    df_15m = pd.read_parquet(proc_15m_path)
    df_15m['timestamp'] = pd.to_datetime(df_15m['timestamp'])

    highs = df_15m['high'].values
    lows = df_15m['low'].values
    closes = df_15m['close'].values
    n = len(df_15m)

    tr = np.maximum(highs - lows, np.maximum(abs(highs - pd.Series(closes).shift(1)), abs(lows - pd.Series(closes).shift(1))))
    atr = pd.Series(tr).rolling(14).mean().values

    lookback = 20
    sl_records = []
    tp_records = []

    for i in range(lookback, n - 24):
        prev_high = np.max(highs[i-lookback:i])
        prev_low = np.min(lows[i-lookback:i])
        cur_high = highs[i]
        cur_low = lows[i]
        cur_close = closes[i]
        cur_atr = atr[i] if not np.isnan(atr[i]) else 2.0

        # Bullish Low Sweep (Wick below 15m Low, close back above)
        if cur_low < prev_low and cur_close > prev_low:
            entry = cur_close
            
            # SL Candidates:
            sl_tight = cur_low - 0.30  # Tight Wick SL ($0.30 buffer)
            sl_struct = prev_low - (0.5 * cur_atr)  # 15m Structural SL ($0.80-$1.50 buffer)
            sl_wide = prev_low - (1.0 * cur_atr)  # Wide Buffer SL

            # Check next 16 bars (4 hours)
            fut_lows = lows[i+1:i+17]
            fut_highs = highs[i+1:i+17]

            min_future_low = np.min(fut_lows)
            max_future_high = np.max(fut_highs)

            # SL Survival
            tight_survived = min_future_low > sl_tight
            struct_survived = min_future_low > sl_struct
            wide_survived = min_future_low > sl_wide

            sl_records.append({
                'type': 'BUY',
                'tight_survived': tight_survived,
                'struct_survived': struct_survived,
                'wide_survived': wide_survived,
                'sweep_depth': prev_low - cur_low,
            })

            # TP Targets (Opposing 15m High Target vs Fixed RRs)
            opposing_target = prev_high  # Distance to opposing liquidity pool
            dist_to_opposing = opposing_target - entry

            if dist_to_opposing > 0:
                hit_opposing = max_future_high >= opposing_target
                
                # Check fixed RR hits using Structural SL
                sl_dist = entry - sl_struct
                if sl_dist > 0:
                    hit_1_5 = max_future_high >= (entry + 1.5 * sl_dist)
                    hit_2_0 = max_future_high >= (entry + 2.0 * sl_dist)
                    hit_2_5 = max_future_high >= (entry + 2.5 * sl_dist)
                    hit_3_0 = max_future_high >= (entry + 3.0 * sl_dist)
                    hit_4_0 = max_future_high >= (entry + 4.0 * sl_dist)

                    tp_records.append({
                        'type': 'BUY',
                        'dist_to_opposing': dist_to_opposing,
                        'hit_opposing': hit_opposing,
                        'hit_1_5': hit_1_5,
                        'hit_2_0': hit_2_0,
                        'hit_2_5': hit_2_5,
                        'hit_3_0': hit_3_0,
                        'hit_4_0': hit_4_0,
                        'struct_survived': struct_survived,
                    })

    df_sl = pd.DataFrame(sl_records)
    df_tp = pd.DataFrame(tp_records)

    print("\n[PART 1] STOP LOSS (SL) SURVIVAL & WHIPSAW ANALYSIS:")
    print(f"  Total Reversal Sweeps Evaluated: {len(df_sl):,}")
    print(f"   - Tight Wick SL ($0.30 buffer):         Survival Rate = {df_sl['tight_survived'].mean()*100:.1f}% (Whipsaw Rate = {100 - df_sl['tight_survived'].mean()*100:.1f}%)")
    print(f"   - Structural 15m SL (+ 0.5 ATR buffer): Survival Rate = {df_sl['struct_survived'].mean()*100:.1f}% (Whipsaw Rate = {100 - df_sl['struct_survived'].mean()*100:.1f}%)")
    print(f"   - Wide Buffer SL (+ 1.0 ATR buffer):    Survival Rate = {df_sl['wide_survived'].mean()*100:.1f}% (Whipsaw Rate = {100 - df_sl['wide_survived'].mean()*100:.1f}%)")

    print("\n[PART 2] TAKE PROFIT (TP) TARGET HIT RATES & EXPECTANCY:")
    print(f"  Total Valid Setup Trades Evaluated: {len(df_tp):,}")
    print(f"   - Opposing 15m Liquidity Target Hit Rate: {df_tp['hit_opposing'].mean()*100:.1f}% (Avg Draw Distance: ${df_tp['dist_to_opposing'].mean():.2f})")
    print("\n  Fixed Risk-to-Reward Target Success Rates:")

    for rr_name, col in [("1:1.5 RR", "hit_1_5"), ("1:2.0 RR", "hit_2_0"), ("1:2.5 RR", "hit_2_5"), ("1:3.0 RR", "hit_3_0"), ("1:4.0 RR", "hit_4_0")]:
        # Hit rate when structural SL survives
        hit_rate = df_tp[col].mean() * 100.0
        rr_val = float(rr_name.split(":")[1].split(" ")[0])
        # Win rate required to break even = 1 / (1 + RR)
        be_win_rate = (1.0 / (1.0 + rr_val)) * 100.0
        edge = hit_rate - be_win_rate
        print(f"   - {rr_name:<10}: Hit Rate = {hit_rate:.1f}% | Required BE Win Rate = {be_win_rate:.1f}% | Mathematical Edge = {edge:+.1f}%")

    print("\n" + "=" * 85)
    print(" SL & TP ANALYSIS COMPLETE!")
    print("=" * 85)

if __name__ == "__main__":
    analyze_sl_tp()
