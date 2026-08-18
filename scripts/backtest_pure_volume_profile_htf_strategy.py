"""
Pure Volume Profile + HTF Bias Strategy Engine (Standalone).

Implements pure Auction Market Theory rules using 5-Year XAU/USD data (2021 - 2026):
1. Higher Timeframe Alignment (H1 EMA 21 vs 50 Trend Bias).
2. Value Area Extreme Reversals (VAL Bounce -> BUY targeting POC / VAH Bounce -> SELL targeting POC).
3. Value Area Acceptance Breakouts (VAH Break & Hold -> BUY / VAL Break & Hold -> SELL).
"""

import sys
from pathlib import Path
from datetime import datetime, date
import pandas as pd
import numpy as np
import time

from volume_profile_engine import VolumeProfileEngine

def run_pure_vp_htf_backtest():
    proc_5m_path = Path("data/processed/xau_5m_5y.parquet")
    if not proc_5m_path.exists():
        print("[ERROR] 5m dataset missing!")
        return

    print("================================================================================")
    print("   PURE VOLUME PROFILE + HIGHER TIMEFRAME BIAS STRATEGY BACKTEST ENGINE")
    print("================================================================================")

    start_time = time.time()

    print("[1/4] Loading 5-Year XAU/USD 5-Minute Parquet Data...")
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

    print("[2/4] Resampling 1-Hour Chart & Computing H1 EMA(21) vs EMA(50) Trend Bias...")
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

    # Compute Daily Volume Profiles (VAH, VAL, POC)
    print("[3/4] Pre-computing Session Volume Profiles (VAH, VAL, POC)...")
    vp_engine = VolumeProfileEngine(bin_size=0.25, va_pct=0.70)
    unique_dates = sorted(df_5m['date'].unique())
    daily_vp_map = {}

    for d in unique_dates:
        mask = dates_5m == d
        d_highs = highs_5m[mask]
        d_lows = lows_5m[mask]
        d_closes = closes_5m[mask]
        profile = vp_engine.compute_profile(d_highs, d_lows, d_closes)
        if profile is not None:
            daily_vp_map[d] = profile

    pip_size = 0.10
    spread = 0.15

    def evaluate_vp_strategy(setup_type="all"):
        """
        setup_type: 'reversal' (VAL/VAH mean-reversion), 'acceptance' (breakout), 'all'
        """
        trades = []
        last_trade_bar = -10

        for i in range(50, n - 100):
            hour = hours_5m[i]
            # Session Window: 06:00 to 20:00 UTC
            if not (6 <= hour < 20):
                continue

            if i <= last_trade_bar + 1:
                continue

            idx = i - 1  # iloc[-2] closed candle

            # H1 Trend Bias
            h1_c = h1_closes[idx]
            h1_e21 = h1_ema21s[idx]
            h1_e50 = h1_ema50s[idx]

            h1_bullish = (h1_c > h1_e21) and (h1_e21 > h1_e50)
            h1_bearish = (h1_c < h1_e21) and (h1_e21 < h1_e50)

            if not (h1_bullish or h1_bearish):
                continue

            # Fetch Yesterday's Volume Profile
            curr_date = dates_5m[i]
            date_idx = unique_dates.index(curr_date) if curr_date in unique_dates else -1
            prev_date = unique_dates[date_idx - 1] if date_idx > 0 else None
            vp_prev = daily_vp_map.get(prev_date, None)

            if vp_prev is None:
                continue

            poc = vp_prev['poc']
            vah = vp_prev['vah']
            val = vp_prev['val']

            c_open = opens_5m[idx]
            c_high = highs_5m[idx]
            c_low = lows_5m[idx]
            c_close = closes_5m[idx]

            # -------------------------------------------------------------------------------------
            # SETUP 1: VALUE AREA REVERSAL (VAL / VAH Rejection -> Targeting POC)
            # -------------------------------------------------------------------------------------
            # BUY: H1 Bullish + Price swept below VAL + Closed back above VAL
            rev_buy = h1_bullish and (c_low <= val) and (c_close > val) and (c_close > c_open)
            # SELL: H1 Bearish + Price swept above VAH + Closed back below VAH
            rev_sell = h1_bearish and (c_high >= vah) and (c_close < vah) and (c_close < c_open)

            # -------------------------------------------------------------------------------------
            # SETUP 2: VALUE AREA ACCEPTANCE (VAH / VAL Breakout Expansion)
            # -------------------------------------------------------------------------------------
            # BUY: H1 Bullish + Price broke above VAH + Closed firmly above VAH
            acc_buy = h1_bullish and (c_low >= vah) and (c_close > vah + 0.30) and (c_close > c_open)
            # SELL: H1 Bearish + Price broke below VAL + Closed firmly below VAL
            acc_sell = h1_bearish and (c_high <= val) and (c_close < val - 0.30) and (c_close < c_open)

            buy_signal, sell_signal = False, False
            trade_mode = ""

            if setup_type in ["reversal", "all"]:
                if rev_buy:
                    buy_signal = True
                    trade_mode = "VAL Reversal (Target POC)"
                elif rev_sell:
                    sell_signal = True
                    trade_mode = "VAH Reversal (Target POC)"

            if setup_type in ["acceptance", "all"] and not (buy_signal or sell_signal):
                if acc_buy:
                    buy_signal = True
                    trade_mode = "VAH Acceptance (Target Expansion)"
                elif acc_sell:
                    sell_signal = True
                    trade_mode = "VAL Acceptance (Target Expansion)"

            if not (buy_signal or sell_signal):
                continue

            # Risk & Target Calculation
            if buy_signal:
                direction = "BUY"
                entry_price = c_close + spread
                sl_price = np.min(lows_5m[idx-2 : idx+1]) - 0.50
                sl_pips = np.clip((entry_price - sl_price) / pip_size, 15.0, 80.0)
                sl_price = entry_price - (sl_pips * pip_size)

                if "Reversal" in trade_mode:
                    tp_price = max(poc, entry_price + (sl_pips * pip_size * 1.5))
                else:
                    tp_price = entry_price + (sl_pips * pip_size * 2.0)

            else:  # SELL
                direction = "SELL"
                entry_price = c_close - spread
                sl_price = np.max(highs_5m[idx-2 : idx+1]) + 0.50
                sl_pips = np.clip((sl_price - entry_price) / pip_size, 15.0, 80.0)
                sl_price = entry_price + (sl_pips * pip_size)

                if "Reversal" in trade_mode:
                    tp_price = min(poc, entry_price - (sl_pips * pip_size * 1.5))
                else:
                    tp_price = entry_price - (sl_pips * pip_size * 2.0)

            # Trade Simulation Execution (Max 36 bars = 3 hours)
            t_hit = False
            sl_hit = False
            exit_bar = i + 36

            risk_amount = 100.0
            r_multiple = abs(tp_price - entry_price) / abs(entry_price - sl_price)
            reward_amount = risk_amount * r_multiple

            trade_pnl = -risk_amount

            for k in range(i, min(i + 36, n)):
                bar_h = highs_5m[k]
                bar_l = lows_5m[k]

                if direction == "BUY":
                    if bar_l <= sl_price:
                        sl_hit = True
                        exit_bar = k
                        break
                    if bar_h >= tp_price:
                        t_hit = True
                        trade_pnl = reward_amount
                        exit_bar = k
                        break
                else:  # SELL
                    if bar_h >= sl_price:
                        sl_hit = True
                        exit_bar = k
                        break
                    if bar_l <= tp_price:
                        t_hit = True
                        trade_pnl = reward_amount
                        exit_bar = k
                        break

            trades.append({
                'timestamp': timestamps[i],
                'direction': direction,
                'mode': trade_mode,
                'entry_price': entry_price,
                'sl_pips': sl_pips,
                'r_multiple': r_multiple,
                'is_win': trade_pnl > 0,
                'pnl': trade_pnl
            })

            last_trade_bar = exit_bar

        return pd.DataFrame(trades)

    print("[4/4] Evaluating Pure Volume Profile Setups...")
    df_rev = evaluate_vp_strategy(setup_type="reversal")
    df_acc = evaluate_vp_strategy(setup_type="acceptance")
    df_all = evaluate_vp_strategy(setup_type="all")

    def print_results(df, label):
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

    print_results(df_rev, "1. PURE VALUE AREA REVERSAL ENGINE (VAL/VAH Bounce -> POC)")
    print_results(df_acc, "2. PURE VALUE AREA ACCEPTANCE ENGINE (VAH/VAL Breakout)")
    print_results(df_all, "3. PURE VOLUME PROFILE + HTF BIAS MASTER STRATEGY (Combined)")

    elapsed = time.time() - start_time
    print(f"\n[DONE] Pure Volume Profile backtest finished in {elapsed:.2f} seconds.")

if __name__ == "__main__":
    run_pure_vp_htf_backtest()
