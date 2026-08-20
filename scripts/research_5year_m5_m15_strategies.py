"""
5-Year M5/M15 Institutional Strategy Research & Loss-Elimination Engine
-----------------------------------------------------------------------
Analyzes 5 years of 5M/15M Gold data (2021-2026), monitoring Asian, London, and NY Sessions + Asian Liquidity Sweeps.
"""

import sys
from pathlib import Path
import pandas as pd
import numpy as np

def run_5year_institutional_research():
    dataset_path = Path("data/processed/xau_5m_5y.parquet")
    if not dataset_path.exists():
        print(f"[ERROR] Dataset missing at: {dataset_path.resolve()}")
        return

    print("Loading 5-Year XAU/USD 5M dataset...")
    df = pd.read_parquet(dataset_path)
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    df = df.sort_values('timestamp').reset_index(drop=True)

    df['date'] = df['timestamp'].dt.date
    df['hour'] = df['timestamp'].dt.hour

    n = len(df)
    closes = df['close'].values
    opens = df['open'].values
    highs = df['high'].values
    lows = df['low'].values
    volumes = df['volume'].values
    hours = df['hour'].values
    timestamps = df['timestamp'].values

    print(f"Dataset Loaded: {n:,} 5-minute bars from {timestamps[0]} to {timestamps[-1]}.")

    # M15 Macro Trend
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

    df['m5_ema21'] = df['close'].ewm(span=21, adjust=False).mean()
    m5_ema21s = df['m5_ema21'].values

    # Track Asian Range High & Low per day (00:00 to 06:00 UTC)
    asian_mask = (df['hour'] >= 0) & (df['hour'] < 6)
    asian_df = df[asian_mask].groupby('date').agg({'high':'max', 'low':'min'}).rename(columns={'high':'asian_high', 'low':'asian_low'}).reset_index()
    df = pd.merge(df, asian_df, on='date', how='left')

    asian_highs = df['asian_high'].values
    asian_lows = df['asian_low'].values

    pip_size = 0.10
    total_friction = (2.5 + 1.0) * pip_size

    # Session Counters
    session_stats = {
        "Asian (00:00-06:00 UTC)": {"wins": 0, "losses": 0, "profit_pips": 0.0, "loss_pips": 0.0},
        "London (06:00-13:00 UTC)": {"wins": 0, "losses": 0, "profit_pips": 0.0, "loss_pips": 0.0},
        "New York (13:00-21:00 UTC)": {"wins": 0, "losses": 0, "profit_pips": 0.0, "loss_pips": 0.0},
        "Asian Liquidity Sweep": {"wins": 0, "losses": 0, "profit_pips": 0.0, "loss_pips": 0.0},
    }

    last_trade_bar = -10

    for i in range(50, n - 100):
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
            tp1_price = entry_price + (sl_pips * pip_size * 2.0)  # 2.0x R:R
        else:
            entry_price = low_t2 - total_friction
            recent_3_high = np.max(highs[idx-2 : idx+1])
            sl_price = recent_3_high + 0.50
            sl_pips = np.clip((sl_price - entry_price) / pip_size, 15.0, 80.0)
            sl_price = entry_price + (sl_pips * pip_size)
            tp1_price = entry_price - (sl_pips * pip_size * 2.0)

        # Forward Outcome
        win = False
        loss = False
        for k in range(i, min(i + 150, n)):
            if direction == "BUY":
                if lows[k] <= sl_price:
                    loss = True
                    break
                if highs[k] >= tp1_price:
                    win = True
                    break
            else:
                if highs[k] >= sl_price:
                    loss = True
                    break
                if lows[k] <= tp1_price:
                    win = True
                    break

        hour = hours[idx]
        is_asian = (0 <= hour < 6)
        is_london = (6 <= hour < 13)
        is_ny = (13 <= hour < 21)
        is_asian_sweep = (direction == "BUY" and prior_5_low <= asian_lows[idx]) or (direction == "SELL" and prior_5_high >= asian_highs[idx])

        targets = []
        if is_asian: targets.append("Asian (00:00-06:00 UTC)")
        if is_london: targets.append("London (06:00-13:00 UTC)")
        if is_ny: targets.append("New York (13:00-21:00 UTC)")
        if is_asian_sweep: targets.append("Asian Liquidity Sweep")

        for key in targets:
            if win:
                session_stats[key]['wins'] += 1
                session_stats[key]['profit_pips'] += sl_pips * 2.0
            elif loss:
                session_stats[key]['losses'] += 1
                session_stats[key]['loss_pips'] += sl_pips

        last_trade_bar = i

    print("\n=========================================================================================")
    print(" 5-YEAR SESSION BREAKDOWN & ASIAN LIQUIDITY RESEARCH REPORT")
    print("=========================================================================================")
    for session, stat in session_stats.items():
        total = stat['wins'] + stat['losses']
        win_rate = (stat['wins'] / total * 100.0) if total > 0 else 0.0
        pf = (stat['profit_pips'] / stat['loss_pips']) if stat['loss_pips'] > 0 else 0.0
        print(f" Session / Pattern: {session:28s}")
        print(f"   - Total Setups: {total:,} | Wins: {stat['wins']:,} | Losses: {stat['losses']:,}")
        print(f"   - Win Rate (%) : {win_rate:.1f}% | Profit Factor: {pf:.2f}\n")

if __name__ == "__main__":
    run_5year_institutional_research()
