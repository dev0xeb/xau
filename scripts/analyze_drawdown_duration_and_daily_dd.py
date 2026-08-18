"""
Analyze drawdown duration, max daily drawdown, max session drawdown, and max cumulative peak-to-trough drawdown 
for Model 2 (Personal Account Engine & Prop Firm Engine) over 4 years (2023 - 2026).
"""

import sys
from pathlib import Path
import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestClassifier

def analyze_drawdown_details():
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
                'pnl': setup_pnl,
                'is_win': int(is_win),
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
    train_mask_p = df_pers['year'] < 2026
    test_mask_p = df_pers['year'] == 2026
    clf_p = RandomForestClassifier(n_estimators=100, max_depth=4, min_samples_leaf=20, random_state=42)
    clf_p.fit(df_pers.loc[train_mask_p, feature_cols], df_pers.loc[train_mask_p, 'is_win'])
    df_pers.loc[test_mask_p, 'ml_proba'] = clf_p.predict_proba(df_pers.loc[test_mask_p, feature_cols])[:, 1]
    df_pers_ml = df_pers[test_mask_p & (df_pers['ml_proba'] >= 0.50)].copy()

    # Process Prop Engine
    df_prop = collect_engine_dataset(is_prop=True)
    train_mask_pr = df_prop['year'] < 2026
    test_mask_pr = df_prop['year'] == 2026
    clf_pr = RandomForestClassifier(n_estimators=100, max_depth=4, min_samples_leaf=20, random_state=42)
    clf_pr.fit(df_prop.loc[train_mask_pr, feature_cols], df_prop.loc[train_mask_pr, 'is_win'])
    df_prop.loc[test_mask_pr, 'ml_proba'] = clf_pr.predict_proba(df_prop.loc[test_mask_pr, feature_cols])[:, 1]
    df_prop_ml = df_prop[test_mask_pr & (df_prop['ml_proba'] >= 0.50)].copy()

    def calc_drawdown_metrics(df_engine, engine_name):
        initial_capital = 10000.0
        df_engine = df_engine.sort_values('timestamp').reset_index(drop=True)
        df_engine['cum_pnl'] = df_engine['pnl'].cumsum()
        df_engine['equity'] = initial_capital + df_engine['cum_pnl']
        df_engine['peak'] = df_engine['equity'].cummax()
        df_engine['dd_dollars'] = df_engine['peak'] - df_engine['equity']
        df_engine['dd_pct'] = (df_engine['dd_dollars'] / df_engine['peak']) * 100.0

        max_cum_dd_pct = df_engine['dd_pct'].max()
        max_cum_dd_dollars = df_engine['dd_dollars'].max()

        # Daily Drawdown
        daily_pnl = df_engine.groupby('date')['pnl'].sum()
        worst_day_pnl = daily_pnl.min()
        worst_day_pct = (worst_day_pnl / initial_capital) * 100.0
        worst_day_date = daily_pnl.idxmin()

        # Single Trade Max Loss
        worst_trade_pnl = df_engine['pnl'].min()

        print(f"\n=========================================================================================")
        print(f" DRAWDOWN STRUCTURE AUDIT: {engine_name.upper()}")
        print(f"=========================================================================================")
        print(f" 1. CUMULATIVE PEAK-TO-TROUGH MAX DRAWDOWN (OVER ENTIRE TIME HORIZON):")
        print(f"    - Max Percentage Drop : -{max_cum_dd_pct:.2f}%")
        print(f"    - Max Dollar Amount    : -${max_cum_dd_dollars:,.2f}")
        print(f" 2. WORST SINGLE-DAY DRAWDOWN (WORST 24-HOUR TRADING DAY):")
        print(f"    - Worst Day PnL        : -${abs(worst_day_pnl):,.2f} (-{abs(worst_day_pct):.2f}%)")
        print(f"    - Date of Worst Day    : {worst_day_date}")
        print(f" 3. WORST SINGLE-TRADE LOSS:")
        print(f"    - Max Single Trade Loss: -${abs(worst_trade_pnl):,.2f} (-1.0% Risk)")

    calc_drawdown_metrics(df_pers_ml, "Personal Account Engine")
    calc_drawdown_metrics(df_prop_ml, "Prop Firm Engine")

if __name__ == "__main__":
    analyze_drawdown_details()
