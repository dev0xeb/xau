"""
High-Confluence Volume Profile + Model 2 Engine.

Focuses on INCREASING WIN RATE by testing Session-Specific VP Confluence:
1. Asian Session (00:00 - 06:00 UTC) Volume Profile (VAH, VAL, POC).
2. Model 2 M5 Execution + Asian VP Level Sweep/Bounce Confluence.
3. HVN Support/Resistance Cluster Alignment.
"""

import sys
from pathlib import Path
from datetime import datetime, date
import pandas as pd
import numpy as np
import time

from volume_profile_engine import VolumeProfileEngine

def run_high_confluence_test():
    proc_5m_path = Path("data/processed/xau_5m_5y.parquet")
    if not proc_5m_path.exists():
        print("[ERROR] 5m dataset missing!")
        return

    print("================================================================================")
    print("   SESSION-SPECIFIC VOLUME PROFILE + MODEL 2 HIGH-CONFLUENCE WIN-RATE ENGINE")
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
    hours_5m = df_5m['hour'].values
    minutes_5m = df_5m['minute'].values
    dates_5m = df_5m['date'].values
    timestamps = df_5m['timestamp'].values

    # Pre-compute H1 EMAs
    print("[2/4] Computing H1 Macro Trend (EMA 21 vs 50)...")
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

    vp_engine = VolumeProfileEngine(bin_size=0.25, va_pct=0.70)

    # Calculate Asian Session (00:00 - 06:00 UTC) Volume Profile for every day
    print("[3/4] Calculating Asian Session (00:00-06:00 UTC) Volume Profiles...")
    unique_dates = sorted(df_5m['date'].unique())
    asian_vp_map = {}

    for d in unique_dates:
        mask = (dates_5m == d) & (hours_5m >= 0) & (hours_5m < 6)
        if np.sum(mask) >= 12:  # at least 1 hour of Asian data
            d_highs = highs_5m[mask]
            d_lows = lows_5m[mask]
            d_closes = closes_5m[mask]
            profile = vp_engine.compute_profile(d_highs, d_lows, d_closes)
            if profile is not None:
                asian_vp_map[d] = profile

    print(f" -> Computed Asian Session Profiles for {len(asian_vp_map)} trading days.")

    pip_size = 0.10
    spread = 0.15

    def run_confluence_backtest(confluence_mode="asian_level_touch"):
        """
        confluence_mode:
        - 'none': Baseline Model 2
        - 'asian_level_touch': Model 2 entry MUST touch or sweep Asian VAH, VAL, or POC (+/- $0.50)
        - 'asian_poc_only': Model 2 entry MUST touch or sweep Asian POC (+/- $0.75)
        - 'hvn_confluence': Model 2 entry MUST land on a High Volume Node (HVN) cluster
        """
        trades = []
        last_trade_bar = -10

        for i in range(50, n - 100):
            hour = hours_5m[i]
            d = dates_5m[i]

            # London & NY Session Filter: 06:00 to 20:00 UTC
            if not (6 <= hour < 20):
                continue

            if i <= last_trade_bar + 1:
                continue

            idx = i - 1  # iloc[-2] closed candle

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

            # -------------------------------------------------------------------------------------
            # VOLUME PROFILE HIGH-CONFLUENCE CHECK
            # -------------------------------------------------------------------------------------
            asian_vp = asian_vp_map.get(d, None)

            if confluence_mode != "none":
                if asian_vp is None:
                    continue

                poc = asian_vp['poc']
                vah = asian_vp['vah']
                val = asian_vp['val']
                hvns = asian_vp['hvn_prices']

                entry_zone_low = prior_5_low if buy_signal else m5_close
                entry_zone_high = m5_close if buy_signal else prior_5_high

                if confluence_mode == "asian_level_touch":
                    # Check if Model 2 sweep touched Asian VAH, VAL, or POC within +/- $0.50
                    touches_poc = np.abs(entry_zone_low - poc) <= 0.75 or np.abs(entry_zone_high - poc) <= 0.75
                    touches_val = np.abs(entry_zone_low - val) <= 0.75 or np.abs(entry_zone_high - val) <= 0.75
                    touches_vah = np.abs(entry_zone_low - vah) <= 0.75 or np.abs(entry_zone_high - vah) <= 0.75
                    if not (touches_poc or touches_val or touches_vah):
                        continue  # Require Asian VP level confluence!

                elif confluence_mode == "asian_poc_only":
                    touches_poc = np.abs(entry_zone_low - poc) <= 0.75 or np.abs(entry_zone_high - poc) <= 0.75
                    if not touches_poc:
                        continue  # Require Asian POC level confluence!

                elif confluence_mode == "hvn_confluence":
                    # Check if entry zone lands on an HVN cluster
                    lands_on_hvn = np.any(np.abs(hvns - m5_close) <= 0.50)
                    if not lands_on_hvn:
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

            # Trade Simulation Execution (Fixed SL, No Trailing Stop Loss)
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
                't1_hit': t1_hit,
                't2_hit': t2_hit,
                't3_hit': t3_hit,
                'sl_hit': sl_hit,
                'pnl': setup_pnl,
                'is_win': setup_pnl > 0
            })

            last_trade_bar = exit_bar

        return pd.DataFrame(trades)

    print("[4/4] Running Comparative Confluence Simulations...")
    df_base = run_confluence_backtest(confluence_mode="none")
    df_asian_touch = run_confluence_backtest(confluence_mode="asian_level_touch")
    df_asian_poc = run_confluence_backtest(confluence_mode="asian_poc_only")
    df_hvn = run_confluence_backtest(confluence_mode="hvn_confluence")

    def print_metrics(df, label):
        if len(df) == 0:
            print(f"\n[{label}] No trades executed.")
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

    print_metrics(df_base, "1. BASELINE MODEL 2 (No Volume Profile Filter)")
    print_metrics(df_asian_touch, "2. MODEL 2 + ASIAN SESSION VP LEVEL CONFLUENCE (VAH/VAL/POC Touch)")
    print_metrics(df_asian_poc, "3. MODEL 2 + ASIAN SESSION POC MAGNET CONFLUENCE (POC Touch Only)")
    print_metrics(df_hvn, "4. MODEL 2 + HIGH VOLUME NODE (HVN) CLUSTER CONFLUENCE")

    elapsed = time.time() - start_time
    print(f"\n[DONE] High-confluence backtest completed in {elapsed:.2f} seconds.")

if __name__ == "__main__":
    run_high_confluence_test()
