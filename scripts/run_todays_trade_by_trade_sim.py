"""
Trade-by-Trade Simulation on Today's (Latest Date) Data for:
1. Baseline Model 2 (Personal Account Engine)
2. Relaxed VWAP Reclaim Engine (Prop Firm Engine)
"""

import sys
from pathlib import Path
import pandas as pd
import numpy as np

def run_todays_sim():
    proc_5m_path = Path("data/processed/xau_5m_5y.parquet")
    if not proc_5m_path.exists():
        print("[ERROR] 5m dataset missing!")
        return

    df_5m = pd.read_parquet(proc_5m_path)
    df_5m['timestamp'] = pd.to_datetime(df_5m['timestamp'])
    df_5m = df_5m.sort_values('timestamp').reset_index(drop=True)
    df_5m['date'] = df_5m['timestamp'].dt.date

    latest_date = df_5m['date'].max()
    print(f"[INFO] Latest available trading date in dataset: {latest_date}")

    df_5m['hour'] = df_5m['timestamp'].dt.hour
    n = len(df_5m)

    closes_5m = df_5m['close'].values
    highs_5m = df_5m['high'].values
    lows_5m = df_5m['low'].values
    volumes_5m = df_5m['volume'].values
    hours_5m = df_5m['hour'].values
    timestamps = df_5m['timestamp'].values
    dates_5m = df_5m['date'].values

    # H1 Trend
    df_h1 = df_5m.resample('1h', on='timestamp').agg({
        'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last'
    }).dropna().reset_index()
    df_h1['ema21'] = df_h1['close'].ewm(span=21, adjust=False).mean()
    df_h1['ema50'] = df_h1['close'].ewm(span=50, adjust=False).mean()
    df_5m['h1_time'] = df_5m['timestamp'].dt.floor('1h')
    df_5m = pd.merge_asof(
        df_5m,
        df_h1[['timestamp', 'ema21', 'ema50', 'close']].rename(columns={'timestamp': 'h1_time', 'ema21': 'h1_ema21', 'ema50': 'h1_ema50', 'close': 'h1_close'}),
        on='h1_time', direction='backward'
    )
    h1_closes = df_5m['h1_close'].values
    h1_ema21s = df_5m['h1_ema21'].values
    h1_ema50s = df_5m['h1_ema50'].values

    # M15 Trend
    df_m15 = df_5m.resample('15min', on='timestamp').agg({
        'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last'
    }).dropna().reset_index()
    df_m15['ema21'] = df_m15['close'].ewm(span=21, adjust=False).mean()
    df_5m['m15_time'] = df_5m['timestamp'].dt.floor('15min')
    df_5m = pd.merge_asof(
        df_5m,
        df_m15[['timestamp', 'ema21', 'close']].rename(columns={'timestamp': 'm15_time', 'ema21': 'm15_ema21', 'close': 'm15_close'}),
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
    fixed_risk = 100.0

    def run_sim_for_date(target_date, mode="baseline"):
        trades = []
        last_trade_bar = -10

        for i in range(50, n - 100):
            if dates_5m[i] != target_date: continue
            hour = hours_5m[i]
            if not (6 <= hour < 20): continue
            if i <= last_trade_bar + 1: continue

            idx = i - 1

            if mode == "baseline":
                h1_bull = (h1_closes[idx] > h1_ema21s[idx]) and (h1_ema21s[idx] > h1_ema50s[idx])
                h1_bear = (h1_closes[idx] < h1_ema21s[idx]) and (h1_ema21s[idx] < h1_ema50s[idx])
            else:  # relaxed_vwap
                h1_bull = (h1_closes[idx] > h1_ema21s[idx]) or (m15_closes[idx] > m15_ema21s[idx])
                h1_bear = (h1_closes[idx] < h1_ema21s[idx]) or (m15_closes[idx] < m15_ema21s[idx])

            if not (h1_bull or h1_bear): continue

            low_t = lows_5m[idx]
            high_t = highs_5m[idx]
            low_t2 = lows_5m[idx - 2]
            high_t2 = highs_5m[idx - 2]

            bull_fvg = (low_t - high_t2) / pip_size >= 1.5
            bear_fvg = (low_t2 - high_t) / pip_size >= 1.5

            prior_5_low = np.min(lows_5m[idx-5 : idx])
            prior_5_high = np.max(highs_5m[idx-5 : idx])
            m5_e21 = m5_ema21s[idx]

            bull_sweep = prior_5_low <= m5_e21
            bear_sweep = prior_5_high >= m5_e21

            m5_close = closes_5m[idx]
            m5_low = lows_5m[idx]
            m5_high = highs_5m[idx]

            bull_confirm = m5_close > m5_e21
            bear_confirm = m5_close < m5_e21

            base_buy = h1_bull and bull_fvg and bull_sweep and bull_confirm
            base_sell = h1_bear and bear_fvg and bear_sweep and bear_confirm

            if not (base_buy or base_sell): continue

            c_vwap = daily_vwap[idx]
            direction = "BUY" if base_buy else "SELL"

            if mode == "relaxed_vwap":
                valid_reclaim = (m5_low <= c_vwap + 0.20 and m5_close > c_vwap) if direction == "BUY" else (m5_high >= c_vwap - 0.20 and m5_close < c_vwap)
                if not valid_reclaim: continue

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

            ticket_risk = fixed_risk / 3.0
            t1_hit, t2_hit, t3_hit = False, False, False
            exit_bar = i + 36

            t1_pnl, t2_pnl, t3_pnl = -ticket_risk, -ticket_risk, -ticket_risk

            for k in range(i, min(i + 36, n)):
                bar_h = highs_5m[k]
                bar_l = lows_5m[k]

                if direction == "BUY":
                    if bar_l <= sl_price:
                        exit_bar = k
                        break
                    if not t1_hit and bar_h >= tp1_price:
                        t1_hit = True
                        t1_pnl = ticket_risk * 1.0
                    if t1_hit and not t2_hit and bar_h >= tp2_price:
                        t2_hit = True
                        t2_pnl = ticket_risk * 2.0
                    if t2_hit and not t3_hit and bar_h >= tp3_price:
                        t3_hit = True
                        t3_pnl = ticket_risk * 3.0
                        exit_bar = k
                        break
                else:  # SELL
                    if bar_h >= sl_price:
                        exit_bar = k
                        break
                    if not t1_hit and bar_l <= tp1_price:
                        t1_hit = True
                        t1_pnl = ticket_risk * 1.0
                    if t1_hit and not t2_hit and bar_l <= tp3_price:
                        t2_hit = True
                        t2_pnl = ticket_risk * 2.0
                    if t2_hit and not t3_hit and bar_l <= tp3_price:
                        t3_hit = True
                        t3_pnl = ticket_risk * 3.0
                        exit_bar = k
                        break

            setup_pnl = t1_pnl + t2_pnl + t3_pnl
            trades.append({
                'entry_time': str(timestamps[i])[11:16],
                'exit_time': str(timestamps[exit_bar])[11:16],
                'direction': direction,
                'entry_price': entry_price,
                'sl_price': sl_price,
                'sl_pips': sl_pips,
                'tp1_price': tp1_price,
                'tp2_price': tp2_price,
                'tp3_price': tp3_price,
                't1_hit': t1_hit,
                't2_hit': t2_hit,
                't3_hit': t3_hit,
                'pnl': setup_pnl
            })
            last_trade_bar = exit_bar

        return trades

    trades_base = run_sim_for_date(latest_date, "baseline")
    trades_vwap = run_sim_for_date(latest_date, "relaxed_vwap")

    print(f"\n================================================================================")
    print(f"  TRADE-BY-TRADE SIMULATION FOR: {latest_date}")
    print(f"================================================================================")

    def print_trades(trades, name):
        print(f"\n--- {name} ({len(trades)} Trades) ---")
        if not trades:
            print("No trades triggered during session.")
            return
        tot_pnl = 0.0
        for idx, t in enumerate(trades, 1):
            tot_pnl += t['pnl']
            res_str = "SL HIT (-$100.00)"
            if t['t3_hit']:
                res_str = "FULL WIN (TP1 + TP2 + TP3 -> +$200.00)"
            elif t['t2_hit']:
                res_str = "PARTIAL WIN (TP1 + TP2 -> +$0.00 Net)"
            elif t['t1_hit']:
                res_str = "TP1 HIT ONLY (TP1 -> -$33.33 Net)"

            print(f"Trade #{idx}: [{t['entry_time']} UTC] {t['direction']} @ ${t['entry_price']:.2f}")
            print(f"   SL: ${t['sl_price']:.2f} ({t['sl_pips']:.1f} pips) | TP1: ${t['tp1_price']:.2f} | TP2: ${t['tp2_price']:.2f} | TP3: ${t['tp3_price']:.2f}")
            print(f"   Exit Time: [{t['exit_time']} UTC] | Outcome: {res_str} | PnL: ${t['pnl']:+.2f}")
            print("   -------------------------------------------------------------------------")
        print(f"TOTAL DAILY SESSION PnL: ${tot_pnl:+.2f}")

    print_trades(trades_base, "BASELINE MODEL 2 (PERSONAL ACCOUNT ENGINE)")
    print_trades(trades_vwap, "RELAXED VWAP RECLAIM ENGINE (PROP FIRM ENGINE)")

if __name__ == "__main__":
    run_todays_sim()
