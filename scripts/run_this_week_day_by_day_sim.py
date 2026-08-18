"""
Day-by-Day Simulation of Personal Engine & Prop Firm Engine for Current Trading Week
(Evaluated under Real Exness Friction 3.5 Pips + Pessimistic Execution)
"""

import sys
from pathlib import Path
import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestClassifier

def run_this_week_simulation():
    proc_5m_path = Path("data/processed/xau_5m_5y.parquet")
    if not proc_5m_path.exists():
        print("[ERROR] 5m dataset missing!")
        return

    df = pd.read_parquet(proc_5m_path)
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    df = df.sort_values('timestamp').reset_index(drop=True)

    df['date'] = df['timestamp'].dt.date
    df['year'] = df['timestamp'].dt.year
    df['hour'] = df['timestamp'].dt.hour
    df['day_name'] = df['timestamp'].dt.day_name()

    n = len(df)

    closes = df['close'].values
    opens = df['open'].values
    highs = df['high'].values
    lows = df['low'].values
    volumes = df['volume'].values
    hours = df['hour'].values
    years = df['year'].values
    timestamps = df['timestamp'].values

    # H1 Trend
    df_h1 = df.resample('1h', on='timestamp').agg({'open':'first','high':'max','low':'min','close':'last'}).dropna().reset_index()
    df_h1['ema21'] = df_h1['close'].ewm(span=21, adjust=False).mean()
    df_h1['ema50'] = df_h1['close'].ewm(span=50, adjust=False).mean()
    df['h1_time'] = df['timestamp'].dt.floor('1h')
    df = pd.merge_asof(df, df_h1[['timestamp','ema21','ema50','close']].rename(columns={'timestamp':'h1_time','ema21':'h1_ema21','ema50':'h1_ema50','close':'h1_close'}), on='h1_time', direction='backward')
    
    h1_closes, h1_ema21s, h1_ema50s = df['h1_close'].values, df['h1_ema21'].values, df['h1_ema50'].values

    df['m5_ema21'] = df['close'].ewm(span=21, adjust=False).mean()
    m5_ema21s = df['m5_ema21'].values

    # Daily VWAP Calculation
    tp_vol = (highs + lows + closes) / 3.0 * volumes
    df['tp_vol'] = tp_vol
    df['cum_tp_vol'] = df.groupby('date')['tp_vol'].cumsum()
    df['cum_vol'] = df.groupby('date')['volume'].cumsum()
    cum_vol_vals = df['cum_vol'].values
    cum_vol_vals[cum_vol_vals == 0] = 1.0
    daily_vwap = df['cum_tp_vol'].values / cum_vol_vals

    tr = np.maximum(highs - lows, np.maximum(np.abs(highs - np.roll(closes, 1)), np.abs(lows - np.roll(closes, 1))))
    tr[0] = highs[0] - lows[0]
    atr5 = pd.Series(tr).ewm(span=5, adjust=False).mean().values
    atr20 = pd.Series(tr).ewm(span=20, adjust=False).mean().values

    delta = pd.Series(closes).diff()
    gain = (delta.where(delta > 0, 0)).ewm(alpha=1/14, adjust=False).mean()
    loss = (-delta.where(delta < 0, 0)).ewm(alpha=1/14, adjust=False).mean()
    rs = gain / (loss + 1e-9)
    rsi14 = (100 - (100 / (1 + rs))).values
    vol_sma20 = pd.Series(volumes).rolling(20, min_periods=1).mean().values

    pip_size = 0.10
    total_friction = (2.5 + 1.0) * pip_size

    def collect_engine_dataset(is_prop=False):
        records = []
        last_trade_bar = -10

        for i in range(50, n):
            hour = hours[i]
            if not (6 <= hour < 17): continue
            if i <= last_trade_bar + 1: continue

            idx = i - 1
            h1_bull = (h1_closes[idx] > h1_ema21s[idx]) and (h1_ema21s[idx] > h1_ema50s[idx])
            h1_bear = (h1_closes[idx] < h1_ema21s[idx]) and (h1_ema21s[idx] < h1_ema50s[idx])

            if not (h1_bull or h1_bear): continue

            low_t, high_t = lows[idx], highs[idx]
            low_t2, high_t2 = lows[idx - 2], highs[idx - 2]

            bull_fvg_size = (low_t - high_t2) / pip_size
            bear_fvg_size = (low_t2 - high_t) / pip_size

            bull_fvg = bull_fvg_size >= 1.5
            bear_fvg = bear_fvg_size >= 1.5

            prior_5_low = np.min(lows[idx-5 : idx])
            prior_5_high = np.max(highs[idx-5 : idx])
            m5_e21 = m5_ema21s[idx]

            bull_sweep = prior_5_low <= m5_e21
            bear_sweep = prior_5_high >= m5_e21

            c_vwap = daily_vwap[idx]
            m5_close = closes[idx]
            m5_open = opens[idx]
            m5_low = lows[idx]
            m5_high = highs[idx]

            if is_prop:
                vwap_bull = m5_close > c_vwap
                vwap_bear = m5_close < c_vwap
                base_buy = h1_bull and bull_fvg and bull_sweep and (m5_close > m5_e21) and vwap_bull
                base_sell = h1_bear and bear_fvg and bear_sweep and (m5_close < m5_e21) and vwap_bear
            else:
                base_buy = h1_bull and bull_fvg and bull_sweep and (m5_close > m5_e21)
                base_sell = h1_bear and bear_fvg and bear_sweep and (m5_close < m5_e21)

            if not (base_buy or base_sell): continue

            direction = "BUY" if base_buy else "SELL"

            recent_3_low = np.min(lows[idx-2 : idx+1])
            recent_3_high = np.max(highs[idx-2 : idx+1])

            if direction == "BUY":
                entry_price = high_t2 + total_friction
                sl_price = recent_3_low - 0.50
                sl_pips = np.clip((entry_price - sl_price) / pip_size, 15.0, 80.0)
                sl_price = entry_price - (sl_pips * pip_size)

                tp1_price = entry_price + (sl_pips * pip_size * 1.0)
                tp2_price = entry_price + (sl_pips * pip_size * 2.0)
                tp3_price = entry_price + (sl_pips * pip_size * 3.0)
            else:
                entry_price = low_t2 - total_friction
                sl_price = recent_3_high + 0.50
                sl_pips = np.clip((sl_price - entry_price) / pip_size, 15.0, 80.0)
                sl_price = entry_price + (sl_pips * pip_size)

                tp1_price = entry_price - (sl_pips * pip_size * 1.0)
                tp2_price = entry_price - (sl_pips * pip_size * 2.0)
                tp3_price = entry_price - (sl_pips * pip_size * 3.0)

            ticket_risk = 100.0 / 3.0
            t1_hit, t2_hit, t3_hit = False, False, False
            exit_bar = i + 36

            t1_pnl, t2_pnl, t3_pnl = -ticket_risk, -ticket_risk, -ticket_risk

            for k in range(i, min(i + 36, n)):
                bar_h, bar_l = highs[k], lows[k]

                if direction == "BUY":
                    sl_touched = (bar_l <= sl_price)
                    tp1_touched = (bar_h >= tp1_price)

                    if sl_touched:
                        exit_bar = k
                        break

                    if not t1_hit and tp1_touched:
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
                    sl_touched = (bar_h >= sl_price)
                    tp1_touched = (bar_l <= tp1_price)

                    if sl_touched:
                        exit_bar = k
                        break

                    if not t1_hit and tp1_touched:
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
            is_win = (t2_hit or t3_hit)

            fvg_size = bull_fvg_size if direction == "BUY" else bear_fvg_size
            sweep_depth = (m5_e21 - prior_5_low) / pip_size if direction == "BUY" else (prior_5_high - m5_e21) / pip_size
            vwap_dist = abs(entry_price - c_vwap) / pip_size
            atr_ratio = atr5[idx] / (atr20[idx] + 1e-9)
            h1_spread = abs(h1_ema21s[idx] - h1_ema50s[idx]) / pip_size
            m5_slope = (m5_e21 - m5_ema21s[idx-3]) / pip_size
            body_ratio = abs(m5_close - m5_open) / (m5_high - m5_low + 1e-6)
            rsi_val = rsi14[idx]
            vol_ratio = volumes[idx] / (vol_sma20[idx] + 1e-9)
            hour_val = hours[idx]

            swing_20_high = np.max(highs[idx-20 : idx])
            swing_20_low = np.min(lows[idx-20 : idx])
            dist_swing = (entry_price - swing_20_low) / pip_size if direction == "BUY" else (swing_20_high - entry_price) / pip_size

            records.append({
                'timestamp': timestamps[i],
                'year': years[i],
                'date': df['date'].iloc[i],
                'day_name': df['day_name'].iloc[i],
                'direction': direction,
                'entry_price': entry_price,
                'sl_price': sl_price,
                'tp1_price': tp1_price,
                'tp2_price': tp2_price,
                'tp3_price': tp3_price,
                'pnl': setup_pnl,
                'is_win': int(is_win),
                't1_hit': int(t1_hit),
                't2_hit': int(t2_hit),
                't3_hit': int(t3_hit),
                'f_fvg_size': fvg_size,
                'f_sweep_depth': sweep_depth,
                'f_vwap_dist': vwap_dist,
                'f_atr_ratio': atr_ratio,
                'f_h1_spread': h1_spread,
                'f_m5_slope': m5_slope,
                'f_body_ratio': body_ratio,
                'f_rsi_14': rsi_val,
                'f_vol_ratio': vol_ratio,
                'f_dist_swing': dist_swing,
                'f_hour_utc': hour_val
            })
            last_trade_bar = exit_bar

        return pd.DataFrame(records)

    feature_cols = ['f_fvg_size', 'f_sweep_depth', 'f_vwap_dist', 'f_atr_ratio', 
                    'f_h1_spread', 'f_m5_slope', 'f_body_ratio', 'f_rsi_14', 
                    'f_vol_ratio', 'f_dist_swing', 'f_hour_utc']

    # Process Personal Engine
    df_pers = collect_engine_dataset(is_prop=False)
    
    # Train ML on 2021-2025 data to predict 2026 (including this week!)
    train_mask_p = df_pers['year'] < 2026
    test_mask_p = df_pers['year'] == 2026
    clf_p = RandomForestClassifier(n_estimators=100, max_depth=4, min_samples_leaf=20, random_state=42)
    clf_p.fit(df_pers.loc[train_mask_p, feature_cols], df_pers.loc[train_mask_p, 'is_win'])
    df_pers.loc[test_mask_p, 'ml_proba'] = clf_p.predict_proba(df_pers.loc[test_mask_p, feature_cols])[:, 1]
    
    df_pers_2026 = df_pers[test_mask_p].copy()
    df_pers_ml = df_pers_2026[df_pers_2026['ml_proba'] >= 0.50].copy()

    # Process Prop Engine
    df_prop = collect_engine_dataset(is_prop=True)
    train_mask_pr = df_prop['year'] < 2026
    test_mask_pr = df_prop['year'] == 2026
    clf_pr = RandomForestClassifier(n_estimators=100, max_depth=4, min_samples_leaf=20, random_state=42)
    clf_pr.fit(df_prop.loc[train_mask_pr, feature_cols], df_prop.loc[train_mask_pr, 'is_win'])
    df_prop.loc[test_mask_pr, 'ml_proba'] = clf_pr.predict_proba(df_prop.loc[test_mask_pr, feature_cols])[:, 1]
    
    df_prop_2026 = df_prop[test_mask_pr].copy()
    df_prop_ml = df_prop_2026[df_prop_2026['ml_proba'] >= 0.50].copy()

    # Filter to most recent completed trading week in dataset
    max_date = df['date'].max()
    # Find Monday of that last week
    min_week_date = max_date - pd.Timedelta(days=max_date.weekday())

    print("=========================================================================================")
    print(f" LAST COMPLETED TRADING WEEK SIMULATION: MONDAY {min_week_date} TO FRIDAY {max_date}")
    print(" Evaluated under Real Exness Friction (3.5 Pips Friction + Pessimistic Sub-Bar Execution)")
    print("=========================================================================================\n")

    # Gold Price Action Summary for this week
    df_week = df[df['date'] >= min_week_date].copy()
    week_open = df_week['open'].iloc[0]
    week_high = df_week['high'].max()
    week_low = df_week['low'].min()
    week_close = df_week['close'].iloc[-1]
    week_range = week_high - week_low

    print(f" GOLD (XAU/USD) PRICE ACTION THIS WEEK:")
    print(f"   Week Open : ${week_open:,.2f}")
    print(f"   Week High : ${week_high:,.2f}")
    print(f"   Week Low  : ${week_low:,.2f}")
    print(f"   Current   : ${week_close:,.2f}")
    print(f"   Week Range: ${week_range:,.2f} ({week_range*10:.1f} pips)\n")

    # Filter trades for this week
    pers_week = df_pers_ml[df_pers_ml['date'] >= min_week_date].copy()
    prop_week = df_prop_ml[df_prop_ml['date'] >= min_week_date].copy()

    print("-----------------------------------------------------------------------------------------")
    print(" DAY-BY-DAY PNL COMPARISON TABLE THIS WEEK")
    print("-----------------------------------------------------------------------------------------")
    print("| Date | Day | Personal Engine Trades | Personal Daily PnL | Prop Engine Trades | Prop Daily PnL |")
    print("| :--- | :--- | :---: | :---: | :---: | :---: |")

    week_dates = sorted(df_week['date'].unique())

    tot_pers_pnl, tot_prop_pnl = 0.0, 0.0
    tot_pers_trades, tot_prop_trades = 0, 0

    for d in week_dates:
        p_sub = pers_week[pers_week['date'] == d]
        pr_sub = prop_week[prop_week['date'] == d]

        p_trades = len(p_sub)
        p_pnl = p_sub['pnl'].sum()

        pr_trades = len(pr_sub)
        pr_pnl = pr_sub['pnl'].sum()

        tot_pers_pnl += p_pnl
        tot_prop_pnl += pr_pnl
        tot_pers_trades += p_trades
        tot_prop_trades += pr_trades

        day_name = pd.to_datetime(d).strftime('%A')
        print(f"| {d} | {day_name:9s} | {p_trades:2d} Trades | ${p_pnl:+8.2f} | {pr_trades:2d} Trades | ${pr_pnl:+8.2f} |")

    print(f"| **TOTAL THIS WEEK** | **SUMMARY** | **{tot_pers_trades} Trades** | **${tot_pers_pnl:+,.2f}** | **{tot_prop_trades} Trades** | **${tot_prop_pnl:+,.2f}** |")

    print("\n-----------------------------------------------------------------------------------------")
    print(" INDIVIDUAL TRADE LOGS THIS WEEK (PERSONAL ENGINE - ML GATE 50%)")
    print("-----------------------------------------------------------------------------------------")
    if len(pers_week) == 0:
        print(" No trades executed this week.")
    else:
        for idx, row in pers_week.iterrows():
            ts = pd.to_datetime(row['timestamp']).strftime('%Y-%m-%d %H:%M UTC')
            outcome = "TP1+TP2+TP3 WINNER" if row['t3_hit'] else ("TP1+TP2 WINNER" if row['t2_hit'] else ("TP1 HIT" if row['t1_hit'] else "STOP LOSS HIT"))
            print(f" [{ts}] {row['direction']:4s} @ ${row['entry_price']:.2f} | SL: ${row['sl_price']:.2f} | TP1: ${row['tp1_price']:.2f} | Outcome: {outcome:18s} | PnL: ${row['pnl']:+6.2f}")

    print("\n-----------------------------------------------------------------------------------------")
    print(" INDIVIDUAL TRADE LOGS THIS WEEK (PROP FIRM ENGINE - ML GATE 50%)")
    print("-----------------------------------------------------------------------------------------")
    if len(prop_week) == 0:
        print(" No trades executed this week.")
    else:
        for idx, row in prop_week.iterrows():
            ts = pd.to_datetime(row['timestamp']).strftime('%Y-%m-%d %H:%M UTC')
            outcome = "TP1+TP2+TP3 WINNER" if row['t3_hit'] else ("TP1+TP2 WINNER" if row['t2_hit'] else ("TP1 HIT" if row['t1_hit'] else "STOP LOSS HIT"))
            print(f" [{ts}] {row['direction']:4s} @ ${row['entry_price']:.2f} | SL: ${row['sl_price']:.2f} | TP1: ${row['tp1_price']:.2f} | Outcome: {outcome:18s} | PnL: ${row['pnl']:+6.2f}")

if __name__ == "__main__":
    run_this_week_simulation()
