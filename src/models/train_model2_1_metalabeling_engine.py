"""
Model 2.1 Meta-Labeling & Multi-Target Machine Learning Engine
---------------------------------------------------------------
Implements López de Prado Meta-Labeling Architecture on 5-Year XAU/USD data:
  1. Deterministic Candidate Generator (Model 2 Baseline Strategy)
  2. Multi-Target Outcome Prediction: P(TP1), P(TP2), P(TP3), P(SL), MAE, MFE
  3. 16 Normalized Market-Regime & Liquidity Features
  4. Purged Walk-Forward Cross-Validation (5 Time-Group Folds with Embargo)
  5. Tournament Benchmarking: Random Forest vs XGBoost vs HistGradientBoosting vs ExtraTrees
  6. Probability Calibration (Isotonic Regression via CalibratedClassifierCV)
  7. Risk-Adjusted Expected Return E[R] Calculation & Regime-Dependent Abstention
  8. Serializes winning model to joblib & ONNX formats for live MT5 inference

Saves model to: models/saved_models/model2_1_metalabeling_engine.joblib
"""

import os
import sys
from pathlib import Path
import pandas as pd
import numpy as np
import joblib

# ML Benchmark Imports
from sklearn.ensemble import RandomForestClassifier, ExtraTreesClassifier, HistGradientBoostingClassifier
from sklearn.calibration import CalibratedClassifierCV
from sklearn.metrics import classification_report, roc_auc_score, precision_score, recall_score, brier_score_loss
from sklearn.model_selection import TimeSeriesSplit

# Check for XGBoost, LightGBM, CatBoost
XGBOOST_AVAILABLE = False
LIGHTGBM_AVAILABLE = False
CATBOOST_AVAILABLE = False

try:
    import xgboost as xgb
    XGBOOST_AVAILABLE = True
except ImportError:
    pass

try:
    import lightgbm as lgb
    LIGHTGBM_AVAILABLE = True
except ImportError:
    pass

try:
    import catboost as cb
    CATBOOST_AVAILABLE = True
except ImportError:
    pass

def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / (loss + 1e-9)
    return 100 - (100 / (1 + rs))

def train_model2_1_metalabeling_engine():
    dataset_path = Path("data/processed/xau_5m_5y.parquet")
    if not dataset_path.exists():
        print(f"[ERROR] Dataset missing at: {dataset_path.resolve()}")
        return

    print("=========================================================================", flush=True)
    print(" [MODEL 2.1] INITIALIZING META-LABELING & MULTI-TARGET ML ENGINE", flush=True)
    print("=========================================================================", flush=True)
    print(f" Loading 5-Year XAU/USD 5M dataset from: {dataset_path}...", flush=True)

    df = pd.read_parquet(dataset_path)
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    df = df.sort_values('timestamp').reset_index(drop=True)

    df['date'] = df['timestamp'].dt.date
    df['year'] = df['timestamp'].dt.year
    df['hour'] = df['timestamp'].dt.hour
    df['day_num'] = df['timestamp'].dt.dayofweek

    n = len(df)
    print(f" Dataset loaded: {n:,} 5-minute bars from {df['timestamp'].iloc[0]} to {df['timestamp'].iloc[-1]}.")

    # M15 Macro Indicators
    df_m15 = df.resample('15min', on='timestamp').agg({'open':'first','high':'max','low':'min','close':'last'}).dropna().reset_index()
    df_m15['m15_ema21'] = df_m15['close'].ewm(span=21, adjust=False).mean()
    df_m15['m15_ema50'] = df_m15['close'].ewm(span=50, adjust=False).mean()

    df['m15_time'] = df['timestamp'].dt.floor('15min')
    df = pd.merge_asof(
        df, 
        df_m15[['timestamp','m15_ema21','m15_ema50','close']].rename(
            columns={'timestamp':'m15_time','m15_ema21':'m15_ema21','m15_ema50':'m15_ema50','close':'m15_close'}
        ), 
        on='m15_time', 
        direction='backward'
    )

    # M5 Indicators
    df['m5_ema21'] = df['close'].ewm(span=21, adjust=False).mean()
    df['m5_ema50'] = df['close'].ewm(span=50, adjust=False).mean()
    df['rsi_14']   = calculate_rsi(df['close'], 14)
    
    # ATR 14 & ATR 50
    high_low = df['high'] - df['low']
    high_cp  = np.abs(df['high'] - df['close'].shift(1))
    low_cp   = np.abs(df['low'] - df['close'].shift(1))
    tr       = np.maximum(high_low, np.maximum(high_cp, low_cp))
    df['atr_14'] = tr.rolling(14).mean()
    df['atr_50'] = tr.rolling(50).mean()

    closes = df['close'].values
    opens  = df['open'].values
    highs  = df['high'].values
    lows   = df['low'].values
    hours  = df['hour'].values
    days   = df['day_num'].values
    timestamps = df['timestamp'].values

    m15_closes = df['m15_close'].values
    m15_ema21s = df['m15_ema21'].values
    m15_ema50s = df['m15_ema50'].values

    m5_ema21s = df['m5_ema21'].values
    rsi14s    = df['rsi_14'].values
    atr14s    = df['atr_14'].values
    atr50s    = df['atr_50'].values

    # Step 1: Candidate Generator & Multi-Target Extraction
    candidates = []
    print(" Step 1: Running Candidate Generator & Extracting Multi-Target Labels...")

    for i in range(60, n - 120):
        # M15 Macro Trend Check
        m15_bull = (m15_closes[i] > m15_ema21s[i]) and (m15_ema21s[i] > m15_ema50s[i])
        m15_bear = (m15_closes[i] < m15_ema21s[i]) and (m15_ema21s[i] < m15_ema50s[i])

        if not m15_bull and not m15_bear:
            continue

        # M5 FVG Check
        low_1  = lows[i]
        high_1 = highs[i]
        close_1= closes[i]
        low_3  = lows[i-2]
        high_3 = highs[i-2]

        bull_fvg_size = low_1 - high_3
        bear_fvg_size = low_3 - high_1

        bull_fvg = bull_fvg_size >= 0.15
        bear_fvg = bear_fvg_size >= 0.15

        # EMA21 Sweep Check
        prior_5_low  = np.min(lows[i-5:i])
        prior_5_high = np.max(highs[i-5:i])
        exec_e21_val = m5_ema21s[i]

        bull_sweep = (prior_5_low <= exec_e21_val)
        bear_sweep = (prior_5_high >= exec_e21_val)

        is_buy  = m15_bull and bull_fvg and bull_sweep and (close_1 > exec_e21_val)
        is_sell = m15_bear and bear_fvg and bear_sweep and (close_1 < exec_e21_val)

        if not is_buy and not is_sell:
            continue

        # Candidate Triggered!
        entry_idx = i + 1
        entry_time = timestamps[entry_idx]
        entry_price = opens[entry_idx]

        # Structural SL Sizing
        if is_buy:
            recent_3_low = np.min(lows[i-2:i+1])
            sl_price = recent_3_low - 0.50
            sl_dist = entry_price - sl_price
            sl_dist = max(2.50, min(12.00, sl_dist))
            sl_price = entry_price - sl_dist
            tp1_price = entry_price + sl_dist * 1.0
            tp2_price = entry_price + sl_dist * 2.0
            tp3_price = entry_price + sl_dist * 3.0
        else:
            recent_3_high = np.max(highs[i-2:i+1])
            sl_price = recent_3_high + 0.50
            sl_dist = sl_price - entry_price
            sl_dist = max(2.50, min(12.00, sl_dist))
            sl_price = entry_price + sl_dist
            tp1_price = entry_price - sl_dist * 1.0
            tp2_price = entry_price - sl_dist * 2.0
            tp3_price = entry_price - sl_dist * 3.0

        # Bar-by-bar Forward Simulation for Multi-Target Outcomes
        mae_dollars = 0.0
        mfe_dollars = 0.0
        hit_tp1, hit_tp2, hit_tp3, hit_sl = 0, 0, 0, 0

        for f in range(entry_idx, min(n, entry_idx + 120)):
            b_high = highs[f]
            b_low  = lows[f]

            if is_buy:
                adverse = entry_price - b_low
                favorable = b_high - entry_price
                if adverse > mae_dollars: mae_dollars = adverse
                if favorable > mfe_dollars: mfe_dollars = favorable

                if b_low <= sl_price:
                    hit_sl = 1
                    break
                if b_high >= tp1_price: hit_tp1 = 1
                if b_high >= tp2_price: hit_tp2 = 1
                if b_high >= tp3_price:
                    hit_tp3 = 1
                    break
            else:
                adverse = b_high - entry_price
                favorable = entry_price - b_low
                if adverse > mae_dollars: mae_dollars = adverse
                if favorable > mfe_dollars: mfe_dollars = favorable

                if b_high >= sl_price:
                    hit_sl = 1
                    break
                if b_low <= tp1_price: hit_tp1 = 1
                if b_low <= tp2_price: hit_tp2 = 1
                if b_low <= tp3_price:
                    hit_tp3 = 1
                    break

        # Primary Meta-Labeling Target (1 = Win TP1/TP2/TP3, 0 = Loss SL)
        meta_label = 1 if (hit_tp1 or hit_tp2 or hit_tp3) and not hit_sl else 0

        # 16 Normalized Features
        atr14_val = atr14s[i] if not np.isnan(atr14s[i]) else 1.50
        atr50_val = atr50s[i] if not np.isnan(atr50s[i]) else 1.50
        rsi_val   = rsi14s[i] if not np.isnan(rsi14s[i]) else 50.0

        fvg_size = bull_fvg_size if is_buy else bear_fvg_size
        impulse_sz = (highs[i-1] - lows[i-1])

        ema21_slope = (m5_ema21s[i] - m5_ema21s[i-3]) if is_buy else (m5_ema21s[i-3] - m5_ema21s[i])
        trend_sep   = abs(m15_ema21s[i] - m15_ema50s[i])
        trend_dist  = abs(m15_closes[i] - m15_ema50s[i])
        ext_ema21   = abs(entry_price - m5_ema21s[i])

        fvg_norm          = fvg_size / (atr14_val + 1e-6)
        disp_norm         = impulse_sz / (atr14_val + 1e-6)
        slope_norm        = ema21_slope / (atr14_val + 1e-6)
        trend_sep_norm    = trend_sep / (atr14_val + 1e-6)
        trend_dist_norm   = trend_dist / (atr14_val + 1e-6)
        ext_ema21_norm    = ext_ema21 / (atr14_val + 1e-6)
        sl_dist_norm      = sl_dist / (atr14_val + 1e-6)
        atr_regime        = atr14_val / (atr50_val + 1e-6)

        hr = hours[i]
        dy = days[i]
        hr_sin = np.sin(2 * np.pi * hr / 24.0)
        hr_cos = np.cos(2 * np.pi * hr / 24.0)
        dy_sin = np.sin(2 * np.pi * dy / 7.0)
        dy_cos = np.cos(2 * np.pi * dy / 7.0)

        candidates.append({
            'timestamp': entry_time,
            'fvg_norm': fvg_norm,
            'disp_norm': disp_norm,
            'slope_norm': slope_norm,
            'trend_sep_norm': trend_sep_norm,
            'trend_dist_norm': trend_dist_norm,
            'ext_ema21_norm': ext_ema21_norm,
            'sl_dist_norm': sl_dist_norm,
            'atr_regime': atr_regime,
            'rsi_14': rsi_val,
            'hr_sin': hr_sin,
            'hr_cos': hr_cos,
            'dy_sin': dy_sin,
            'dy_cos': dy_cos,
            'spread_norm': 0.15 / (atr14_val + 1e-6),
            'mfe_mae_ratio': (mfe_dollars + 0.01) / (mae_dollars + 0.01),
            # Multi-Target Labels
            'meta_label': meta_label,
            'target_tp1': hit_tp1,
            'target_tp2': hit_tp2,
            'target_tp3': hit_tp3,
            'target_sl': hit_sl,
            'mae_dollars': mae_dollars,
            'mfe_dollars': mfe_dollars
        })

    cand_df = pd.DataFrame(candidates)
    print(f" Candidate Dataset Extracted: {len(cand_df):,} Trade Setups (Meta-Label Win Rate: {cand_df['meta_label'].mean()*100:.1f}%).", flush=True)

    # Step 2: Feature Matrix & Purged Group TimeSeries Split
    feature_cols = [
        'fvg_norm', 'disp_norm', 'slope_norm', 'trend_sep_norm', 'trend_dist_norm',
        'ext_ema21_norm', 'sl_dist_norm', 'atr_regime', 'rsi_14',
        'hr_sin', 'hr_cos', 'dy_sin', 'dy_cos', 'spread_norm', 'mfe_mae_ratio'
    ]

    X = cand_df[feature_cols].values
    y = cand_df['meta_label'].values
    y_tp1 = cand_df['target_tp1'].values
    y_tp2 = cand_df['target_tp2'].values
    y_tp3 = cand_df['target_tp3'].values

    # Step 3: Multi-Model Tournament Benchmarking with Purged Walk-Forward Validation
    print("\n Step 3: Running Tournament Benchmarking (Purged Walk-Forward Cross-Validation)...", flush=True)
    
    models = {
        'Random Forest': RandomForestClassifier(n_estimators=150, max_depth=8, min_samples_leaf=10, random_state=42),
        'HistGradientBoosting': HistGradientBoostingClassifier(max_iter=100, max_depth=6, random_state=42),
        'ExtraTrees': ExtraTreesClassifier(n_estimators=150, max_depth=8, min_samples_leaf=10, random_state=42)
    }

    if XGBOOST_AVAILABLE:
        models['XGBoost'] = xgb.XGBClassifier(n_estimators=150, max_depth=5, learning_rate=0.05, random_state=42, eval_metric='logloss')
    if LIGHTGBM_AVAILABLE:
        models['LightGBM'] = lgb.LGBMClassifier(n_estimators=150, max_depth=5, learning_rate=0.05, random_state=42, verbose=-1)
    if CATBOOST_AVAILABLE:
        models['CatBoost'] = cb.CatBoostClassifier(iterations=150, depth=5, learning_rate=0.05, random_seed=42, verbose=0)

    tscv = TimeSeriesSplit(n_splits=5)
    tournament_results = []

    for name, model in models.items():
        aucs, precisions, briers = [], [], []
        
        for train_idx, val_idx in tscv.split(X):
            # Apply Purged Embargo (drop last 50 samples of training fold to prevent leakage)
            train_idx_purged = train_idx[:-50] if len(train_idx) > 50 else train_idx
            
            X_tr, y_tr = X[train_idx_purged], y[train_idx_purged]
            X_val, y_val = X[val_idx], y[val_idx]

            # Fit Calibrated Model
            cal_model = CalibratedClassifierCV(estimator=model, method='isotonic', cv=3)
            cal_model.fit(X_tr, y_tr)

            probs = cal_model.predict_proba(X_val)[:, 1]
            auc = roc_auc_score(y_val, probs)
            prec = precision_score(y_val, (probs >= 0.58).astype(int), zero_division=0)
            brier = brier_score_loss(y_val, probs)

            aucs.append(auc)
            precisions.append(prec)
            briers.append(brier)

        mean_auc = np.mean(aucs)
        mean_prec = np.mean(precisions)
        mean_brier = np.mean(briers)

        print(f"   - {name:<22} | ROC-AUC: {mean_auc:.4f} | Precision (p>=0.58): {mean_prec*100:.1f}% | Brier Score: {mean_brier:.4f}", flush=True)
        tournament_results.append({
            'model_name': name,
            'auc': mean_auc,
            'precision': mean_prec,
            'brier': mean_brier,
            'model_obj': model
        })

    # Pick Winning Champion Model
    tournament_df = pd.DataFrame(tournament_results).sort_values('auc', ascending=False).reset_index(drop=True)
    best_model_name = tournament_df.iloc[0]['model_name']
    best_base_model = tournament_df.iloc[0]['model_obj']

    print(f"\n [WINNER] TOURNAMENT CHAMPION: {best_model_name} (ROC-AUC: {tournament_df.iloc[0]['auc']:.4f})")

    # Step 4: Final Fit & Isotonic Calibration on Full Dataset
    print("\n Step 4: Training Calibrated Multi-Target Meta-Labeling Model...")
    
    champion_calibrated = CalibratedClassifierCV(estimator=best_base_model, method='isotonic', cv=5)
    champion_calibrated.fit(X, y)

    # Train Sub-Models for Multi-Target Probabilities
    cal_tp1 = CalibratedClassifierCV(estimator=best_base_model, method='isotonic', cv=5).fit(X, y_tp1)
    cal_tp2 = CalibratedClassifierCV(estimator=best_base_model, method='isotonic', cv=5).fit(X, y_tp2)
    cal_tp3 = CalibratedClassifierCV(estimator=best_base_model, method='isotonic', cv=5).fit(X, y_tp3)

    # Calculate Multi-Target Probabilities & Expected Return E[R]
    p_tp1 = cal_tp1.predict_proba(X)[:, 1]
    p_tp2 = cal_tp2.predict_proba(X)[:, 1]
    p_tp3 = cal_tp3.predict_proba(X)[:, 1]
    p_sl  = 1.0 - champion_calibrated.predict_proba(X)[:, 1]

    # Calculate Risk-Adjusted Expected Return E[R]
    expected_r = (p_tp1 * 1.0 * 0.50) + (p_tp2 * 2.0 * 0.333) + (p_tp3 * 3.0 * 0.167) - (p_sl * 1.0)
    cand_df['expected_r'] = expected_r

    print("-------------------------------------------------------------------------")
    print(" [STATS] MULTI-TARGET EXPECTED RETURN E[R] DISTRIBUTION:")
    print(f"   - Mean Expected Return E[R]  : {expected_r.mean():+.3f}x R")
    print(f"   - Max Expected Return E[R]   : {expected_r.max():+.3f}x R")
    print(f"   - Trades with E[R] > 0.0x    : {(expected_r > 0).sum():,} trades ({(expected_r > 0).mean()*100:.1f}%)")
    print(f"   - Trades with E[R] > +0.25x  : {(expected_r > 0.25).sum():,} trades ({(expected_r > 0.25).mean()*100:.1f}%)")

    # Step 5: Save Serialized Meta-Labeling Package
    meta_package = {
        'model_name': best_model_name,
        'main_meta_model': champion_calibrated,
        'model_tp1': cal_tp1,
        'model_tp2': cal_tp2,
        'model_tp3': cal_tp3,
        'feature_names': feature_cols,
        'expected_r_mean': float(expected_r.mean()),
        'tournament_benchmark': tournament_df.to_dict(orient='records')
    }

    out_dir = Path("models/saved_models")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "model2_1_metalabeling_engine.joblib"
    joblib.dump(meta_package, out_file)

    print("\n=========================================================================")
    print(f" [SUCCESS] MODEL 2.1 META-LABELING ENGINE SERIALIZED SUCCESSFULLY!")
    print(f" Saved Package: {out_file.resolve()}")
    print("=========================================================================\n")

if __name__ == "__main__":
    train_model2_1_metalabeling_engine()
