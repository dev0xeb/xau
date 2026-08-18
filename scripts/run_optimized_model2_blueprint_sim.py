"""
Master Optimized Model 2 Strategy Engine Benchmark (5-Year Horizon)
Features:
1. Dynamic Structural SL: 15.0 to 80.0 pips
2. Late NY Session Cutoff: 06:00 to 17:00 UTC (No new entries after 17:00 UTC)
3. Evaluates both Prop Firm Engine & Personal Account Engine
"""

import sys
from pathlib import Path
import pandas as pd
import numpy as np

def run_optimized_simulation():
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

    def run_sim(mode="baseline", max_hour=17):
        trades = []
        last_trade_bar = -10

        for i in range(50, n - 100):
            hour = hours_5m[i]
            if not (6 <= hour < max_hour): continue  # LATE NY CUTOFF APPLIED
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
                sl_pips = np.clip((entry_price - sl_price) / pip_size, 15.0, 80.0)  # ORIGINAL 15-PIP FLOOR PRESERVED
                sl_price = entry_price - (sl_pips * pip_size)

                tp1_price = entry_price + (sl_pips * pip_size * 1.0)
                tp2_price = entry_price + (sl_pips * pip_size * 2.0)
                tp3_price = entry_price + (sl_pips * pip_size * 3.0)
            else:
                entry_price = low_t2
                sl_price = recent_3_high + 0.50
                sl_pips = np.clip((sl_price - entry_price) / pip_size, 15.0, 80.0)  # ORIGINAL 15-PIP FLOOR PRESERVED
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
                    if t1_hit and not t2_hit and bar_l <= tp3_price:
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
                'entry_time': str(timestamps[i])[11:16],
                'hour': hour,
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

    # Run original (06:00 - 20:00 UTC) vs optimized (06:00 - 17:00 UTC)
    df_prop_orig = run_sim("relaxed_vwap", max_hour=20)
    df_prop_opt = run_sim("relaxed_vwap", max_hour=17)

    df_base_orig = run_sim("baseline", max_hour=20)
    df_base_opt = run_sim("baseline", max_hour=17)

    print("\n================================================================================")
    print(" MASTER 5-YEAR BENCHMARK: ORIGINAL (20:00 CUTOFF) VS OPTIMIZED (17:00 CUTOFF)")
    print("================================================================================")

    def print_comparison(dforig, dfopt, name):
        tot_o, tot_n = len(dforig), len(dfopt)
        sl_o, sl_n = dforig['is_sl'].sum(), dfopt['is_sl'].sum()
        win_o = (dforig['t3_hit'] | dforig['t2_hit']).sum()
        win_n = (dfopt['t3_hit'] | dfopt['t2_hit']).sum()
        pnl_o, pnl_n = dforig['pnl'].sum(), dfopt['pnl'].sum()

        wins_val_o = (dforig[dforig['pnl'] > 0]['pnl']).sum()
        loss_val_o = abs(dforig[dforig['pnl'] < 0]['pnl']).sum()
        pf_o = wins_val_o / loss_val_o if loss_val_o > 0 else 0

        wins_val_n = (dfopt[dfopt['pnl'] > 0]['pnl']).sum()
        loss_val_n = abs(dfopt[dfopt['pnl'] < 0]['pnl']).sum()
        pf_n = wins_val_n / loss_val_n if loss_val_n > 0 else 0

        # Equity Curve Peak Drawdown
        def get_max_dd(df_in):
            df_in['cum'] = df_in['pnl'].cumsum()
            df_in['peak'] = df_in['cum'].cummax()
            df_in['dd'] = df_in['peak'] - df_in['cum']
            return df_in['dd'].max() / 10000.0 * 100.0

        dd_o = get_max_dd(dforig)
        dd_n = get_max_dd(dfopt)

        print(f"\n--- {name} ---")
        print(f"Metric                       | Original (06-20 UTC) | Optimized (06-17 UTC)| Improvement")
        print(f"-------------------------------------------------------------------------------------")
        print(f"Total Trades                 | {tot_o:20d} | {tot_n:20d} | {tot_n-tot_o:+d}")
        print(f"Winning Trades (TP2/TP3)     | {win_o:20d} | {win_n:20d} | {win_n-win_o:+d}")
        print(f"Full Stop Losses (-$100)     | {sl_o:20d} | {sl_n:20d} | {sl_n-sl_o:+d} ({((sl_n-sl_o)/sl_o*100.0):+.1f}%)")
        print(f"Win Rate (%)                 | {win_o/tot_o*100.0:19.2f}% | {win_n/tot_n*100.0:19.2f}% | {(win_n/tot_n*100.0)-(win_o/tot_o*100.0):+.2f}%")
        print(f"Loss Rate (%)                | {sl_o/tot_o*100.0:19.2f}% | {sl_n/tot_n*100.0:19.2f}% | {(sl_n/tot_n*100.0)-(sl_o/tot_o*100.0):+.2f}%")
        print(f"Profit Factor                | {pf_o:20.2f} | {pf_n:20.2f} | {pf_n-pf_o:+.2f}")
        print(f"Max Peak-to-Trough DD (%)    | {dd_o:19.2f}% | {dd_n:19.2f}% | {dd_n-dd_o:+.2f}%")
        print(f"Total 5-Year Net PnL ($)     | ${pnl_o:19,.2f} | ${pnl_n:19,.2f} | ${pnl_n-pnl_o:+,.2f}")

    print_comparison(df_prop_orig, df_prop_opt, "PROP FIRM ENGINE (RELAXED VWAP RECLAIM)")
    print_comparison(df_base_orig, df_base_opt, "PERSONAL ACCOUNT ENGINE (BASELINE MODEL 2)")

if __name__ == "__main__":
    run_optimized_simulation()
