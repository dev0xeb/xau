"""
Train & Serialize Random Forest Quality Gate ML Model for Model 2 (M5 Execution / M15 Macro Trend)
---------------------------------------------------------------------------------------------------
Trains an 11-feature Random Forest Classifier on 5-Year XAU/USD data (2021-2026).
Saves serialized model to: models/saved_models/model2_fvg_rf_quality_gate.joblib
"""

import os
import sys
from pathlib import Path
import pandas as pd
import numpy as np
import joblib
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report, roc_auc_score, precision_score, recall_score

def train_and_save_m15_rf_gate():
    dataset_path = Path("data/processed/xau_5m_5y.parquet")
    if not dataset_path.exists():
        print(f"[ERROR] Dataset missing at: {dataset_path.resolve()}")
        return

    print(f"Loading 5-year XAU/USD 5M dataset: {dataset_path}...")
    df = pd.read_parquet(dataset_path)
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    df = df.sort_values('timestamp').reset_index(drop=True)

    df['date'] = df['timestamp'].dt.date
    df['year'] = df['timestamp'].dt.year
    df['hour'] = df['timestamp'].dt.hour

    n = len(df)
    closes = df['close'].values
    opens = df['open'].values
    highs = df['high'].values
    lows = df['low'].values
    volumes = df['volume'].values
    hours = df['hour'].values
    timestamps = df['timestamp'].values

    print(f"Dataset loaded: {n:,} 5-minute bars from {timestamps[0]} to {timestamps[-1]}.")

    # 👑 Resample M5 to M15 for exact M15 Macro Trend calculation
    print("Constructing M15 Macro Trend (EMA21 & EMA50 on M15 Timeframe)...")
    df_m15 = df.resample('15min', on='timestamp').agg({'open':'first','high':'max','low':'min','close':'last'}).dropna().reset_index()
    df_m15['m15_ema21'] = df_m15['close'].ewm(span=21, adjust=False).mean()
    df_m15['m15_ema50'] = df_m15['close'].ewm(span=50, adjust=False).mean()

    df['m15_time'] = df['timestamp'].dt.floor('15min')
    df = pd.merge_asof(
        df, 
        df_m15[['timestamp','m15_ema21','m15_ema50','close']].rename(columns={'timestamp':'m15_time','m15_ema21':'m15_ema21','m15_ema50':'m15_ema50','close':'m15_close'}), 
        on='m15_time', 
        direction='backward'
    )

    m15_closes = df['m15_close'].values
    m15_ema21s = df['m15_ema21'].values
    m15_ema50s = df['m15_ema50'].values

    # M5 EMA21
    df['m5_ema21'] = df['close'].ewm(span=21, adjust=False).mean()
    m5_ema21s = df['m5_ema21'].values

    # Daily VWAP
    tp_vol = (highs + lows + closes) / 3.0 * volumes
    df['tp_vol'] = tp_vol
    df['cum_tp_vol'] = df.groupby('date')['tp_vol'].cumsum()
    df['cum_vol'] = df.groupby('date')['volume'].cumsum()
    cum_vol_vals = df['cum_vol'].values
    cum_vol_vals[cum_vol_vals == 0] = 1.0
    daily_vwap = df['cum_tp_vol'].values / cum_vol_vals

    # Technical Indicators
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

    records = []
    last_trade_bar = -10

    print("Extracting setup candidate features and forward trade outcomes...")
    for i in range(50, n - 200):
        hour = hours[i]
        if not (6 <= hour < 17): continue
        if i <= last_trade_bar + 1: continue

        idx = i - 1
        m15_bull = (m15_closes[idx] > m15_ema21s[idx]) and (m15_ema21s[idx] > m15_ema50s[idx])
        m15_bear = (m15_closes[idx] < m15_ema21s[idx]) and (m15_ema21s[idx] < m15_ema50s[idx])
        if not (m15_bull or m15_bear): continue

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

        m5_close = closes[idx]
        base_buy  = m15_bull and bull_fvg and bull_sweep and (m5_close > m5_e21)
        base_sell = m15_bear and bear_fvg and bear_sweep and (m5_close < m5_e21)
        if not (base_buy or base_sell): continue

        direction = "BUY" if base_buy else "SELL"
        if direction == "BUY":
            entry_price = high_t2 + total_friction
            recent_3_low = np.min(lows[idx-2 : idx+1])
            sl_price = recent_3_low - 0.50
            sl_pips = np.clip((entry_price - sl_price) / pip_size, 15.0, 80.0)
            sl_price = entry_price - (sl_pips * pip_size)
            tp1_price = entry_price + (sl_pips * pip_size * 1.0)
        else:
            entry_price = low_t2 - total_friction
            recent_3_high = np.max(highs[idx-2 : idx+1])
            sl_price = recent_3_high + 0.50
            sl_pips = np.clip((sl_price - entry_price) / pip_size, 15.0, 80.0)
            sl_price = entry_price + (sl_pips * pip_size)
            tp1_price = entry_price - (sl_pips * pip_size * 1.0)

        # Forward Outcome Simulation: Did price hit TP1 before SL?
        outcome = 0
        for k in range(i, min(i + 200, n)):
            if direction == "BUY":
                if lows[k] <= sl_price:
                    outcome = 0
                    break
                if highs[k] >= tp1_price:
                    outcome = 1
                    break
            else:
                if highs[k] >= sl_price:
                    outcome = 0
                    break
                if lows[k] <= tp1_price:
                    outcome = 1
                    break

        # 11 Institutional Features
        fvg_size = bull_fvg_size if direction == "BUY" else bear_fvg_size
        sweep_depth = (m5_e21 - prior_5_low) / pip_size if direction == "BUY" else (prior_5_high - m5_e21) / pip_size
        vwap_dist = abs(entry_price - daily_vwap[idx]) / pip_size
        atr_ratio_val = atr5[idx] / (atr20[idx] + 1e-9)
        h1_spread_val = abs(m15_ema21s[idx] - m15_ema50s[idx]) / pip_size
        m5_slope_val = (m5_e21 - m5_ema21s[idx-3]) / pip_size
        body_ratio_val = abs(closes[idx] - opens[idx]) / (highs[idx] - lows[idx] + 1e-6)
        vol_ratio_val = volumes[idx] / (vol_sma20[idx] + 1e-9)
        
        swing_20_high = np.max(highs[idx-20 : idx])
        swing_20_low = np.min(lows[idx-20 : idx])
        dist_swing = (entry_price - swing_20_low) / pip_size if direction == "BUY" else (swing_20_high - entry_price) / pip_size

        records.append({
            'timestamp': timestamps[idx],
            'year': df['year'].iloc[idx],
            'f_fvg_size': fvg_size,
            'f_sweep_depth': sweep_depth,
            'f_vwap_dist': vwap_dist,
            'f_atr_ratio': atr_ratio_val,
            'f_h1_spread': h1_spread_val,
            'f_m5_slope': m5_slope_val,
            'f_body_ratio': body_ratio_val,
            'f_rsi_14': rsi14[idx],
            'f_vol_ratio': vol_ratio_val,
            'f_dist_swing': dist_swing,
            'f_hour_utc': hours[idx],
            'target': outcome
        })

        last_trade_bar = i

    df_setups = pd.DataFrame(records)
    print(f"Extracted {len(df_setups):,} setup candidates across 5 years.")
    print(f"Target Distribution: Wins (TP1 Hit): {df_setups['target'].sum():,} ({df_setups['target'].mean()*100:.1f}%) | Losses: {(1-df_setups['target']).sum():,}")

    feature_cols = [
        'f_fvg_size', 'f_sweep_depth', 'f_vwap_dist', 'f_atr_ratio',
        'f_h1_spread', 'f_m5_slope', 'f_body_ratio', 'f_rsi_14',
        'f_vol_ratio', 'f_dist_swing', 'f_hour_utc'
    ]

    # Out-of-Sample Temporal Split: Train on 2021-2024, Test on 2025-2026
    train_mask = df_setups['year'] <= 2024
    test_mask = df_setups['year'] >= 2025

    X_train, y_train = df_setups.loc[train_mask, feature_cols], df_setups.loc[train_mask, 'target']
    X_test, y_test   = df_setups.loc[test_mask, feature_cols], df_setups.loc[test_mask, 'target']

    print(f"Train samples (2021-2024): {len(X_train):,} | Test samples (2025-2026): {len(X_test):,}")

    rf = RandomForestClassifier(
        n_estimators=100,
        max_depth=5,
        min_samples_leaf=10,
        class_weight='balanced',
        random_state=42
    )

    rf.fit(X_train, y_train)

    # Predictions & Probabilities on Test Set
    test_probs = rf.predict_proba(X_test)[:, 1]
    auc_score = roc_auc_score(y_test, test_probs)

    print("=========================================================================================")
    print(" RANDOM FOREST MODEL PERFORMANCE ON OUT-OF-SAMPLE TEST SET (2025-2026)")
    print("=========================================================================================")
    print(f" Out-of-Sample ROC-AUC Score: {auc_score:.4f}")

    # Threshold Analysis @ 0.58
    high_qual_mask = test_probs >= 0.58
    if np.sum(high_qual_mask) > 0:
        prec_at_58 = precision_score(y_test[high_qual_mask], np.ones(np.sum(high_qual_mask)))
        print(f" Precision @ 58% Threshold (Win Rate of Passed Setups): {prec_at_58*100:.1f}%")
        print(f" Passed Setups Count: {np.sum(high_qual_mask)} / {len(X_test)}")
    else:
        print(" No setups reached 58% threshold on test set.")

    # Feature Importance Analysis
    print("\n FEATURE IMPORTANCE RANKING:")
    importances = pd.Series(rf.feature_importances_, index=feature_cols).sort_values(ascending=False)
    for col, imp in importances.items():
        print(f"   - {col:15s}: {imp*100:5.2f}%")

    # Serialize & Save Model
    save_dir = Path("models/saved_models")
    save_dir.mkdir(parents=True, exist_ok=True)
    model_save_path = save_dir / "model2_fvg_rf_quality_gate.joblib"

    joblib.dump(rf, model_save_path)
    print(f"\n[SUCCESS] Retrained ML model serialized & saved to: {model_save_path.resolve()}")

if __name__ == "__main__":
    train_and_save_m15_rf_gate()
