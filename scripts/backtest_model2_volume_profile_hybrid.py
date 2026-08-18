"""
Refined Empirical Backtester: Model 2 (M5 Scalp Hybrid) vs Volume Profile Engine (WITHOUT TRAILING STOPS).

Evaluates 5-Year Master Data (2021 - 2026 / 396,000+ 5m bars).
Tests:
1. Baseline Model 2 (No Trailing SL - Fixed Structural SL).
2. Model 2 + Volume Profile Engine (No Trailing SL - Fixed Structural SL).
3. Model 2 + Volume Profile Engine (With Trailing SL to POC/BE).
"""

import sys
from pathlib import Path
from datetime import datetime, date
import pandas as pd
import numpy as np
import time

from volume_profile_engine import VolumeProfileEngine

def run_no_trailing_backtest():
    proc_5m_path = Path("data/processed/xau_5m_5y.parquet")
    if not proc_5m_path.exists():
        print("[ERROR] 5m dataset missing!")
        return

    print("================================================================================")
    print("  MODEL 2 (M5 SCALP HYBRID) vs VOLUME PROFILE ENGINE (WITHOUT TRAILING STOPS)")
    print("================================================================================")

    start_time = time.time()

    print("[1/5] Loading 5-Year XAU/USD 5-Minute Parquet Data...")
    df_5m = pd.read_parquet(proc_5m_path)
    df_5m['timestamp'] = pd.to_datetime(df_5m['timestamp'])

    # Sort & extract core arrays
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
    hours_5m = df_5m['hour'].values
    minutes_5m = df_5m['minute'].values
    dates_5m = df_5m['date'].values
    timestamps = df_5m['timestamp'].values

    # Pre-compute H1 EMAs for Macro Trend Filter
    print("[2/5] Resampling 1-Hour Chart & Computing H1 EMA(21) vs EMA(50)...")
    df_h1 = df_5m.resample('1h', on='timestamp').agg({
        'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last'
    }).dropna().reset_index()

    df_h1['ema21'] = df_h1['close'].ewm(span=21, adjust=False).mean()
    df_h1['ema50'] = df_h1['close'].ewm(span=50, adjust=False).mean()

    # Map H1 trend back to M5 bars
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

    # Pre-compute M5 EMA21
    df_5m['m5_ema21'] = df_5m['close'].ewm(span=21, adjust=False).mean()
    m5_ema21s = df_5m['m5_ema21'].values

    vp_engine = VolumeProfileEngine(bin_size=0.25, va_pct=0.70)

    pip_size = 0.10
    spread = 0.15

    def run_backtest_simulation(use_vp=False, use_trailing_sl=False):
        trades = []
        last_trade_bar = -10

        curr_day = None
        day_start_idx = 0

        for i in range(50, n - 100):
            hour = hours_5m[i]
            d = dates_5m[i]

            if d != curr_day:
                curr_day = d
                day_start_idx = i

            # Session Filter: 06:00 to 20:00 UTC
            if not (6 <= hour < 20):
                continue

            if i <= last_trade_bar + 1:
                continue

            idx = i - 1  # Closed Candle Indexing iloc[-2]

            # H1 Macro Trend Alignment Filter
            h1_c = h1_closes[idx]
            h1_e21 = h1_ema21s[idx]
            h1_e50 = h1_ema50s[idx]

            h1_bullish = (h1_c > h1_e21) and (h1_e21 > h1_e50)
            h1_bearish = (h1_c < h1_e21) and (h1_e21 < h1_e50)

            if not (h1_bullish or h1_bearish):
                continue

            # M5 FVG Displacement
            low_t = lows_5m[idx]
            high_t = highs_5m[idx]
            low_t2 = lows_5m[idx - 2]
            high_t2 = highs_5m[idx - 2]

            bull_fvg_pips = (low_t - high_t2) / pip_size
            bear_fvg_pips = (low_t2 - high_t) / pip_size

            is_bull_fvg = bull_fvg_pips >= 1.5
            is_bear_fvg = bear_fvg_pips >= 1.5

            # Institutional Liquidity Sweep
            prior_5_low = np.min(lows_5m[idx-5 : idx])
            prior_5_high = np.max(highs_5m[idx-5 : idx])
            m5_e21 = m5_ema21s[idx]

            bull_sweep = prior_5_low <= m5_e21
            bear_sweep = prior_5_high >= m5_e21

            # Micro-Structure Close Confirmation
            m5_close = closes_5m[idx]
            bull_confirm = m5_close > m5_e21
            bear_confirm = m5_close < m5_e21

            buy_signal = h1_bullish and is_bull_fvg and bull_sweep and bull_confirm
            sell_signal = h1_bearish and is_bear_fvg and bear_sweep and bear_confirm

            if not (buy_signal or sell_signal):
                continue

            vp_data = None
            if use_vp:
                if i - day_start_idx >= 12:
                    dev_highs = highs_5m[day_start_idx : i]
                    dev_lows = lows_5m[day_start_idx : i]
                    dev_closes = closes_5m[day_start_idx : i]
                    vp_data = vp_engine.compute_profile(dev_highs, dev_lows, dev_closes)

            if use_vp and vp_data is not None:
                vah = vp_data['vah']
                val = vp_data['val']

                # Reject overextension outside VA
                if buy_signal and (m5_close - vah > 3.00):
                    continue
                if sell_signal and (val - m5_close > 3.00):
                    continue

            # Structural Entry & Stop Loss Calculation
            recent_3_low = np.min(lows_5m[idx-2 : idx+1])
            recent_3_high = np.max(highs_5m[idx-2 : idx+1])

            if buy_signal:
                direction = "BUY"
                entry_price = high_t2 + spread
                sl_price = recent_3_low - 0.50
                raw_sl_pips = (entry_price - sl_price) / pip_size
                sl_pips = np.clip(raw_sl_pips, 15.0, 80.0)
                sl_price = entry_price - (sl_pips * pip_size)

                tp1_price = entry_price + (sl_pips * pip_size * 1.0)
                tp2_price = entry_price + (sl_pips * pip_size * 2.0)
                tp3_price = entry_price + (sl_pips * pip_size * 3.0)

            else:
                direction = "SELL"
                entry_price = low_t2
                sl_price = recent_3_high + 0.50
                raw_sl_pips = (sl_price - entry_price) / pip_size
                sl_pips = np.clip(raw_sl_pips, 15.0, 80.0)
                sl_price = entry_price + (sl_pips * pip_size)

                tp1_price = entry_price - (sl_pips * pip_size * 1.0)
                tp2_price = entry_price - (sl_pips * pip_size * 2.0)
                tp3_price = entry_price - (sl_pips * pip_size * 3.0)

            # Trade Simulation Execution
            t1_hit, t2_hit, t3_hit = False, False, False
            sl_hit = False
            exit_bar = i + 36

            risk_per_ticket = 33.33
            t1_pnl, t2_pnl, t3_pnl = -33.33, -33.33, -33.33

            curr_sl = sl_price

            for k in range(i, min(i + 36, n)):
                bar_h = highs_5m[k]
                bar_l = lows_5m[k]

                if direction == "BUY":
                    if bar_l <= curr_sl:
                        sl_hit = True
                        exit_bar = k
                        break
                    if not t1_hit and bar_h >= tp1_price:
                        t1_hit = True
                        t1_pnl = risk_per_ticket * 1.0
                        if use_trailing_sl:
                            if use_vp and vp_data is not None:
                                curr_sl = max(entry_price, vp_data['poc'])
                            else:
                                curr_sl = entry_price
                    if t1_hit and not t2_hit and bar_h >= tp2_price:
                        t2_hit = True
                        t2_pnl = risk_per_ticket * 2.0
                    if t2_hit and not t3_hit and bar_h >= tp3_price:
                        t3_hit = True
                        t3_pnl = risk_per_ticket * 3.0
                        exit_bar = k
                        break
                else:  # SELL
                    if bar_h >= curr_sl:
                        sl_hit = True
                        exit_bar = k
                        break
                    if not t1_hit and bar_l <= tp1_price:
                        t1_hit = True
                        t1_pnl = risk_per_ticket * 1.0
                        if use_trailing_sl:
                            if use_vp and vp_data is not None:
                                curr_sl = min(entry_price, vp_data['poc'])
                            else:
                                curr_sl = entry_price
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
                't1_hit': t1_hit,
                't2_hit': t2_hit,
                't3_hit': t3_hit,
                'sl_hit': sl_hit,
                'pnl': setup_pnl,
                'is_win': setup_pnl > 0
            })

            last_trade_bar = exit_bar

        return pd.DataFrame(trades)

    print("[3/5] Running Baseline Model 2 (NO TRAILING SL)...")
    df_base_no_trail = run_backtest_simulation(use_vp=False, use_trailing_sl=False)

    print("[4/5] Running Model 2 + Volume Profile (NO TRAILING SL)...")
    df_vp_no_trail = run_backtest_simulation(use_vp=True, use_trailing_sl=False)

    print("[5/5] Running Model 2 + Volume Profile (WITH TRAILING SL)...")
    df_vp_with_trail = run_backtest_simulation(use_vp=True, use_trailing_sl=True)

    def format_stats(df, label):
        if len(df) == 0:
            print(f"[{label}] No trades.")
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

    format_stats(df_base_no_trail, "1. BASELINE MODEL 2 (NO TRAILING SL)")
    format_stats(df_vp_no_trail, "2. MODEL 2 + VOLUME PROFILE (NO TRAILING SL)")
    format_stats(df_vp_with_trail, "3. MODEL 2 + VOLUME PROFILE (WITH TRAILING SL)")

    elapsed = time.time() - start_time
    print(f"\n[DONE] Comparative backtest finished in {elapsed:.2f} seconds.")

if __name__ == "__main__":
    run_no_trailing_backtest()
