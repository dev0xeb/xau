"""
Diagnostic & Frequency Optimization Engine: Hypothesis 3 (VWAP Reclaim Gate).

Analyzes:
1. Why original H3 trade frequency is low (544 trades / 5 years).
2. Diagnostic funnel of Baseline Model 2 setup positions relative to Daily VWAP.
3. Evaluates 5 variations of VWAP Reclaim to increase trade frequency:
   - Variant 3A: Strict Single-Bar Reclaim (m5_open < VWAP and m5_close > VWAP) [Original H3]
   - Variant 3B: 2-Bar Reclaim Window (Price crossed VWAP within the last 2 bars)
   - Variant 3C: VWAP Touch & Reclaim (m5_low <= VWAP + $0.20 and m5_close > VWAP)
   - Variant 3D: VWAP Sweep & Reclaim (m5_low <= VWAP - $0.30 and m5_close > VWAP)
   - Variant 3E: London/NY Session Anchored VWAP Reclaim
"""

import sys
from pathlib import Path
from datetime import datetime
import pandas as pd
import numpy as np
import time

def run_hyp3_frequency_diagnosis():
    proc_5m_path = Path("data/processed/xau_5m_5y.parquet")
    if not proc_5m_path.exists():
        print("[ERROR] 5m dataset missing!")
        return

    print("================================================================================")
    print("  HYPOTHESIS 3 (VWAP RECLAIM GATE) FREQUENCY DIAGNOSIS & EXPANSION BENCHMARK")
    print("================================================================================")

    start_time = time.time()

    print("[1/4] Loading 5-Year XAU/USD 5-Minute Data...")
    df_5m = pd.read_parquet(proc_5m_path)
    df_5m['timestamp'] = pd.to_datetime(df_5m['timestamp'])

    df_5m = df_5m.sort_values('timestamp').reset_index(drop=True)
    df_5m['hour'] = df_5m['timestamp'].dt.hour
    df_5m['date'] = df_5m['timestamp'].dt.date

    n = len(df_5m)

    closes_5m = df_5m['close'].values
    opens_5m = df_5m['open'].values
    highs_5m = df_5m['high'].values
    lows_5m = df_5m['low'].values
    volumes_5m = df_5m['volume'].values
    hours_5m = df_5m['hour'].values
    dates_5m = df_5m['date'].values
    timestamps = df_5m['timestamp'].values

    # H1 Macro Trend
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

    # Daily VWAP
    typical_prices = (highs_5m + lows_5m + closes_5m) / 3.0
    tp_vol = typical_prices * volumes_5m

    df_5m['tp_vol'] = tp_vol
    df_5m['cum_tp_vol'] = df_5m.groupby('date')['tp_vol'].cumsum()
    df_5m['cum_vol'] = df_5m.groupby('date')['volume'].cumsum()

    cum_vol_vals = df_5m['cum_vol'].values
    cum_vol_vals[cum_vol_vals == 0] = 1.0

    vwap_vals = df_5m['cum_tp_vol'].values / cum_vol_vals
    df_5m['daily_vwap'] = vwap_vals

    pip_size = 0.10
    spread = 0.15

    # 1. Collect all Baseline Model 2 Setups and evaluate VWAP position
    print("[2/4] Analyzing Baseline Model 2 Trade Positions relative to Daily VWAP...")

    baseline_setups = []
    last_trade_bar = -10

    for i in range(50, n - 100):
        hour = hours_5m[i]
        if not (6 <= hour < 20):
            continue

        if i <= last_trade_bar + 1:
            continue

        idx = i - 1  # closed candle

        h1_c = h1_closes[idx]
        h1_e21 = h1_ema21s[idx]
        h1_e50 = h1_ema50s[idx]

        h1_bullish = (h1_c > h1_e21) and (h1_e21 > h1_e50)
        h1_bearish = (h1_c < h1_e21) and (h1_e21 < h1_e50)

        if not (h1_bullish or h1_bearish):
            continue

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
        m5_high = highs_5m[idx]
        m5_low = lows_5m[idx]

        bull_confirm = m5_close > m5_e21
        bear_confirm = m5_close < m5_e21

        buy_signal = h1_bullish and is_bull_fvg and bull_sweep and bull_confirm
        sell_signal = h1_bearish and is_bear_fvg and bear_sweep and bear_confirm

        if not (buy_signal or sell_signal):
            continue

        c_vwap = vwap_vals[idx]
        c_vwap_prev = vwap_vals[idx - 1]

        # Prior bar OHLC
        m5_open_prev = opens_5m[idx - 1]
        m5_close_prev = closes_5m[idx - 1]
        m5_low_prev = lows_5m[idx - 1]
        m5_high_prev = highs_5m[idx - 1]

        direction = "BUY" if buy_signal else "SELL"

        # Categorize relative to VWAP
        is_entirely_above_vwap = (m5_low > c_vwap) if direction == "BUY" else (m5_high < c_vwap)
        is_entirely_below_vwap = (m5_high < c_vwap) if direction == "BUY" else (m5_low > c_vwap)
        
        # Strict 1-Bar Reclaim (3A)
        is_reclaim_3a = (m5_open < c_vwap and m5_close > c_vwap) if direction == "BUY" else (m5_open > c_vwap and m5_close < c_vwap)

        # 2-Bar Reclaim Window (3B): Was open/close below VWAP in prev bar or current open, and current close above?
        is_reclaim_3b = ((m5_close_prev < c_vwap_prev or m5_open < c_vwap) and m5_close > c_vwap) if direction == "BUY" else ((m5_close_prev > c_vwap_prev or m5_open > c_vwap) and m5_close < c_vwap)

        # Touch & Reclaim (3C): Low/High touched within $0.20 of VWAP and closed on right side
        is_reclaim_3c = (m5_low <= c_vwap + 0.20 and m5_close > c_vwap) if direction == "BUY" else (m5_high >= c_vwap - 0.20 and m5_close < c_vwap)

        # Sweep & Reclaim (3D): Low/High swept past VWAP by at least $0.15 and closed back over VWAP
        is_reclaim_3d = (m5_low <= c_vwap - 0.15 and m5_close > c_vwap) if direction == "BUY" else (m5_high >= c_vwap + 0.15 and m5_close < c_vwap)

        baseline_setups.append({
            'bar_idx': i,
            'idx': idx,
            'timestamp': timestamps[i],
            'direction': direction,
            'entry_price': high_t2 + spread if direction == "BUY" else low_t2,
            'm5_open': m5_open,
            'm5_close': m5_close,
            'm5_low': m5_low,
            'm5_high': m5_high,
            'c_vwap': c_vwap,
            'is_entirely_above_vwap': is_entirely_above_vwap,
            'is_entirely_below_vwap': is_entirely_below_vwap,
            'is_reclaim_3a': is_reclaim_3a,
            'is_reclaim_3b': is_reclaim_3b,
            'is_reclaim_3c': is_reclaim_3c,
            'is_reclaim_3d': is_reclaim_3d
        })

        last_trade_bar = i + 36

    df_base_setups = pd.DataFrame(baseline_setups)
    tot_base = len(df_base_setups)

    print(f"\n================================================================================")
    print(f" DIAGNOSTIC REASONING: WHY IS ORIGINAL H3 FREQUENCY LOW? ({tot_base:,} Total Baseline Setups)")
    print(f"================================================================================")
    
    above_cnt = df_base_setups['is_entirely_above_vwap'].sum()
    below_cnt = df_base_setups['is_entirely_below_vwap'].sum()
    str_rec_cnt = df_base_setups['is_reclaim_3a'].sum()
    b2_rec_cnt = df_base_setups['is_reclaim_3b'].sum()
    touch_rec_cnt = df_base_setups['is_reclaim_3c'].sum()
    sweep_rec_cnt = df_base_setups['is_reclaim_3d'].sum()

    print(f" 1. Setups already ENTIRELY ABOVE VWAP when triggering BUY (or below for SELL): {above_cnt:,} ({(above_cnt/tot_base)*100:.1f}%)")
    print(f"    -> REASON: Model 2 is a trend continuation engine; by the time H1 trend + M5 FVG + EMA21 sweep aligns,")
    print(f"       price is often ALREADY trading cleanly above Daily VWAP! Only ~8% of candles open below & close above VWAP.")
    print(f" 2. Setups triggering ENTIRELY BELOW VWAP (Stuck below fair value): {below_cnt:,} ({(below_cnt/tot_base)*100:.1f}%)")
    print(f" 3. Original Strict 1-Bar Reclaim (3A): {str_rec_cnt:,} setups ({(str_rec_cnt/tot_base)*100:.1f}%)")
    print(f" 4. Expanded 2-Bar Reclaim Window (3B): {b2_rec_cnt:,} setups ({(b2_rec_cnt/tot_base)*100:.1f}%)")
    print(f" 5. VWAP Touch & Reclaim (3C):          {touch_rec_cnt:,} setups ({(touch_rec_cnt/tot_base)*100:.1f}%)")
    print(f" 6. VWAP Deep Sweep & Reclaim (3D):     {sweep_rec_cnt:,} setups ({(sweep_rec_cnt/tot_base)*100:.1f}%)")
    print(f"--------------------------------------------------------------------------------")

    # 3. Simulate performance for each variant
    print("\n[3/4] Simulating 5 Variations of VWAP Reclaim to Increase Trade Frequency...")

    def run_variant_sim(variant_col):
        trades = []
        last_trade_bar = -10

        for i in range(50, n - 100):
            hour = hours_5m[i]
            if not (6 <= hour < 20): continue
            if i <= last_trade_bar + 1: continue

            idx = i - 1

            h1_c = h1_closes[idx]
            h1_e21 = h1_ema21s[idx]
            h1_e50 = h1_ema50s[idx]

            h1_bullish = (h1_c > h1_e21) and (h1_e21 > h1_e50)
            h1_bearish = (h1_c < h1_e21) and (h1_e21 < h1_e50)
            if not (h1_bullish or h1_bearish): continue

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
            m5_low = lows_5m[idx]
            m5_high = highs_5m[idx]

            bull_confirm = m5_close > m5_e21
            bear_confirm = m5_close < m5_e21

            base_buy = h1_bullish and is_bull_fvg and bull_sweep and bull_confirm
            base_sell = h1_bearish and is_bear_fvg and bear_sweep and bear_confirm

            if not (base_buy or base_sell): continue

            c_vwap = vwap_vals[idx]
            c_vwap_prev = vwap_vals[idx - 1]
            m5_close_prev = closes_5m[idx - 1]

            direction = "BUY" if base_buy else "SELL"

            valid = False
            if variant_col == "3a_strict":
                valid = (m5_open < c_vwap and m5_close > c_vwap) if direction == "BUY" else (m5_open > c_vwap and m5_close < c_vwap)
            elif variant_col == "3b_2bar":
                valid = ((m5_close_prev < c_vwap_prev or m5_open < c_vwap) and m5_close > c_vwap) if direction == "BUY" else ((m5_close_prev > c_vwap_prev or m5_open > c_vwap) and m5_close < c_vwap)
            elif variant_col == "3c_touch":
                valid = (m5_low <= c_vwap + 0.20 and m5_close > c_vwap) if direction == "BUY" else (m5_high >= c_vwap - 0.20 and m5_close < c_vwap)
            elif variant_col == "3d_sweep":
                valid = (m5_low <= c_vwap - 0.15 and m5_close > c_vwap) if direction == "BUY" else (m5_high >= c_vwap + 0.15 and m5_close < c_vwap)

            if not valid: continue

            recent_3_low = np.min(lows_5m[idx-2 : idx+1])
            recent_3_high = np.max(highs_5m[idx-2 : idx+1])

            if direction == "BUY":
                entry_price = high_t2 + spread
                sl_price = recent_3_low - 0.50
                sl_pips = np.clip((entry_price - sl_price) / pip_size, 15.0, 80.0)
                sl_price = entry_price - (sl_pips * pip_size)

                tp1_price = entry_price + (sl_pips * pip_size * 1.0)
                tp2_price = entry_price + (sl_pips * pip_size * 2.0)
                tp3_price = entry_price + (sl_pips * pip_size * 3.0)
            else:
                entry_price = low_t2
                sl_price = recent_3_high + 0.50
                sl_pips = np.clip((sl_price - entry_price) / pip_size, 15.0, 80.0)
                sl_price = entry_price + (sl_pips * pip_size)

                tp1_price = entry_price - (sl_pips * pip_size * 1.0)
                tp2_price = entry_price - (sl_pips * pip_size * 2.0)
                tp3_price = entry_price - (sl_pips * pip_size * 3.0)

            t1_hit, t2_hit, t3_hit = False, False, False
            exit_bar = i + 36

            risk_per_ticket = 33.33
            t1_pnl, t2_pnl, t3_pnl = -33.33, -33.33, -33.33

            for k in range(i, min(i + 36, n)):
                bar_h = highs_5m[k]
                bar_l = lows_5m[k]

                if direction == "BUY":
                    if bar_l <= sl_price:
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

    df_3a = run_variant_sim("3a_strict")
    df_3b = run_variant_sim("3b_2bar")
    df_3c = run_variant_sim("3c_touch")
    df_3d = run_variant_sim("3d_sweep")

    def print_variant_metrics(df, label):
        if len(df) == 0: return
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
        print(f" -> Total Trades Executed:   {tot:,} trades (~{(tot/(tot_w*5)):.2f} trades / day)")
        print(f" -> Win Rate (%):            {wr:.2f}% ({len(wins):,} W / {len(losses):,} L)")
        print(f" -> Net Cumulative Profit:   +${net:,.2f} ({(net/10000.0)*100.0:.2f}% Return)")
        print(f" -> Profit Factor (PF):      {pf:.2f}")
        print(f" -> Maximum Drawdown (%):    {dd:.2f}%")
        print(f" -> Weekly Consistency Rate: {wcons:.2f}% ({prof_w}/{tot_w} Weeks Profitable)")
        print(f"--------------------------------------------------------------------------------")

    print_variant_metrics(df_3a, "3A: Original Strict 1-Bar Reclaim (m5_open < VWAP & m5_close > VWAP)")
    print_variant_metrics(df_3b, "3B: 2-Bar Reclaim Window (Reclaimed VWAP in last 2 candles)")
    print_variant_metrics(df_3c, "3C: VWAP Touch & Reclaim (m5_low <= VWAP + $0.20 & m5_close > VWAP)")
    print_variant_metrics(df_3d, "3D: VWAP Deep Sweep & Reclaim (m5_low <= VWAP - $0.15 & m5_close > VWAP)")

    elapsed = time.time() - start_time
    print(f"\n[DONE] Hypothesis 3 frequency diagnostic finished in {elapsed:.2f} seconds.")

if __name__ == "__main__":
    run_hyp3_frequency_diagnosis()
