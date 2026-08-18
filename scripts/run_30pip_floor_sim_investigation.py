"""
3-Month & 5-Year Simulation and Stop Loss Forensic Analysis
WITH 30-PIP HARD MINIMUM STOP LOSS FLOOR (sl_pips = np.clip(raw_sl_pips, 30.0, 80.0))
"""

import sys
from pathlib import Path
import pandas as pd
import numpy as np

def run_30pip_floor_analysis():
    proc_5m_path = Path("data/processed/xau_5m_5y.parquet")
    if not proc_5m_path.exists():
        print("[ERROR] 5m dataset missing!")
        return

    df_5m = pd.read_parquet(proc_5m_path)
    df_5m['timestamp'] = pd.to_datetime(df_5m['timestamp'])
    df_5m = df_5m.sort_values('timestamp').reset_index(drop=True)
    df_5m['date'] = df_5m['timestamp'].dt.date
    df_5m['hour'] = df_5m['timestamp'].dt.hour
    df_5m['day_name'] = df_5m['timestamp'].dt.day_name()
    df_5m['year'] = df_5m['timestamp'].dt.year.astype(str)

    n = len(df_5m)

    closes_5m = df_5m['close'].values
    highs_5m = df_5m['high'].values
    lows_5m = df_5m['low'].values
    volumes_5m = df_5m['volume'].values
    hours_5m = df_5m['hour'].values
    timestamps = df_5m['timestamp'].values
    dates_5m = df_5m['date'].values
    day_names_5m = df_5m['day_name'].values
    years_5m = df_5m['year'].values

    # H1 Trend
    df_h1 = df_5m.resample('1h', on='timestamp').agg({'open':'first','high':'max','low':'min','close':'last'}).dropna().reset_index()
    df_h1['ema21'] = df_h1['close'].ewm(span=21, adjust=False).mean()
    df_h1['ema50'] = df_h1['close'].ewm(span=50, adjust=False).mean()
    df_5m['h1_time'] = df_5m['timestamp'].dt.floor('1h')
    df_5m = pd.merge_asof(df_5m, df_h1[['timestamp','ema21','ema50','close']].rename(columns={'timestamp':'h1_time','ema21':'h1_ema21','ema50':'h1_ema50','close':'h1_close'}), on='h1_time', direction='backward')
    h1_closes, h1_ema21s, h1_ema50s = df_5m['h1_close'].values, df_5m['h1_ema21'].values, df_5m['h1_ema50'].values

    # M15 Trend
    df_m15 = df_5m.resample('15min', on='timestamp').agg({'open':'first','high':'max','low':'min','close':'last'}).dropna().reset_index()
    df_m15['ema21'] = df_m15['close'].ewm(span=21, adjust=False).mean()
    df_5m['m15_time'] = df_5m['timestamp'].dt.floor('15min')
    df_5m = pd.merge_asof(df_5m, df_m15[['timestamp','ema21','close']].rename(columns={'timestamp':'m15_time','ema21':'m15_ema21','close':'m15_close'}), on='m15_time', direction='backward')
    m15_closes, m15_ema21s = df_5m['m15_close'].values, df_5m['m15_ema21'].values

    df_5m['m5_ema21'] = df_5m['close'].ewm(span=21, adjust=False).mean()
    m5_ema21s = df_5m['m5_ema21'].values

    # Daily VWAP
    tp_vol = (highs_5m + lows_5m + closes_5m) / 3.0 * volumes_5m
    df_5m['tp_vol'] = tp_vol
    df_5m['cum_tp_vol'] = df_5m.groupby('date')['tp_vol'].cumsum()
    df_5m['cum_vol'] = df_5m.groupby('date')['volume'].cumsum()
    cum_vol_vals = df_5m['cum_vol'].values
    cum_vol_vals[cum_vol_vals == 0] = 1.0
    daily_vwap = df_5m['cum_tp_vol'].values / cum_vol_vals

    pip_size, spread, fixed_risk = 0.10, 0.15, 100.0

    def run_sim(mode="baseline", start_d=None, min_sl=30.0):
        trades = []
        last_trade_bar = -10

        for i in range(50, n - 100):
            if start_d and dates_5m[i] < start_d: continue
            hour = hours_5m[i]
            if not (6 <= hour < 20): continue
            if i <= last_trade_bar + 1: continue

            idx = i - 1
            if mode == "baseline":
                h1_bull = (h1_closes[idx] > h1_ema21s[idx]) and (h1_ema21s[idx] > h1_ema50s[idx])
                h1_bear = (h1_closes[idx] < h1_ema21s[idx]) and (h1_ema21s[idx] < h1_ema50s[idx])
            else:
                h1_bull = (h1_closes[idx] > h1_ema21s[idx]) or (m15_closes[idx] > m15_ema21s[idx])
                h1_bear = (h1_closes[idx] < h1_ema21s[idx]) or (m15_closes[idx] < m15_ema21s[idx])

            if not (h1_bull or h1_bear): continue

            low_t, high_t = lows_5m[idx], highs_5m[idx]
            low_t2, high_t2 = lows_5m[idx - 2], highs_5m[idx - 2]

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
                raw_sl_pips = (entry_price - sl_price) / pip_size
                sl_pips = np.clip(raw_sl_pips, min_sl, 80.0)  # HARD FLOOR APPLIED
                sl_price = entry_price - (sl_pips * pip_size)

                tp1_price = entry_price + (sl_pips * pip_size * 1.0)
                tp2_price = entry_price + (sl_pips * pip_size * 2.0)
                tp3_price = entry_price + (sl_pips * pip_size * 3.0)
            else:
                entry_price = low_t2
                sl_price = recent_3_high + 0.50
                raw_sl_pips = (sl_price - entry_price) / pip_size
                sl_pips = np.clip(raw_sl_pips, min_sl, 80.0)  # HARD FLOOR APPLIED
                sl_price = entry_price + (sl_pips * pip_size)

                tp1_price = entry_price - (sl_pips * pip_size * 1.0)
                tp2_price = entry_price - (sl_pips * pip_size * 2.0)
                tp3_price = entry_price - (sl_pips * pip_size * 3.0)

            ticket_risk = fixed_risk / 3.0
            t1_hit, t2_hit, t3_hit = False, False, False
            exit_bar = i + 36

            t1_pnl, t2_pnl, t3_pnl = -ticket_risk, -ticket_risk, -ticket_risk

            for k in range(i, min(i + 36, n)):
                bar_h, bar_l = highs_5m[k], lows_5m[k]

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
                else:
                    if bar_h >= sl_price:
                        exit_bar = k
                        break
                    if not t1_hit and bar_l <= tp1_price:
                        t1_hit = True
                        t1_pnl = ticket_risk * 1.0
                    if t1_hit and not t2_hit and bar_l <= tp2_price:
                        t2_hit = True
                        t2_pnl = ticket_risk * 2.0
                    if t2_hit and not t3_hit and bar_l <= tp3_price:
                        t3_hit = True
                        t3_pnl = ticket_risk * 3.0
                        exit_bar = k
                        break

            setup_pnl = t1_pnl + t2_pnl + t3_pnl
            is_sl = not (t1_hit or t2_hit or t3_hit)

            trades.append({
                'date': str(dates_5m[i]),
                'year': years_5m[i],
                'timestamp': str(timestamps[i]),
                'entry_time': str(timestamps[i])[11:16],
                'hour': hour,
                'day_name': day_names_5m[i],
                'direction': direction,
                'entry_price': entry_price,
                'sl_price': sl_price,
                'sl_pips': sl_pips,
                't1_hit': t1_hit,
                't2_hit': t2_hit,
                't3_hit': t3_hit,
                'is_sl': is_sl,
                'pnl': setup_pnl
            })
            last_trade_bar = exit_bar

        return pd.DataFrame(trades)

    end_d = df_5m['date'].max()
    d_3m = end_d - pd.Timedelta(days=90)

    # 3-Month Prop Engine Test with 30-pip Floor
    df_3m_prop = run_sim("relaxed_vwap", start_d=d_3m, min_sl=30.0)

    print("\n================================================================================")
    print(" 1. 3-MONTH PROP ENGINE SIMULATION WITH 30-PIP SL FLOOR")
    print("================================================================================")
    tot_3m = len(df_3m_prop)
    win_3m = df_3m_prop[df_3m_prop['t3_hit'] | df_3m_prop['t2_hit']]
    sl_3m = df_3m_prop[df_3m_prop['is_sl']]
    t1_3m = df_3m_prop[df_3m_prop['t1_hit'] & (~df_3m_prop['t2_hit'])]

    print(f"Total Trades: {tot_3m}")
    print(f"Full / Partial Wins: {len(win_3m)} ({len(win_3m)/tot_3m*100.0:.2f}%)")
    print(f"TP1 Only Hits (-$33.33): {len(t1_3m)}")
    print(f"Full Stop Losses (-$100.00): {len(sl_3m)} ({len(sl_3m)/tot_3m*100.0:.2f}%)")
    print(f"3-Month Net PnL ($100 Risk): ${df_3m_prop['pnl'].sum():+.2f}")

    print("\n--- 3-Month Stop Loss Log (With 30-Pip Floor) ---")
    if sl_3m.empty:
        print("ZERO STOP LOSSES HIT! 100% WIN RATE IN 3 MONTHS!")
    else:
        for idx, r in sl_3m.iterrows():
            print(f"SL Trade: {r['date']} @ {r['entry_time']} UTC | {r['direction']} @ ${r['entry_price']:.2f} | SL: ${r['sl_price']:.2f} ({r['sl_pips']:.1f} pips)")

    # 5-Year Prop Engine Test with 30-pip Floor vs 15-pip Floor
    df_5y_prop_30 = run_sim("relaxed_vwap", start_d=None, min_sl=30.0)
    df_5y_prop_15 = run_sim("relaxed_vwap", start_d=None, min_sl=15.0)

    # 5-Year Personal Engine Test with 30-pip Floor vs 15-pip Floor
    df_5y_base_30 = run_sim("baseline", start_d=None, min_sl=30.0)
    df_5y_base_15 = run_sim("baseline", start_d=None, min_sl=15.0)

    print("\n================================================================================")
    print(" 2. 5-YEAR IMPACT OF 30-PIP SL FLOOR COMPARISON")
    print("================================================================================")

    def print_comp(df15, df30, name):
        tot15, tot30 = len(df15), len(df30)
        sl15, sl30 = df15['is_sl'].sum(), df30['is_sl'].sum()
        win15 = (df15['t3_hit'] | df15['t2_hit']).sum()
        win30 = (df30['t3_hit'] | df30['t2_hit']).sum()
        pnl15, pnl30 = df15['pnl'].sum(), df30['pnl'].sum()

        print(f"\n--- {name} ---")
        print(f"Metric                       | 15-Pip Min Floor | 30-Pip Min Floor | Change")
        print(f"-----------------------------------------------------------------------------")
        print(f"Total Trades                 | {tot15:16d} | {tot30:16d} | {tot30-tot15:+d}")
        print(f"Winning Trades (TP2/TP3)     | {win15:16d} | {win30:16d} | {win30-win15:+d}")
        print(f"Full Stop Losses (-$100)     | {sl15:16d} | {sl30:16d} | {sl30-sl15:+d} ({((sl30-sl15)/sl15*100.0):+.1f}%)")
        print(f"Win Rate (%)                 | {win15/tot15*100.0:15.2f}% | {win30/tot30*100.0:15.2f}% | {(win30/tot30*100.0)-(win15/tot15*100.0):+.2f}%")
        print(f"Loss Rate (%)                | {sl15/tot15*100.0:15.2f}% | {sl30/tot30*100.0:15.2f}% | {(sl30/tot30*100.0)-(sl15/tot15*100.0):+.2f}%")
        print(f"Total 5-Year Net PnL ($)     | ${pnl15:15,.2f} | ${pnl30:15,.2f} | ${pnl30-pnl15:+,.2f}")

    print_comp(df_5y_prop_15, df_5y_prop_30, "PROP FIRM ENGINE (RELAXED VWAP RECLAIM)")
    print_comp(df_5y_base_15, df_5y_base_30, "PERSONAL ACCOUNT ENGINE (BASELINE MODEL 2)")

if __name__ == "__main__":
    run_30pip_floor_analysis()
