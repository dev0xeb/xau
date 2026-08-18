"""
Empirical Backtest Engine: Volume Profile + Order Flow (Absorption & Delta) on GBP/USD (GU).

Evaluates:
1. VP + Order Flow Institutional Absorption on GBP/USD (M5).
2. Model 2 (M5 Scalp Hybrid) on GBP/USD (M5).
Using real MetaTrader 5 100,000 M5 bars.
"""

import sys
from pathlib import Path
from datetime import datetime, date
import pandas as pd
import numpy as np
import time

from volume_profile_engine import VolumeProfileEngine

def run_gu_vp_orderflow_benchmark():
    proc_gu_path = Path("data/processed/gu_5m_5y.parquet")
    if not proc_gu_path.exists():
        print("[ERROR] GBP/USD 5m dataset missing!")
        return

    print("================================================================================")
    print("  GBP/USD (GU) VOLUME PROFILE + ORDER FLOW & MODEL 2 EMPIRICAL BENCHMARK")
    print("================================================================================")

    start_time = time.time()

    print("[1/4] Loading Real MetaTrader 5 GBP/USD (GU) M5 Data...")
    df_5m = pd.read_parquet(proc_gu_path)
    df_5m['timestamp'] = pd.to_datetime(df_5m['timestamp'])

    df_5m = df_5m.sort_values('timestamp').reset_index(drop=True)
    df_5m['hour'] = df_5m['timestamp'].dt.hour
    df_5m['minute'] = df_5m['timestamp'].dt.minute
    df_5m['date'] = df_5m['timestamp'].dt.date

    n = len(df_5m)
    print(f" -> Total Loaded GU Candles: {n:,} 5-minute bars from {df_5m['timestamp'].min()} to {df_5m['timestamp'].max()}.")

    closes_5m = df_5m['close'].values
    opens_5m = df_5m['open'].values
    highs_5m = df_5m['high'].values
    lows_5m = df_5m['low'].values
    volumes_5m = df_5m['volume'].values
    hours_5m = df_5m['hour'].values
    minutes_5m = df_5m['minute'].values
    dates_5m = df_5m['date'].values
    timestamps = df_5m['timestamp'].values

    pip_size = 0.0001  # 1 pip on GBP/USD = 0.0001
    spread = 0.00010    # 1.0 pip spread on GU

    # 1. Compute Volume Delta & Volume SMA
    ranges = highs_5m - lows_5m
    ranges[ranges == 0] = 0.00001

    buy_vol_ratio = (closes_5m - lows_5m) / ranges
    sell_vol_ratio = (highs_5m - closes_5m) / ranges

    buy_volume = volumes_5m * buy_vol_ratio
    sell_volume = volumes_5m * sell_vol_ratio
    volume_delta = buy_volume - sell_volume

    df_5m['vol_sma20'] = df_5m['volume'].rolling(20).mean().bfill()
    vol_sma20s = df_5m['vol_sma20'].values

    # Pre-compute H1 EMAs for Macro Trend
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

    vp_engine = VolumeProfileEngine(bin_size=0.0002, va_pct=0.70)

    print("[2/4] Computing Volume Profiles on GBP/USD...")
    unique_dates = sorted(df_5m['date'].unique())
    asian_vp_map = {}

    for d in unique_dates:
        mask = (dates_5m == d) & (hours_5m >= 0) & (hours_5m < 6)
        if np.sum(mask) >= 12:
            d_highs = highs_5m[mask]
            d_lows = lows_5m[mask]
            d_closes = closes_5m[mask]
            profile = vp_engine.compute_profile(d_highs, d_lows, d_closes)
            if profile is not None:
                asian_vp_map[d] = profile

    # SIMULATION 1: VP + Order Flow Absorption on GBP/USD
    print("[3/4] Running VP + Order Flow Simulation on GBP/USD...")
    trades_vp_of = []
    last_trade_bar = -10

    for i in range(50, n - 100):
        hour = hours_5m[i]
        d = dates_5m[i]

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

        asian_vp = asian_vp_map.get(d, None)
        if asian_vp is None:
            continue

        poc = asian_vp['poc']
        vah = asian_vp['vah']
        val = asian_vp['val']
        hvns = asian_vp['hvn_prices']

        c_close = closes_5m[idx]
        c_open = opens_5m[idx]
        c_high = highs_5m[idx]
        c_low = lows_5m[idx]
        c_vol = volumes_5m[idx]
        c_v_sma = vol_sma20s[idx]

        c_range = c_high - c_low
        if c_range == 0: continue
        c_body = abs(c_close - c_open)
        body_ratio = c_body / c_range

        at_val = abs(c_low - val) <= 0.0008 or abs(c_close - val) <= 0.0008
        at_poc = abs(c_low - poc) <= 0.0008 or abs(c_high - poc) <= 0.0008
        at_hvn = np.any(np.abs(hvns - c_close) <= 0.0005)

        vp_location_buy = at_val or at_poc or at_hvn

        at_vah = abs(c_high - vah) <= 0.0008 or abs(c_close - vah) <= 0.0008
        vp_location_sell = at_vah or at_poc or at_hvn

        if not (vp_location_buy or vp_location_sell):
            continue

        is_high_vol = c_vol >= 1.3 * c_v_sma
        is_small_body = body_ratio <= 0.45
        is_bull_pin = (c_close - c_low) >= 0.50 * c_range
        is_bear_pin = (c_high - c_close) >= 0.50 * c_range

        bull_absorption = is_high_vol and is_small_body and is_bull_pin
        bear_absorption = is_high_vol and is_small_body and is_bear_pin

        buy_signal = h1_bullish and vp_location_buy and bull_absorption
        sell_signal = h1_bearish and vp_location_sell and bear_absorption

        if not (buy_signal or sell_signal):
            continue

        recent_3_low = np.min(lows_5m[idx-2 : idx+1])
        recent_3_high = np.max(highs_5m[idx-2 : idx+1])

        if buy_signal:
            direction = "BUY"
            entry_price = c_close + spread
            sl_price = recent_3_low - 0.0005
            sl_pips = np.clip((entry_price - sl_price) / pip_size, 10.0, 40.0)
            sl_price = entry_price - (sl_pips * pip_size)

            tp1_price = entry_price + (sl_pips * pip_size * 1.0)
            tp2_price = entry_price + (sl_pips * pip_size * 2.0)
            tp3_price = entry_price + (sl_pips * pip_size * 3.0)

        else:
            direction = "SELL"
            entry_price = c_close
            sl_price = recent_3_high + 0.0005
            sl_pips = np.clip((sl_price - entry_price) / pip_size, 10.0, 40.0)
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
        trades_vp_of.append({
            'timestamp': timestamps[i],
            'direction': direction,
            'entry_price': entry_price,
            'sl_pips': sl_pips,
            'pnl': setup_pnl,
            'is_win': setup_pnl > 0
        })

        last_trade_bar = exit_bar

    # SIMULATION 2: Model 2 (M5 Scalp Hybrid) on GBP/USD
    print("[4/4] Running Model 2 (M5 Scalp Hybrid) Simulation on GBP/USD...")
    trades_model2 = []
    last_trade_bar = -10

    for i in range(50, n - 100):
        hour = hours_5m[i]
        d = dates_5m[i]

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

        # FVG threshold for GU: 1.5 pips (0.00015)
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

        recent_3_low = np.min(lows_5m[idx-2 : idx+1])
        recent_3_high = np.max(highs_5m[idx-2 : idx+1])

        if buy_signal:
            direction = "BUY"
            entry_price = high_t2 + spread
            sl_price = recent_3_low - 0.0005
            sl_pips = np.clip((entry_price - sl_price) / pip_size, 10.0, 40.0)
            sl_price = entry_price - (sl_pips * pip_size)

            tp1_price = entry_price + (sl_pips * pip_size * 1.0)
            tp2_price = entry_price + (sl_pips * pip_size * 2.0)
            tp3_price = entry_price + (sl_pips * pip_size * 3.0)

        else:
            direction = "SELL"
            entry_price = low_t2
            sl_price = recent_3_high + 0.0005
            sl_pips = np.clip((sl_price - entry_price) / pip_size, 10.0, 40.0)
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
        trades_model2.append({
            'timestamp': timestamps[i],
            'direction': direction,
            'entry_price': entry_price,
            'sl_pips': sl_pips,
            'pnl': setup_pnl,
            'is_win': setup_pnl > 0
        })

        last_trade_bar = exit_bar

    df_vp_of = pd.DataFrame(trades_vp_of)
    df_m2 = pd.DataFrame(trades_model2)

    def print_gu_metrics(df, label):
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
        print(f" PERFORMANCE METRICS ON GBP/USD (GU): {label}")
        print(f"================================================================================")
        print(f" -> Total Trades Executed:   {tot:,} trades (~{(tot/(tot_w*5)):.1f} trades / day)")
        print(f" -> Win Rate (%):            {wr:.2f}% ({len(wins):,} W / {len(losses):,} L)")
        print(f" -> Net Cumulative Profit:   +${net:,.2f} ({(net/10000.0)*100.0:.2f}% Return)")
        print(f" -> Profit Factor (PF):      {pf:.2f}")
        print(f" -> Maximum Drawdown (%):    {dd:.2f}%")
        print(f" -> Weekly Consistency Rate: {wcons:.2f}% ({prof_w}/{tot_w} Weeks Profitable)")
        print(f" -> Average SL Size:        {df['sl_pips'].mean():.1f} pips")
        print(f"--------------------------------------------------------------------------------")

    print_gu_metrics(df_vp_of, "1. VP + ORDER FLOW ABSORPTION ON GBP/USD (GU)")
    print_gu_metrics(df_m2, "2. MODEL 2 (M5 SCALP HYBRID) ON GBP/USD (GU)")

    elapsed = time.time() - start_time
    print(f"\n[DONE] GBP/USD benchmark finished in {elapsed:.2f} seconds.")

if __name__ == "__main__":
    run_gu_vp_orderflow_benchmark()
