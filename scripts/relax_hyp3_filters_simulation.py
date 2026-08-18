"""
Empirical Benchmark: Relaxing Model 2 Filters for Hypothesis 3 (VWAP Reclaims).

Goal: Unlock 4,000+ High-Conviction Trades over 5 Years ($400k+ Net Return at $100 flat risk)
by relaxing restrictive secondary filters specifically on VWAP Reclaim setups.

Relaxation Tests:
1. Baseline Hypothesis 3 (Strict Model 2 Rules)
2. Test A: Remove M5 EMA21 Sweep Requirement (VWAP sweep is sufficient)
3. Test B: Lower FVG Requirement from 1.5 pips -> 0.8 pips ($0.08 on Gold)
4. Test C: Relax H1 Trend (Allow M15 Trend or Price vs H1 EMA21 instead of EMA21>EMA50)
5. Test D: Expanded Session Hours (02:00 UTC - 22:00 UTC)
6. Test E: Master Relaxed VWAP Reclaim Engine (All Filter Relaxations Combined)
"""

import sys
from pathlib import Path
import pandas as pd
import numpy as np
import time

def run_relaxed_hyp3_benchmark():
    proc_5m_path = Path("data/processed/xau_5m_5y.parquet")
    if not proc_5m_path.exists():
        print("[ERROR] 5m dataset missing!")
        return

    print("================================================================================")
    print("  HYPOTHESIS 3 (VWAP RECLAIM) FILTER RELAXATION BENCHMARK (5-YEAR DATA)")
    print("================================================================================")

    start_time = time.time()

    print("[1/3] Loading 5-Year XAU/USD 5-Minute Data...")
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

    # H1 Trend
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

    # M15 Trend (for relaxed H1 test)
    df_m15 = df_5m.resample('15min', on='timestamp').agg({
        'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last'
    }).dropna().reset_index()
    df_m15['ema21'] = df_m15['close'].ewm(span=21, adjust=False).mean()

    df_5m['m15_time'] = df_5m['timestamp'].dt.floor('15min')
    df_5m = pd.merge_asof(
        df_5m,
        df_m15[['timestamp', 'ema21', 'close']].rename(columns={
            'timestamp': 'm15_time', 'ema21': 'm15_ema21', 'close': 'm15_close'
        }),
        on='m15_time', direction='backward'
    )
    m15_closes = df_5m['m15_close'].values
    m15_ema21s = df_5m['m15_ema21'].values

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
    daily_vwap = df_5m['cum_tp_vol'].values / cum_vol_vals

    pip_size = 0.10
    spread = 0.15

    print("[2/3] Simulating Filter Relaxations for VWAP Reclaim Setups...")

    def run_relaxation_sim(mode="baseline"):
        trades = []
        last_trade_bar = -10

        for i in range(50, n - 100):
            hour = hours_5m[i]

            # Session Hour Rule
            start_h, end_h = (6, 20)
            if mode in ["test_d_session", "master_relaxed"]:
                start_h, end_h = (2, 22)

            if not (start_h <= hour < end_h): continue
            if i <= last_trade_bar + 1: continue

            idx = i - 1  # closed candle

            # H1 / Trend Filter
            h1_c = h1_closes[idx]
            h1_e21 = h1_ema21s[idx]
            h1_e50 = h1_ema50s[idx]
            m15_c = m15_closes[idx]
            m15_e21 = m15_ema21s[idx]

            if mode in ["test_c_h1_trend", "master_relaxed"]:
                # Relaxed trend: Close > EMA21 on H1 OR M15
                h1_bullish = (h1_c > h1_e21) or (m15_c > m15_e21)
                h1_bearish = (h1_c < h1_e21) or (m15_c < m15_e21)
            else:
                # Strict H1 trend
                h1_bullish = (h1_c > h1_e21) and (h1_e21 > h1_e50)
                h1_bearish = (h1_c < h1_e21) and (h1_e21 < h1_e50)

            if not (h1_bullish or h1_bearish): continue

            # FVG Requirement
            low_t = lows_5m[idx]
            high_t = highs_5m[idx]
            low_t2 = lows_5m[idx - 2]
            high_t2 = highs_5m[idx - 2]

            bull_fvg_pips = (low_t - high_t2) / pip_size
            bear_fvg_pips = (low_t2 - high_t) / pip_size

            fvg_threshold = 1.5
            if mode in ["test_b_fvg", "master_relaxed"]:
                fvg_threshold = 0.8  # Relaxed to 0.8 pips ($0.08 on Gold)

            is_bull_fvg = bull_fvg_pips >= fvg_threshold
            is_bear_fvg = bear_fvg_pips >= fvg_threshold

            # EMA21 Sweep Requirement
            prior_5_low = np.min(lows_5m[idx-5 : idx])
            prior_5_high = np.max(highs_5m[idx-5 : idx])
            m5_e21 = m5_ema21s[idx]

            bull_sweep = prior_5_low <= m5_e21
            bear_sweep = prior_5_high >= m5_e21

            if mode in ["test_a_no_ema_sweep", "master_relaxed"]:
                bull_sweep = True  # EMA sweep not required when sweeping VWAP
                bear_sweep = True

            m5_close = closes_5m[idx]
            m5_open = opens_5m[idx]
            m5_low = lows_5m[idx]
            m5_high = highs_5m[idx]

            base_buy = h1_bullish and is_bull_fvg and bull_sweep
            base_sell = h1_bearish and is_bear_fvg and bear_sweep

            if not (base_buy or base_sell): continue

            c_vwap = daily_vwap[idx]
            direction = "BUY" if base_buy else "SELL"

            # VWAP Touch/Reclaim condition: Low <= VWAP + $0.20 and Close > VWAP
            valid_vwap_reclaim = (m5_low <= c_vwap + 0.20 and m5_close > c_vwap) if direction == "BUY" else (m5_high >= c_vwap - 0.20 and m5_close < c_vwap)

            if not valid_vwap_reclaim: continue

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

            risk_per_ticket = 33.33  # $100 flat risk setup ($33.33 per target)
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
                        t2_pnl = ticket_risk = risk_per_ticket * 2.0
                    if t2_hit and not t3_hit and bar_l <= tp3_price:
                        t3_hit = True
                        t3_pnl = risk_per_ticket * 3.0
                        exit_bar = k
                        break

            setup_pnl = t1_pnl + t2_pnl + t3_pnl
            trades.append({
                'timestamp': timestamps[i],
                'direction': direction,
                'pnl': setup_pnl,
                'is_win': setup_pnl > 0
            })

            last_trade_bar = exit_bar

        return pd.DataFrame(trades)

    df_base = run_relaxation_sim("baseline")
    df_no_ema = run_relaxation_sim("test_a_no_ema_sweep")
    df_fvg = run_relaxation_sim("test_b_fvg")
    df_h1 = run_relaxation_sim("test_c_h1_trend")
    df_sess = run_relaxation_sim("test_d_session")
    df_master = run_relaxation_sim("master_relaxed")

    def print_rel_metrics(df, label):
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

    print_rel_metrics(df_base, "0. BASELINE H3 (Touch & Reclaim)")
    print_rel_metrics(df_no_ema, "1. TEST A: Remove M5 EMA21 Sweep Requirement")
    print_rel_metrics(df_fvg, "2. TEST B: Lower FVG Requirement to 0.8 pips ($0.08)")
    print_rel_metrics(df_h1, "3. TEST C: Relaxed H1/M15 Trend Filter")
    print_rel_metrics(df_sess, "4. TEST D: Expanded Session Hours (02:00 - 22:00 UTC)")
    print_rel_metrics(df_master, "5. MASTER RELAXED VWAP RECLAIM ENGINE (All Relaxations Combined)")

    elapsed = time.time() - start_time
    print(f"\n[DONE] Relaxation benchmark finished in {elapsed:.2f} seconds.")

if __name__ == "__main__":
    run_relaxed_hyp3_benchmark()
