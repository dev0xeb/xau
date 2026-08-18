"""
Empirical Benchmark Engine: Model 2 (M5 Scalp Hybrid) + VWAP 4-Hypothesis Testing.

Tests:
1. Baseline Model 2 (Pure)
2. Hypothesis 1: VWAP Discount Filter (Entry <= Daily VWAP + 1.0 StdDev for BUY)
3. Hypothesis 2: VWAP Slope Acceleration Filter (VWAP_t > VWAP_t-5 for BUY)
4. Hypothesis 3: VWAP Reclaim Gate (M5 confirmation candle closes across Daily VWAP)
5. Hypothesis 4: Master Combined VWAP + Model 2 Engine

Evaluated across 5 Years of XAU/USD 5-Minute Data (2021 - 2026 / 396,689 bars).
"""

import sys
from pathlib import Path
from datetime import datetime, date
import pandas as pd
import numpy as np
import time

def run_vwap_model2_hypotheses_benchmark():
    proc_5m_path = Path("data/processed/xau_5m_5y.parquet")
    if not proc_5m_path.exists():
        print("[ERROR] 5m dataset missing!")
        return

    print("================================================================================")
    print("  MODEL 2 + VWAP 4-HYPOTHESIS EMPIRICAL BENCHMARK (5-YEAR XAU/USD)")
    print("================================================================================")

    start_time = time.time()

    print("[1/4] Loading 5-Year XAU/USD 5-Minute Parquet Data...")
    df_5m = pd.read_parquet(proc_5m_path)
    df_5m['timestamp'] = pd.to_datetime(df_5m['timestamp'])

    df_5m = df_5m.sort_values('timestamp').reset_index(drop=True)
    df_5m['hour'] = df_5m['timestamp'].dt.hour
    df_5m['minute'] = df_5m['timestamp'].dt.minute
    df_5m['date'] = df_5m['timestamp'].dt.date

    n = len(df_5m)
    print(f" -> Total Loaded Candles: {n:,} 5-minute bars across 5 Years.")

    closes_5m = df_5m['close'].values
    opens_5m = df_5m['open'].values
    highs_5m = df_5m['high'].values
    lows_5m = df_5m['low'].values
    volumes_5m = df_5m['volume'].values
    hours_5m = df_5m['hour'].values
    minutes_5m = df_5m['minute'].values
    dates_5m = df_5m['date'].values
    timestamps = df_5m['timestamp'].values

    # Pre-compute H1 Macro Trend
    print("[2/4] Computing H1 Macro Trend & M5 EMAs...")
    df_h1 = df_5m.resample('1h', on='timestamp').agg({
        'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last'
    }).dropna().reset_index()

    df_h1['ema21'] = df_h1['close'].ewm(span=21, adjust=False).mean()
    df_h1['ema50'] = df_h1['close'].ewm(span=50, adjust=False).mean()

    df_5m['h1_time'] = df_5m['timestamp'].dt.floor('1h')
    df_5m = pd.merge_asof(
        df_5m,
        df_h1[['timestamp', 'ema21', 'ema50', 'close']].rename(columns={
            'timestamp': 'h1_time', 'ema21': 'h1_ema21', 'ema50': 'h1_ema50', 'close': 'h1_close'
        }),
        on='h1_time', direction='backward'
    )

    h1_closes = df_5m['h1_close'].values
    h1_ema21s = df_5m['h1_ema21'].values
    h1_ema50s = df_5m['h1_ema50'].values

    df_5m['m5_ema21'] = df_5m['close'].ewm(span=21, adjust=False).mean()
    m5_ema21s = df_5m['m5_ema21'].values

    # 3. Compute Daily Anchored VWAP & Standard Deviation Bands
    print("[3/4] Pre-calculating Daily Rolling VWAP & Standard Deviation Bands...")
    typical_prices = (highs_5m + lows_5m + closes_5m) / 3.0
    tp_vol = typical_prices * volumes_5m

    df_5m['tp_vol'] = tp_vol
    df_5m['cum_tp_vol'] = df_5m.groupby('date')['tp_vol'].cumsum()
    df_5m['cum_vol'] = df_5m.groupby('date')['volume'].cumsum()

    # Avoid div zero
    cum_vol_vals = df_5m['cum_vol'].values
    cum_vol_vals[cum_vol_vals == 0] = 1.0

    vwap_vals = df_5m['cum_tp_vol'].values / cum_vol_vals
    df_5m['vwap'] = vwap_vals

    # Compute VWAP Variance/StdDev per day
    df_5m['sq_diff'] = ((typical_prices - vwap_vals) ** 2) * volumes_5m
    df_5m['cum_sq_diff'] = df_5m.groupby('date')['sq_diff'].cumsum()
    vwap_std_vals = np.sqrt(df_5m['cum_sq_diff'].values / cum_vol_vals)
    df_5m['vwap_std'] = vwap_std_vals

    vwap_slopes = np.zeros(n)
    vwap_slopes[5:] = vwap_vals[5:] - vwap_vals[:-5]

    pip_size = 0.10
    spread = 0.15

    # Core Simulation Engine
    def run_vwap_simulation(mode="baseline"):
        trades = []
        last_trade_bar = -10

        for i in range(50, n - 100):
            hour = hours_5m[i]
            d = dates_5m[i]

            if not (6 <= hour < 20):
                continue

            if i <= last_trade_bar + 1:
                continue

            idx = i - 1  # iloc[-2] closed candle

            # H1 Macro Trend Filter
            h1_c = h1_closes[idx]
            h1_e21 = h1_ema21s[idx]
            h1_e50 = h1_ema50s[idx]

            h1_bullish = (h1_c > h1_e21) and (h1_e21 > h1_e50)
            h1_bearish = (h1_c < h1_e21) and (h1_e21 < h1_e50)

            if not (h1_bullish or h1_bearish):
                continue

            # M5 Model 2 Core Setup Evaluation
            low_t = lows_5m[idx]
            high_t = highs_5m[idx]
            low_t2 = lows_5m[idx - 2]
            high_t2 = highs_5m[idx - 2]

            bull_fvg_pips = (low_t - high_t2) / pip_size
            bear_fvg_pips = (low_t2 - high_t) / pip_size

            is_bull_fvg = bull_fvg_pips >= 1.5
            is_bear_fvg = bear_fvg_pips >= 1.5

            prior_5_low = np.min(lows_5m[idx-5 : idx])
            prior_5_high = np.max(highs_5m[idx-5 : idx])
            m5_e21 = m5_ema21s[idx]

            bull_sweep = prior_5_low <= m5_e21
            bear_sweep = prior_5_high >= m5_e21

            m5_close = closes_5m[idx]
            m5_open = opens_5m[idx]
            bull_confirm = m5_close > m5_e21
            bear_confirm = m5_close < m5_e21

            base_buy = h1_bullish and is_bull_fvg and bull_sweep and bull_confirm
            base_sell = h1_bearish and is_bear_fvg and bear_sweep and bear_confirm

            if not (base_buy or base_sell):
                continue

            # VWAP Indicators at trigger bar
            c_vwap = vwap_vals[idx]
            c_vwap_std = vwap_std_vals[idx]
            c_vwap_slope = vwap_slopes[idx]

            buy_signal = base_buy
            sell_signal = base_sell

            # Mode 1: H1 (Discount Filter - No buying above VWAP + 1.0 std)
            if mode == "hyp1_discount":
                if base_buy and (m5_close > c_vwap + 1.0 * c_vwap_std):
                    buy_signal = False
                if base_sell and (m5_close < c_vwap - 1.0 * c_vwap_std):
                    sell_signal = False

            # Mode 2: H2 (Slope Acceleration Filter - VWAP slope positive for BUY)
            elif mode == "hyp2_slope":
                if base_buy and (c_vwap_slope <= 0):
                    buy_signal = False
                if base_sell and (c_vwap_slope >= 0):
                    sell_signal = False

            # Mode 3: H3 (VWAP Reclaim Gate - candle open below VWAP, close above VWAP)
            elif mode == "hyp3_reclaim":
                if base_buy and not (m5_open < c_vwap and m5_close > c_vwap):
                    buy_signal = False
                if base_sell and not (m5_open > c_vwap and m5_close < c_vwap):
                    sell_signal = False

            # Mode 4: H4 (Master Combined Engine)
            elif mode == "hyp4_master":
                # Discount filter + Slope filter
                if base_buy and ((m5_close > c_vwap + 1.0 * c_vwap_std) or (c_vwap_slope <= 0)):
                    buy_signal = False
                if base_sell and ((m5_close < c_vwap - 1.0 * c_vwap_std) or (c_vwap_slope >= 0)):
                    sell_signal = False

            if not (buy_signal or sell_signal):
                continue

            # Risk & Target Matrix
            recent_3_low = np.min(lows_5m[idx-2 : idx+1])
            recent_3_high = np.max(highs_5m[idx-2 : idx+1])

            if buy_signal:
                direction = "BUY"
                entry_price = high_t2 + spread
                sl_price = recent_3_low - 0.50
                sl_pips = np.clip((entry_price - sl_price) / pip_size, 15.0, 80.0)
                sl_price = entry_price - (sl_pips * pip_size)

                tp1_price = entry_price + (sl_pips * pip_size * 1.0)
                tp2_price = entry_price + (sl_pips * pip_size * 2.0)
                tp3_price = entry_price + (sl_pips * pip_size * 3.0)

            else:
                direction = "SELL"
                entry_price = low_t2
                sl_price = recent_3_high + 0.50
                sl_pips = np.clip((sl_price - entry_price) / pip_size, 15.0, 80.0)
                sl_price = entry_price + (sl_pips * pip_size)

                tp1_price = entry_price - (sl_pips * pip_size * 1.0)
                tp2_price = entry_price - (sl_pips * pip_size * 2.0)
                tp3_price = entry_price - (sl_pips * pip_size * 3.0)

            t1_hit, t2_hit, t3_hit = False, False, False
            sl_hit = False
            exit_bar = i + 36

            risk_per_ticket = 33.33
            t1_pnl, t2_pnl, t3_pnl = -33.33, -33.33, -33.33

            for k in range(i, min(i + 36, n)):
                bar_h = highs_5m[k]
                bar_l = lows_5m[k]

                if direction == "BUY":
                    if bar_l <= sl_price:
                        sl_hit = True
                        exit_bar = k
                        break
                    if not t1_hit and bar_h >= tp1_price:
                        t1_hit = True
                        t1_pnl = risk_per_ticket * 1.0
                    if t1_hit and not t2_hit and bar_h >= tp2_price:
                        t2_hit = True
                        t2_pnl = risk_per_ticket * 2.0
                    if t2_hit and not t3_hit and bar_h >= tp3_price:
                        t3_hit = True
                        t3_pnl = risk_per_ticket * 3.0
                        exit_bar = k
                        break
                else:  # SELL
                    if bar_h >= sl_price:
                        sl_hit = True
                        exit_bar = k
                        break
                    if not t1_hit and bar_l <= tp1_price:
                        t1_hit = True
                        t1_pnl = risk_per_ticket * 1.0
                    if t1_hit and not t2_hit and bar_l <= tp2_price:
                        t2_hit = True
                        t2_pnl = risk_per_ticket * 2.0
                    if t2_hit and not t3_hit and bar_l <= tp3_price:
                        t3_hit = True
                        t3_pnl = risk_per_ticket * 3.0
                        exit_bar = k
                        break

            setup_pnl = t1_pnl + t2_pnl + t3_pnl
            trades.append({
                'timestamp': timestamps[i],
                'direction': direction,
                'entry_price': entry_price,
                'sl_pips': sl_pips,
                'pnl': setup_pnl,
                'is_win': setup_pnl > 0
            })

            last_trade_bar = exit_bar

        return pd.DataFrame(trades)

    print("[4/4] Executing 5 Empirical Backtest Simulations...")

    df_base = run_vwap_simulation("baseline")
    df_h1_disc = run_vwap_simulation("hyp1_discount")
    df_h2_slope = run_vwap_simulation("hyp2_slope")
    df_h3_reclaim = run_vwap_simulation("hyp3_reclaim")
    df_h4_master = run_vwap_simulation("hyp4_master")

    def print_hyp_metrics(df, label):
        if len(df) == 0:
            print(f"\n[{label}] No trades.")
            return

        tot = len(df)
        wins = df[df['is_win']]
        losses = df[~df['is_win']]
        wr = (len(wins) / tot) * 100.0

        gp = wins['pnl'].sum()
        gl = abs(losses['pnl'].sum())
        net = df['pnl'].sum()
        pf = (gp / gl) if gl > 0 else np.nan

        eq = 10000.0 + df['pnl'].cumsum()
        pk = eq.cummax()
        dd = ((eq - pk) / pk * 100.0).min()

        df['week'] = pd.to_datetime(df['timestamp']).dt.to_period('W')
        wpnl = df.groupby('week')['pnl'].sum()
        prof_w = (wpnl > 0).sum()
        tot_w = len(wpnl)
        wcons = (prof_w / tot_w * 100.0) if tot_w > 0 else 0.0

        print(f"\n================================================================================")
        print(f" PERFORMANCE METRICS: {label}")
        print(f"================================================================================")
        print(f" -> Total Trades Executed:   {tot:,} trades (~{(tot/(tot_w*5)):.1f} trades / day)")
        print(f" -> Win Rate (%):            {wr:.2f}% ({len(wins):,} W / {len(losses):,} L)")
        print(f" -> Net Cumulative Profit:   +${net:,.2f} ({(net/10000.0)*100.0:.2f}% Return)")
        print(f" -> Profit Factor (PF):      {pf:.2f}")
        print(f" -> Maximum Drawdown (%):    {dd:.2f}%")
        print(f" -> Weekly Consistency Rate: {wcons:.2f}% ({prof_w}/{tot_w} Weeks Profitable)")
        print(f"--------------------------------------------------------------------------------")

    print_hyp_metrics(df_base, "0. BASELINE MODEL 2 (Pure)")
    print_hyp_metrics(df_h1_disc, "1. HYPOTHESIS 1: VWAP Discount/Premium Gate")
    print_hyp_metrics(df_h2_slope, "2. HYPOTHESIS 2: VWAP Slope Acceleration Gate")
    print_hyp_metrics(df_h3_reclaim, "3. HYPOTHESIS 3: VWAP Reclaim High-Conviction Gate")
    print_hyp_metrics(df_h4_master, "4. HYPOTHESIS 4: Master VWAP + Model 2 Confluence")

    elapsed = time.time() - start_time
    print(f"\n[DONE] 5-Hypothesis VWAP benchmark completed in {elapsed:.2f} seconds.")

if __name__ == "__main__":
    run_vwap_model2_hypotheses_benchmark()
