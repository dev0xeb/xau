"""
Empirical Benchmark of ML Quality Gate Probability Thresholds for August 1 - 17 ($100 Deposit)
Evaluates Random Forest ML Probability Scores: No ML vs >= 50% vs >= 55% vs >= 60% vs >= 65%
"""

import sys
from pathlib import Path
import pandas as pd
import numpy as np
import joblib

def run_ml_threshold_study():
    proc_5m_path = Path("data/processed/xau_5m_5y.parquet")
    model_path = Path("src/models/model2_rf_gate.joblib")

    if not proc_5m_path.exists() or not model_path.exists():
        print("[ERROR] Parquet data or ML model missing!")
        return

    rf_model = joblib.load(model_path)
    df = pd.read_parquet(proc_5m_path)
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    df = df.sort_values('timestamp').reset_index(drop=True)

    df_sub = df[(df['timestamp'] >= pd.to_datetime('2026-08-01', utc=True)) & (df['timestamp'] <= pd.to_datetime('2026-08-17 23:59:59', utc=True))].reset_index(drop=True)
    df_sub['date'] = df_sub['timestamp'].dt.date
    df_sub['hour'] = df_sub['timestamp'].dt.hour

    # H1 Trend
    df_h1 = df_sub.resample('1h', on='timestamp').agg({'open':'first','high':'max','low':'min','close':'last'}).dropna().reset_index()
    df_h1['h1_ema21'] = df_h1['close'].ewm(span=21, adjust=False).mean()
    df_h1['h1_ema50'] = df_h1['close'].ewm(span=50, adjust=False).mean()
    df_sub['h1_time'] = df_sub['timestamp'].dt.floor('1h')
    df_sub = pd.merge_asof(df_sub, df_h1[['timestamp','h1_ema21','h1_ema50','close']].rename(columns={'timestamp':'h1_time','close':'h1_close'}), on='h1_time', direction='backward')
    
    h1_closes = df_sub['h1_close'].values
    h1_ema21s = df_sub['h1_ema21'].values
    h1_ema50s = df_sub['h1_ema50'].values

    df_sub['m5_ema21'] = df_sub['close'].ewm(span=21, adjust=False).mean()
    m5_ema21s = df_sub['m5_ema21'].values

    # Daily VWAP
    tp_vol = (df_sub['high'].values + df_sub['low'].values + df_sub['close'].values) / 3.0 * df_sub['volume'].values
    df_sub['tp_vol'] = tp_vol
    df_sub['cum_tp_vol'] = df_sub.groupby('date')['tp_vol'].cumsum()
    df_sub['cum_vol'] = df_sub.groupby('date')['volume'].cumsum()
    cum_vol_vals = df_sub['cum_vol'].values
    cum_vol_vals[cum_vol_vals == 0] = 1.0
    daily_vwaps = df_sub['cum_tp_vol'].values / cum_vol_vals

    closes = df_sub['close'].values
    highs = df_sub['high'].values
    lows = df_sub['low'].values
    hours = df_sub['hour'].values
    volumes = df_sub['volume'].values
    n = len(df_sub)

    # Feature calculations for ML
    delta = df_sub['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / (loss + 1e-9)
    rsi14 = (100 - (100 / (1 + rs))).fillna(50.0).values

    tr1 = df_sub['high'] - df_sub['low']
    tr2 = (df_sub['high'] - df_sub['close'].shift(1)).abs()
    tr3 = (df_sub['low'] - df_sub['close'].shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr5 = tr.rolling(5).mean().fillna(1.0).values
    atr20 = tr.rolling(20).mean().fillna(1.0).values

    vol_sma20 = df_sub['volume'].rolling(20).mean().fillna(100.0).values

    pip_size = 0.10
    total_friction = (2.5 + 1.0) * pip_size

    def simulate_ml_threshold(ml_threshold=0.0):
        balance = 100.0
        last_trade_bar = -10
        records = []
        scores = []

        for i in range(50, n):
            hour = hours[i]
            if not (6 <= hour < 17): continue
            if i <= last_trade_bar + 1: continue

            idx = i - 1
            htf_bull = (h1_closes[idx] > h1_ema21s[idx]) and (h1_ema21s[idx] > h1_ema50s[idx])
            htf_bear = (h1_closes[idx] < h1_ema21s[idx]) and (h1_ema21s[idx] < h1_ema50s[idx])
            if not (htf_bull or htf_bear): continue

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
            c_vwap = daily_vwaps[idx]
            m5_close = closes[idx]

            base_buy = htf_bull and bull_fvg and bull_sweep and (m5_close > m5_e21)
            base_sell = htf_bear and bear_fvg and bear_sweep and (m5_close < m5_e21)
            if not (base_buy or base_sell): continue

            direction = "BUY" if base_buy else "SELL"
            recent_3_low = np.min(lows[idx-2 : idx+1])
            recent_3_high = np.max(highs[idx-2 : idx+1])

            if direction == "BUY":
                entry = high_t2 + total_friction
                sl_dist = np.clip((entry - (recent_3_low - 0.50)) / pip_size, 15.0, 80.0) * pip_size
                sl = entry - sl_dist
                fvg_sz = bull_fvg_size
                sweep_dp = (m5_e21 - prior_5_low) / pip_size
            else:
                entry = low_t2 - total_friction
                sl_dist = np.clip(((recent_3_high + 0.50) - entry) / pip_size, 15.0, 80.0) * pip_size
                sl = entry + sl_dist
                fvg_sz = bear_fvg_size
                sweep_dp = (prior_5_high - m5_e21) / pip_size

            # ML Score Evaluation
            if ml_threshold > 0.0:
                vwap_d = abs(entry - c_vwap) / pip_size
                atr_r = atr5[idx] / (atr20[idx] + 1e-9)
                h1_sp = abs(h1_ema21s[idx] - h1_ema50s[idx]) / pip_size
                m5_slp = (m5_e21 - m5_ema21s[idx-3]) / pip_size
                body_r = abs(closes[idx] - df_sub['open'].values[idx]) / (highs[idx] - lows[idx] + 1e-6)
                vol_r = volumes[idx] / (vol_sma20[idx] + 1e-9)
                
                sw_20_h = np.max(highs[idx-20:idx])
                sw_20_l = np.min(lows[idx-20:idx])
                dist_sw = (entry - sw_20_l) / pip_size if direction == "BUY" else (sw_20_h - entry) / pip_size

                feat_df = pd.DataFrame([{
                    'f_fvg_size': fvg_sz,
                    'f_sweep_depth': sweep_dp,
                    'f_vwap_dist': vwap_d,
                    'f_atr_ratio': atr_r,
                    'f_h1_spread': h1_sp,
                    'f_m5_slope': m5_slp,
                    'f_body_ratio': body_r,
                    'f_rsi_14': rsi14[idx],
                    'f_vol_ratio': vol_r,
                    'f_dist_swing': dist_sw,
                    'f_hour_utc': hour
                }])

                proba = rf_model.predict_proba(feat_df)[0, 1]
                scores.append(proba)
                if proba < ml_threshold: continue

            tp1 = entry + (sl_dist * 1.0) if direction == "BUY" else entry - (sl_dist * 1.0)
            tp2 = entry + (sl_dist * 2.0) if direction == "BUY" else entry - (sl_dist * 2.0)
            tp3 = entry + (sl_dist * 3.0) if direction == "BUY" else entry - (sl_dist * 3.0)

            ticket_risk = 1.0 / 3.0
            t1_hit, t2_hit, t3_hit = False, False, False
            t1_pnl, t2_pnl, t3_pnl = -ticket_risk, -ticket_risk, -ticket_risk

            for k in range(i, min(i + 36, n)):
                bh, bl = highs[k], lows[k]
                if direction == "BUY":
                    if not t1_hit:
                        if bl <= sl: break
                        elif bh >= tp1: t1_hit = True; t1_pnl = ticket_risk * 1.0
                    if t1_hit and not t2_hit:
                        if bl <= sl: break
                        elif bh >= tp2: t2_hit = True; t2_pnl = ticket_risk * 2.0
                    if t2_hit and not t3_hit:
                        if bl <= sl: break
                        elif bh >= tp3: t3_hit = True; t3_pnl = ticket_risk * 3.0; last_bar = k; break
                else:
                    if not t1_hit:
                        if bh >= sl: break
                        elif bl <= tp1: t1_hit = True; t1_pnl = ticket_risk * 1.0
                    if t1_hit and not t2_hit:
                        if bh >= sl: break
                        elif bl <= tp2: t2_hit = True; t2_pnl = ticket_risk * 2.0
                    if t2_hit and not t3_hit:
                        if bh >= sl: break
                        elif bl <= tp3: t3_hit = True; t3_pnl = ticket_risk * 3.0; last_bar = k; break

            setup_pnl = t1_pnl + t2_pnl + t3_pnl
            balance += setup_pnl
            records.append({'pnl': setup_pnl, 't1': int(t1_hit)})

        df_r = pd.DataFrame(records)
        setups = len(df_r)
        wins = df_r['t1'].sum() if setups > 0 else 0
        wr = (wins / setups * 100.0) if setups > 0 else 0
        pnl = balance - 100.0
        avg_score = np.mean(scores) * 100.0 if len(scores) > 0 else 0.0

        return setups, balance, pnl, wr, avg_score

    print("=========================================================================================")
    print(" AUGUST 1 - 17 ML QUALITY GATE PROBABILITY THRESHOLD MATRIX ($100 DEPOSIT)")
    print("=========================================================================================\n")

    for th, lbl in [(0.0, "No ML Gate (Rule-Based Only)"), (0.50, "ML Gate >= 50.0% (Default Baseline)"), (0.55, "ML Gate >= 55.0%"), (0.60, "ML Gate >= 60.0% (High Conviction)"), (0.65, "ML Gate >= 65.0% (Ultra Conviction)")]:
        st, bal, pnl, wr, avg_s = simulate_ml_threshold(th)
        print(f"--- {lbl} ---")
        print(f"   - Final Balance  : ${bal:.2f} USD (+{pnl:.2f}% Return)")
        print(f"   - Total Setups   : {st} Setups")
        print(f"   - Setup Win Rate : {wr:.2f}%")
        if th > 0:
            print(f"   - Avg ML Score   : {avg_s:.1f}%\n")
        else:
            print(f"   - Avg ML Score   : N/A\n")

if __name__ == "__main__":
    run_ml_threshold_study()
