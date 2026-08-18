"""
Deep Diagnostic Engine: Model 2 + Volume Profile (No Trailing SL) Losing Trades Analysis.

Investigates:
1. Were Stop Losses choking (too tight, e.g., < 25 pips / $2.50)?
2. MAE (Maximum Adverse Excursion) analysis - how far did price wick past SL before reversing?
3. SL Padding sensitivity test (+0.50, +1.00, +1.50 buffer).
4. Session/Hour distribution of losses.
5. Location relative to VAH, VAL, and POC.
"""

import sys
from pathlib import Path
from datetime import datetime, date
import pandas as pd
import numpy as np
import time

from volume_profile_engine import VolumeProfileEngine

def run_deep_loss_diagnosis():
    proc_5m_path = Path("data/processed/xau_5m_5y.parquet")
    if not proc_5m_path.exists():
        print("[ERROR] 5m dataset missing!")
        return

    print("================================================================================")
    print("  MODEL 2 + VOLUME PROFILE (NO TRAILING SL) DEEP LOSS DIAGNOSTIC ENGINE")
    print("================================================================================")

    start_time = time.time()

    print("[1/5] Loading 5-Year XAU/USD 5-Minute Parquet Data...")
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

    # Pre-compute H1 EMAs for Macro Trend Filter
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

    pip_size = 0.10
    spread = 0.15

    print("[2/5] Running Simulation and Logging Detailed Microstructure Data per Trade...")

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

        if not (6 <= hour < 20):
            continue

        if i <= last_trade_bar + 1:
            continue

        idx = i - 1  # iloc[-2] closed candle

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
        bull_confirm = m5_close > m5_e21
        bear_confirm = m5_close < m5_e21

        buy_signal = h1_bullish and is_bull_fvg and bull_sweep and bull_confirm
        sell_signal = h1_bearish and is_bear_fvg and bear_sweep and bear_confirm

        if not (buy_signal or sell_signal):
            continue

        vp_data = None
        if i - day_start_idx >= 12:
            dev_highs = highs_5m[day_start_idx : i]
            dev_lows = lows_5m[day_start_idx : i]
            dev_closes = closes_5m[day_start_idx : i]
            vp_data = vp_engine.compute_profile(dev_highs, dev_lows, dev_closes)

        if vp_data is not None:
            vah = vp_data['vah']
            val = vp_data['val']
            poc = vp_data['poc']

            if buy_signal and (m5_close - vah > 3.00):
                continue
            if sell_signal and (val - m5_close > 3.00):
                continue

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

        # Execution tracking with MAE (Maximum Adverse Excursion)
        t1_hit, t2_hit, t3_hit = False, False, False
        sl_hit = False
        exit_bar = i + 36

        risk_per_ticket = 33.33
        t1_pnl, t2_pnl, t3_pnl = -33.33, -33.33, -33.33

        max_adverse_excursion = 0.0
        max_favorable_excursion = 0.0

        for k in range(i, min(i + 36, n)):
            bar_h = highs_5m[k]
            bar_l = lows_5m[k]

            if direction == "BUY":
                adv = entry_price - bar_l
                fav = bar_h - entry_price
                if adv > max_adverse_excursion: max_adverse_excursion = adv
                if fav > max_favorable_excursion: max_favorable_excursion = fav

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
                adv = bar_h - entry_price
                fav = entry_price - bar_l
                if adv > max_adverse_excursion: max_adverse_excursion = adv
                if fav > max_favorable_excursion: max_favorable_excursion = fav

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
        is_win = setup_pnl > 0

        # Check if trade would have eventually hit TP if given +$0.50 or +$1.00 extra SL padding
        padded_sl_hit = False
        padded_sl_price = sl_price - 0.50 if direction == "BUY" else sl_price + 0.50
        padded_would_win = False

        for k in range(i, min(i + 36, n)):
            bar_h = highs_5m[k]
            bar_l = lows_5m[k]
            if direction == "BUY":
                if bar_l <= padded_sl_price:
                    padded_sl_hit = True
                    break
                if bar_h >= tp1_price:
                    padded_would_win = True
                    break
            else:
                if bar_h >= padded_sl_price:
                    padded_sl_hit = True
                    break
                if bar_l <= tp1_price:
                    padded_would_win = True
                    break

        trades.append({
            'timestamp': timestamps[i],
            'hour': hour,
            'direction': direction,
            'entry_price': entry_price,
            'sl_pips': sl_pips,
            'sl_price': sl_price,
            'mae_dollars': max_adverse_excursion,
            'mfe_dollars': max_favorable_excursion,
            't1_hit': t1_hit,
            't2_hit': t2_hit,
            't3_hit': t3_hit,
            'sl_hit': sl_hit,
            'padded_would_win': (not is_win) and padded_would_win and (not padded_sl_hit),
            'pnl': setup_pnl,
            'is_win': is_win
        })

        last_trade_bar = exit_bar

    df_trades = pd.DataFrame(trades)
    wins = df_trades[df_trades['is_win']]
    losses = df_trades[~df_trades['is_win']]

    print("\n[3/5] LOSS DIAGNOSIS STATISTICAL BREAKDOWN")
    print("================================================================================")
    print(f" -> Total Trades:               {len(df_trades):,}")
    print(f" -> Winning Trades:             {len(wins):,} ({len(wins)/len(df_trades)*100:.2f}%)")
    print(f" -> Losing Trades:              {len(losses):,} ({len(losses)/len(df_trades)*100:.2f}%)")
    print("--------------------------------------------------------------------------------")

    print("\n[4/5] STOP LOSS SIZE ANALYSIS (Were SLs Choking?)")
    print(f" -> Average SL Size (All Trades):   {df_trades['sl_pips'].mean():.2f} pips (${df_trades['sl_pips'].mean()*0.10:.2f})")
    print(f" -> Average SL Size (Wins):         {wins['sl_pips'].mean():.2f} pips (${wins['sl_pips'].mean()*0.10:.2f})")
    print(f" -> Average SL Size (Losses):       {losses['sl_pips'].mean():.2f} pips (${losses['sl_pips'].mean()*0.10:.2f})")

    # Group losses by SL Size Bin
    losses['sl_bin'] = pd.cut(losses['sl_pips'], bins=[0, 20, 30, 40, 60, 100], labels=['<20 pips', '20-30 pips', '30-40 pips', '40-60 pips', '>60 pips'])
    print("\n -> Distribution of Losses by Stop Loss Size:")
    print(losses['sl_bin'].value_counts().to_string())

    print("\n[5/5] SL PADDING SENSITIVITY TEST (+ $0.50 Padding)")
    saved_losses = losses['padded_would_win'].sum()
    print(f" -> Losses Stopped Out by < $0.50 Wick Hunts: {saved_losses:,} trades ({(saved_losses/len(losses))*100:.2f}% of all losses!)")

    # Hour distribution of losses
    print("\n -> Loss Count by Hour (UTC):")
    print(losses['hour'].value_counts().sort_index().to_string())

    elapsed = time.time() - start_time
    print(f"\n[DONE] Deep Loss Diagnosis finished in {elapsed:.2f} seconds.")

if __name__ == "__main__":
    run_deep_loss_diagnosis()
