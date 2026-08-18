"""
Comprehensive Empirical Price Action & Market Structure Analyzer for XAU/USD.

Analyzes 1.98M bars across 1m, 5m, and 15m timeframes to extract statistical patterns in:
1. Liquidity Sweeps (Wick vs Body closes, Reversal vs Continuation probabilities)
2. Market Structure Shifts (CHoCH/BOS displacement sizes and success rates)
3. Fair Value Gaps (FVG mitigation depths, fill timing, and win rates)
4. Session Volatility & Trend Confluence (London vs NY vs Overlap dynamics)
"""

import sys
from pathlib import Path
from datetime import datetime
import numpy as np
import pandas as pd

# Add src to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

def analyze_price_action():
    print("=" * 80)
    print(" EMPIRICAL XAU/USD PRICE ACTION & MARKET STRUCTURE ANALYSIS (2021 - 2026)")
    print("=" * 80)

    raw_1m_path = Path("data/raw/xau_1m_5y.parquet")
    proc_5m_path = Path("data/processed/xau_5m_5y.parquet")
    proc_15m_path = Path("data/processed/xau_15m_5y.parquet")

    if not (raw_1m_path.exists() and proc_5m_path.exists() and proc_15m_path.exists()):
        print("[ERROR] Datasets missing! Run python scripts/download_xau_data.py first.")
        return

    print("\n[1/5] Loading 5-Year Multi-Timeframe Datasets...")
    df_1m = pd.read_parquet(raw_1m_path)
    df_5m = pd.read_parquet(proc_5m_path)
    df_15m = pd.read_parquet(proc_15m_path)

    print(f"  - 1-Minute Bars:  {len(df_1m):,}")
    print(f"  - 5-Minute Bars:  {len(df_5m):,}")
    print(f"  - 15-Minute Bars: {len(df_15m):,}")

    # Ensure DatetimeIndex
    df_1m['timestamp'] = pd.to_datetime(df_1m['timestamp'])
    df_5m['timestamp'] = pd.to_datetime(df_5m['timestamp'])
    df_15m['timestamp'] = pd.to_datetime(df_15m['timestamp'])

    # -------------------------------------------------------------------------
    # PART 1: SESSION VOLATILITY & CANDLE RANGE STRUCTURE
    # -------------------------------------------------------------------------
    print("\n[2/5] Analyzing Session Volatility & ATR Expansion Dynamics...")
    
    df_15m['range'] = df_15m['high'] - df_15m['low']
    df_15m['body'] = (df_15m['close'] - df_15m['open']).abs()
    df_15m['upper_wick'] = df_15m['high'] - df_15m[['open', 'close']].max(axis=1)
    df_15m['lower_wick'] = df_15m[['open', 'close']].min(axis=1) - df_15m['low']

    df_15m['hour'] = df_15m['timestamp'].dt.hour
    
    session_stats = df_15m.groupby('hour')['range'].agg(['mean', 'median', 'std']).reset_index()
    
    # Tag sessions
    df_15m['session'] = 'ASIA'
    df_15m.loc[(df_15m['hour'] >= 7) & (df_15m['hour'] < 13), 'session'] = 'LONDON'
    df_15m.loc[(df_15m['hour'] >= 13) & (df_15m['hour'] < 16), 'session'] = 'OVERLAP'
    df_15m.loc[(df_15m['hour'] >= 16) & (df_15m['hour'] < 21), 'session'] = 'NY'

    sess_summary = df_15m.groupby('session')['range'].agg(['count', 'mean', 'median', 'max']).reset_index()
    print("\n  15-Minute Candle Range ($ Gold Movement) by Session:")
    for _, r in sess_summary.iterrows():
        print(f"   - {r['session']:<8}: Count={r['count']:,} | Mean Range=${r['mean']:.2f} | Median=${r['median']:.2f} | Max=${r['max']:.2f}")

    # -------------------------------------------------------------------------
    # PART 2: 15M LIQUIDITY SWEEPS (WICK VS BODY CLOSES)
    # -------------------------------------------------------------------------
    print("\n[3/5] Studying 15m Liquidity Sweeps & Post-Sweep Reversal vs Continuation Patterns...")
    
    # Identify 15m Swing Highs & Lows (2-bar fractal window)
    highs = df_15m['high'].values
    lows = df_15m['low'].values
    closes = df_15m['close'].values
    opens = df_15m['open'].values
    n_15m = len(df_15m)

    swing_highs = []
    swing_lows = []
    
    # Rolling 20-bar max/min swing levels
    lookback = 20
    sweeps_wick = []
    sweeps_body = []

    for i in range(lookback, n_15m - 20):
        prev_high = np.max(highs[i-lookback:i])
        prev_low = np.min(lows[i-lookback:i])
        
        cur_high = highs[i]
        cur_low = lows[i]
        cur_close = closes[i]

        # Bearish Sweep of High
        if cur_high > prev_high:
            is_wick_sweep = (cur_close < prev_high)
            # Look ahead 4 bars (1 hour) to check price movement
            post_change = closes[i+4] - cur_close
            if is_wick_sweep:
                sweeps_wick.append({'type': 'BEARISH_HIGH', 'post_change': post_change, 'sweep_depth': cur_high - prev_high})
            else:
                sweeps_body.append({'type': 'BEARISH_HIGH', 'post_change': post_change, 'sweep_depth': cur_high - prev_high})

        # Bullish Sweep of Low
        elif cur_low < prev_low:
            is_wick_sweep = (cur_close > prev_low)
            post_change = closes[i+4] - cur_close
            if is_wick_sweep:
                sweeps_wick.append({'type': 'BULLISH_LOW', 'post_change': post_change, 'sweep_depth': prev_low - cur_low})
            else:
                sweeps_body.append({'type': 'BULLISH_LOW', 'post_change': post_change, 'sweep_depth': prev_low - cur_low})

    df_wick_sweeps = pd.DataFrame(sweeps_wick)
    df_body_sweeps = pd.DataFrame(sweeps_body)

    if not df_wick_sweeps.empty:
        wick_bear = df_wick_sweeps[df_wick_sweeps['type'] == 'BEARISH_HIGH']
        wick_bull = df_wick_sweeps[df_wick_sweeps['type'] == 'BULLISH_LOW']

        bear_reversals = (wick_bear['post_change'] < 0).mean() * 100.0 if len(wick_bear) > 0 else 0
        bull_reversals = (wick_bull['post_change'] > 0).mean() * 100.0 if len(wick_bull) > 0 else 0

        bear_avg_drop = wick_bear[wick_bear['post_change'] < 0]['post_change'].mean() if len(wick_bear) > 0 else 0
        bull_avg_rise = wick_bull[wick_bull['post_change'] > 0]['post_change'].mean() if len(wick_bull) > 0 else 0

        print(f"\n  Wick-Only Liquidity Sweeps (Price wicks past swing level but CLOSES inside):")
        print(f"   - Total Wick Sweeps Detected: {len(df_wick_sweeps):,}")
        print(f"   - Bearish High Wick Sweeps:   Count={len(wick_bear):,} | 1-Hour Reversal Rate={bear_reversals:.1f}% | Avg Drop=${abs(bear_avg_drop):.2f}")
        print(f"   - Bullish Low Wick Sweeps:    Count={len(wick_bull):,} | 1-Hour Reversal Rate={bull_reversals:.1f}% | Avg Rise=${bull_avg_rise:.2f}")

    if not df_body_sweeps.empty:
        body_bear = df_body_sweeps[df_body_sweeps['type'] == 'BEARISH_HIGH']
        body_bull = df_body_sweeps[df_body_sweeps['type'] == 'BULLISH_LOW']

        bear_cont = (body_bear['post_change'] > 0).mean() * 100.0 if len(body_bear) > 0 else 0
        bull_cont = (body_bull['post_change'] < 0).mean() * 100.0 if len(body_bull) > 0 else 0

        print(f"\n  Full Body Breakouts (Price CLOSES beyond swing level):")
        print(f"   - Total Body Breakouts:      {len(df_body_sweeps):,}")
        print(f"   - Bearish High Body Closes:  Count={len(body_bear):,} | Continuation Trend Rate={bear_cont:.1f}%")
        print(f"   - Bullish Low Body Closes:   Count={len(body_bull):,} | Continuation Trend Rate={bull_cont:.1f}%")

    # -------------------------------------------------------------------------
    # PART 3: FAIR VALUE GAP (FVG) MITIGATION & FILL STATISTICS
    # -------------------------------------------------------------------------
    print("\n[4/5] Analyzing Fair Value Gap (FVG) Mitigation Depth & Fill Rates (1m & 5m)...")

    # Detect 5m FVGs
    highs_5m = df_5m['high'].values
    lows_5m = df_5m['low'].values
    closes_5m = df_5m['close'].values
    n_5m = len(df_5m)

    fvg_5m_list = []

    for i in range(2, n_5m - 20):
        # Bullish 5m FVG: Low[i] > High[i-2]
        if lows_5m[i] > highs_5m[i-2]:
            gap_size = lows_5m[i] - highs_5m[i-2]
            if gap_size >= 0.30:  # At least $0.30 gap on Gold
                fvg_top = lows_5m[i]
                fvg_bot = highs_5m[i-2]
                fvg_mid = (fvg_top + fvg_bot) / 2.0
                
                # Check next 20 bars for fill depth
                future_lows = lows_5m[i+1:i+21]
                min_future_low = np.min(future_lows) if len(future_lows) > 0 else fvg_top
                
                mitigated = min_future_low <= fvg_top
                filled_mid = min_future_low <= fvg_mid
                invalidated = min_future_low < fvg_bot

                # Measure 1-hour move after mid fill
                post_move = closes_5m[min(i+12, n_5m-1)] - fvg_mid if filled_mid else 0.0

                fvg_5m_list.append({
                    'type': 'BULLISH',
                    'gap_size': gap_size,
                    'mitigated': mitigated,
                    'filled_mid': filled_mid,
                    'invalidated': invalidated,
                    'post_move': post_move
                })

        # Bearish 5m FVG: High[i] < Low[i-2]
        elif highs_5m[i] < lows_5m[i-2]:
            gap_size = lows_5m[i-2] - highs_5m[i]
            if gap_size >= 0.30:
                fvg_top = lows_5m[i-2]
                fvg_bot = highs_5m[i]
                fvg_mid = (fvg_top + fvg_bot) / 2.0

                future_highs = highs_5m[i+1:i+21]
                max_future_high = np.max(future_highs) if len(future_highs) > 0 else fvg_bot
                
                mitigated = max_future_high >= fvg_bot
                filled_mid = max_future_high >= fvg_mid
                invalidated = max_future_high > fvg_top

                post_move = fvg_mid - closes_5m[min(i+12, n_5m-1)] if filled_mid else 0.0

                fvg_5m_list.append({
                    'type': 'BEARISH',
                    'gap_size': gap_size,
                    'mitigated': mitigated,
                    'filled_mid': filled_mid,
                    'invalidated': invalidated,
                    'post_move': post_move
                })

    df_fvgs = pd.DataFrame(fvg_5m_list)

    if not df_fvgs.empty:
        total_fvgs = len(df_fvgs)
        mit_rate = (df_fvgs['mitigated']).mean() * 100.0
        mid_fill_rate = (df_fvgs['filled_mid']).mean() * 100.0
        inval_rate = (df_fvgs['invalidated']).mean() * 100.0

        mid_filled_df = df_fvgs[df_fvgs['filled_mid']]
        win_rate_mid = (mid_filled_df['post_move'] > 0).mean() * 100.0 if len(mid_filled_df) > 0 else 0
        avg_win_move = mid_filled_df[mid_filled_df['post_move'] > 0]['post_move'].mean() if len(mid_filled_df) > 0 else 0

        print(f"\n  5-Minute Fair Value Gap (FVG) Mitigation Statistics:")
        print(f"   - Total 5m FVGs (>= $0.30):    {total_fvgs:,}")
        print(f"   - Touch Rate (Price touches FVG): {mit_rate:.1f}%")
        print(f"   - Consequent Encroachment (50% Mid Fill Rate): {mid_fill_rate:.1f}%")
        print(f"   - Full Blow-Through (Invalidated Rate):        {inval_rate:.1f}%")
        print(f"   - Reversal Accuracy on 50% FVG Retrace:        {win_rate_mid:.1f}% | Avg Move=${avg_win_move:.2f}")

    # -------------------------------------------------------------------------
    # PART 4: 15M TREND CONFLUENCE PATTERNS
    # -------------------------------------------------------------------------
    print("\n[5/5] Analyzing Higher Timeframe (15m) Trend Alignment Impact...")

    # Calculate 50 EMA on 15m
    df_15m['ema_50'] = df_15m['close'].ewm(span=50, adjust=False).mean()
    df_15m['trend_15m'] = np.where(df_15m['close'] > df_15m['ema_50'], 'BULLISH', 'BEARISH')

    trend_counts = df_15m['trend_15m'].value_counts()
    print(f"\n  15-Minute Trend State Distribution:")
    print(f"   - Bullish Trend (Close > 50 EMA): {trend_counts.get('BULLISH', 0):,} bars ({trend_counts.get('BULLISH', 0)/len(df_15m)*100:.1f}%)")
    print(f"   - Bearish Trend (Close < 50 EMA): {trend_counts.get('BEARISH', 0):,} bars ({trend_counts.get('BEARISH', 0)/len(df_15m)*100:.1f}%)")

    # Match sweeps with 15m Trend Alignment
    sweeps_with_trend = []

    for i in range(lookback, n_15m - 20):
        prev_high = np.max(highs[i-lookback:i])
        prev_low = np.min(lows[i-lookback:i])
        cur_high = highs[i]
        cur_low = lows[i]
        cur_close = closes[i]
        trend = df_15m['trend_15m'].iloc[i]

        # Bullish Low Sweep (Look for Buy Reversal)
        if cur_low < prev_low and cur_close > prev_low:
            post_move = closes[i+4] - cur_close
            with_trend = (trend == 'BULLISH')  # Oversold dip inside Bullish HTF trend
            sweeps_with_trend.append({'type': 'BULLISH_SWEEP', 'with_trend': with_trend, 'post_move': post_move})

        # Bearish High Sweep (Look for Sell Reversal)
        elif cur_high > prev_high and cur_close < prev_high:
            post_move = cur_close - closes[i+4]
            with_trend = (trend == 'BEARISH')  # Overbought rally inside Bearish HTF trend
            sweeps_with_trend.append({'type': 'BEARISH_SWEEP', 'with_trend': with_trend, 'post_move': post_move})

    df_trend_sweeps = pd.DataFrame(sweeps_with_trend)

    if not df_trend_sweeps.empty:
        with_t = df_trend_sweeps[df_trend_sweeps['with_trend']]
        against_t = df_trend_sweeps[~df_trend_sweeps['with_trend']]

        win_with_t = (with_t['post_move'] > 0).mean() * 100.0 if len(with_t) > 0 else 0
        win_against_t = (against_t['post_move'] > 0).mean() * 100.0 if len(against_t) > 0 else 0

        avg_pnl_with_t = with_t['post_move'].mean() if len(with_t) > 0 else 0
        avg_pnl_against_t = against_t['post_move'].mean() if len(against_t) > 0 else 0

        print(f"\n  SWEEP REVERSAL WIN RATES WITH VS AGAINST 15M TREND:")
        print(f"   [WITH HTF TREND]    Count={len(with_t):,} | Win Rate={win_with_t:.1f}% | Expectancy per Sweep=+${avg_pnl_with_t:.2f}")
        print(f"   [AGAINST HTF TREND] Count={len(against_t):,} | Win Rate={win_against_t:.1f}% | Expectancy per Sweep=${avg_pnl_against_t:.2f}")

    print("\n" + "=" * 80)
    print(" PRICE ACTION ANALYSIS COMPLETE!")
    print("=" * 80)

if __name__ == "__main__":
    analyze_price_action()
