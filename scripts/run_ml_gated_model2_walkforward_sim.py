"""
Walk-Forward Machine Learning Probability Gate Backtest for Model 2 (M5 Scalp Hybrid).
Uses 3-Fold Expanding Window Out-of-Sample Training (2021-2026).
Strict closed-candle feature indexing at iloc[-2].
"""

import sys
from pathlib import Path
import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestClassifier

def run_ml_walkforward_sim():
    proc_5m_path = Path("data/processed/xau_5m_5y.parquet")
    if not proc_5m_path.exists():
        print("[ERROR] 5m dataset missing!")
        return

    df_5m = pd.read_parquet(proc_5m_path)
    df_5m['timestamp'] = pd.to_datetime(df_5m['timestamp'])
    df_5m = df_5m.sort_values('timestamp').reset_index(drop=True)

    df_5m['date'] = df_5m['timestamp'].dt.date
    df_5m['year'] = df_5m['timestamp'].dt.year
    df_5m['hour'] = df_5m['timestamp'].dt.hour
    df_5m['day_name'] = df_5m['timestamp'].dt.day_name()

    n = len(df_5m)

    closes_5m = df_5m['close'].values
    opens_5m = df_5m['open'].values
    highs_5m = df_5m['high'].values
    lows_5m = df_5m['low'].values
    volumes_5m = df_5m['volume'].values
    hours_5m = df_5m['hour'].values
    years_5m = df_5m['year'].values
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

    # ATR Features
    tr = np.maximum(highs_5m - lows_5m, np.maximum(np.abs(highs_5m - np.roll(closes_5m, 1)), np.abs(lows_5m - np.roll(closes_5m, 1))))
    tr[0] = highs_5m[0] - lows_5m[0]
    atr5 = pd.Series(tr).ewm(span=5, adjust=False).mean().values
    atr20 = pd.Series(tr).ewm(span=20, adjust=False).mean().values

    # RSI Feature
    delta = pd.Series(closes_5m).diff()
    gain = (delta.where(delta > 0, 0)).ewm(alpha=1/14, adjust=False).mean()
    loss = (-delta.where(delta < 0, 0)).ewm(alpha=1/14, adjust=False).mean()
    rs = gain / (loss + 1e-9)
    rsi14 = (100 - (100 / (1 + rs))).values

    # Volume Ratio Feature
    vol_sma20 = pd.Series(volumes_5m).rolling(20, min_periods=1).mean().values

    pip_size, spread, fixed_risk = 0.10, 0.15, 100.0

    def collect_dataset(mode="baseline"):
        records = []
        last_trade_bar = -10

        for i in range(50, n):
            hour = hours_5m[i]
            if not (6 <= hour < 17): continue  # LATE NY CUTOFF APPLIED
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

            bull_fvg_size = (low_t - high_t2) / pip_size
            bear_fvg_size = (low_t2 - high_t) / pip_size

            bull_fvg = bull_fvg_size >= 1.5
            bear_fvg = bear_fvg_size >= 1.5

            prior_5_low = np.min(lows_5m[idx-5 : idx])
            prior_5_high = np.max(highs_5m[idx-5 : idx])
            m5_e21 = m5_ema21s[idx]

            bull_sweep = prior_5_low <= m5_e21
            bear_sweep = prior_5_high >= m5_e21

            m5_close = closes_5m[idx]
            m5_open = opens_5m[idx]
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
            is_win = (t2_hit or t3_hit)
            is_sl = not (t1_hit or t2_hit or t3_hit)

            # Feature Calculation at iloc[-2]
            fvg_size = bull_fvg_size if direction == "BUY" else bear_fvg_size
            sweep_depth = (m5_e21 - prior_5_low) / pip_size if direction == "BUY" else (prior_5_high - m5_e21) / pip_size
            vwap_dist = abs(entry_price - c_vwap) / pip_size
            atr_ratio = atr5[idx] / (atr20[idx] + 1e-9)
            h1_spread = abs(h1_ema21s[idx] - h1_ema50s[idx]) / pip_size
            m5_slope = (m5_e21 - m5_ema21s[idx-3]) / pip_size
            body_ratio = abs(m5_close - m5_open) / (m5_high - m5_low + 1e-6)
            rsi_val = rsi14[idx]
            vol_ratio = volumes_5m[idx] / (vol_sma20[idx] + 1e-9)
            hour_val = hours_5m[idx]

            swing_20_high = np.max(highs_5m[idx-20 : idx])
            swing_20_low = np.min(lows_5m[idx-20 : idx])
            dist_swing = (entry_price - swing_20_low) / pip_size if direction == "BUY" else (swing_20_high - entry_price) / pip_size

            records.append({
                'bar_idx': i,
                'year': years_5m[i],
                'date': str(dates_5m[i]),
                'direction': direction,
                'entry_price': entry_price,
                'sl_pips': sl_pips,
                'pnl': setup_pnl,
                'is_win': int(is_win),
                'is_sl': int(is_sl),
                # 10 Closed Candle ML Features
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

    df_prop = collect_dataset("relaxed_vwap")
    df_base = collect_dataset("baseline")

    feature_cols = ['f_fvg_size', 'f_sweep_depth', 'f_vwap_dist', 'f_atr_ratio', 
                    'f_h1_spread', 'f_m5_slope', 'f_body_ratio', 'f_rsi_14', 
                    'f_vol_ratio', 'f_dist_swing', 'f_hour_utc']

    def run_walk_forward_eval(df, name):
        print(f"\n================================================================================")
        print(f" WALK-FORWARD ML PROBABILITY GATE BENCHMARK FOR: {name}")
        print(f" Dataset: {len(df)} Candidate Signals across 5 Years (2021-2026)")
        print(f" Target: TP2/TP3 Win (1) vs SL/TP1 (0)")
        print(f"================================================================================")

        # 3-Fold Expanding Walk Forward
        # Fold 1: Train 2021-2022 -> Predict 2023
        # Fold 2: Train 2021-2023 -> Predict 2024
        # Fold 3: Train 2021-2024 -> Predict 2025-2026

        df = df.copy()
        df['ml_proba'] = np.nan

        folds = [
            (range(2021, 2023), [2023]),
            (range(2021, 2024), [2024]),
            (range(2021, 2025), [2025, 2026])
        ]

        feature_importances = np.zeros(len(feature_cols))

        for train_years, test_years in folds:
            train_mask = df['year'].isin(train_years)
            test_mask = df['year'].isin(test_years)

            X_train, y_train = df.loc[train_mask, feature_cols], df.loc[train_mask, 'is_win']
            X_test = df.loc[test_mask, feature_cols]

            clf = RandomForestClassifier(n_estimators=100, max_depth=4, min_samples_leaf=20, random_state=42)
            clf.fit(X_train, y_train)

            probas = clf.predict_proba(X_test)[:, 1]
            df.loc[test_mask, 'ml_proba'] = probas
            feature_importances += clf.feature_importances_ / len(folds)

        # Filter to Out-of-Sample Period (2023-2026)
        df_oos = df.dropna(subset=['ml_proba']).copy()

        # Evaluate Performance across thresholds
        thresholds = [0.0, 0.50, 0.55, 0.60, 0.65]

        print(f"\nOUT-OF-SAMPLE (2023 - 2026) THRESHOLD COMPARISON ({len(df_oos)} total candidate signals):")
        print(f"{'Gate Threshold':16s} | {'Trades':6s} | {'Win Rate':8s} | {'Stop Losses':11s} | {'Net PnL ($)':12s} | {'Profit Factor':13s} | {'Max DD (%)':10s}")
        print(f"---------------------------------------------------------------------------------------------------------")

        for th in thresholds:
            sub = df_oos[df_oos['ml_proba'] >= th]
            tot_trades = len(sub)
            if tot_trades == 0: continue

            wins = sub[sub['is_win'] == 1]
            sls = sub[sub['is_sl'] == 1]
            win_rate = len(wins) / tot_trades * 100.0
            sl_count = len(sls)
            tot_pnl = sub['pnl'].sum()

            gross_win = sub[sub['pnl'] > 0]['pnl'].sum()
            gross_loss = abs(sub[sub['pnl'] < 0]['pnl'].sum())
            pf = gross_win / (gross_loss + 1e-9)

            cum_pnl = sub['pnl'].cumsum()
            peak = np.maximum.accumulate(cum_pnl)
            dd = (cum_pnl - peak) / 10000.0 * 100.0  # Base capital 10k
            max_dd = abs(dd.min()) if len(dd) > 0 else 0.0

            label = "BASELINE (No ML)" if th == 0.0 else f"ML Proba >= {th*100:.0f}%"
            print(f"{label:16s} | {tot_trades:6d} | {win_rate:7.2f}% | {sl_count:11d} | ${tot_pnl:+11.2f} | {pf:13.2f} | -{max_dd:9.2f}%")

        print(f"\nTOP 5 MARKET MICROSTRUCTURE FEATURE IMPORTANCES:")
        feat_imp_df = pd.DataFrame({'feature': feature_cols, 'importance': feature_importances}).sort_values('importance', ascending=False)
        for idx, r in feat_imp_df.head(5).iterrows():
            print(f" - {r['feature']:16s}: {r['importance']*100:.2f}% weight")

    run_walk_forward_eval(df_prop, "PROP FIRM ENGINE (RELAXED VWAP RECLAIM)")
    run_walk_forward_eval(df_base, "PERSONAL ACCOUNT ENGINE (BASELINE MODEL 2)")

if __name__ == "__main__":
    run_ml_walkforward_sim()
