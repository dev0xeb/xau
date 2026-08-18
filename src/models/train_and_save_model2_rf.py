"""
Train and serialize the Random Forest Quality Gate model for Model 2 on XAU/USD.
Trained on 2021-2025 data and saved to src/models/model2_rf_gate.joblib.
"""

import sys
from pathlib import Path
import pandas as pd
import numpy as np
import joblib
from sklearn.ensemble import RandomForestClassifier

def train_and_save_rf_model():
    proc_5m_path = Path("data/processed/xau_5m_5y.parquet")
    if not proc_5m_path.exists():
        print("[ERROR] 5m dataset missing at data/processed/xau_5m_5y.parquet!")
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

        t1_hit, t2_hit, t3_hit = False, False, False
        exit_bar = i + 36

        for k in range(i, min(i + 36, n)):
            bar_h, bar_l = highs[k], lows[k]
            if direction == "BUY":
                if bar_l <= sl_price:
                    exit_bar = k
                    break
                if not t1_hit and bar_h >= tp1_price: t1_hit = True
                if t1_hit and not t2_hit and bar_h >= tp2_price: t2_hit = True
                if t2_hit and not t3_hit and bar_h >= tp3_price:
                    t3_hit = True
                    exit_bar = k
                    break
            else:
                if bar_h >= sl_price:
                    exit_bar = k
                    break
                if not t1_hit and bar_l <= tp1_price: t1_hit = True
                if t1_hit and not t2_hit and bar_l <= tp2_price: t2_hit = True
                if t2_hit and not t3_hit and bar_l <= tp3_price:
                    t3_hit = True
                    exit_bar = k
                    break

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
            'year': years[i],
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

    df_dataset = pd.DataFrame(records)
    feature_cols = ['f_fvg_size', 'f_sweep_depth', 'f_vwap_dist', 'f_atr_ratio', 
                    'f_h1_spread', 'f_m5_slope', 'f_body_ratio', 'f_rsi_14', 
                    'f_vol_ratio', 'f_dist_swing', 'f_hour_utc']

    train_mask = df_dataset['year'] < 2026
    X_train = df_dataset.loc[train_mask, feature_cols]
    y_train = df_dataset.loc[train_mask, 'is_win']

    print(f"[INFO] Training Random Forest Quality Gate on {len(X_train)} historical samples (2021-2025)...")
    clf = RandomForestClassifier(n_estimators=100, max_depth=4, min_samples_leaf=20, random_state=42)
    clf.fit(X_train, y_train)

    models_dir = Path("src/models")
    models_dir.mkdir(parents=True, exist_ok=True)
    model_path = models_dir / "model2_rf_gate.joblib"
    joblib.dump(clf, model_path)

    print(f"[SUCCESS] Trained Random Forest model saved successfully to: {model_path.resolve()}")

if __name__ == "__main__":
    train_and_save_rf_model()
