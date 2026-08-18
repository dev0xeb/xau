"""
Diagnostic Script: Why Trailing SL to TP1 Price cuts profits on Gold (XAU/USD)
"""

import sys
from pathlib import Path
import pandas as pd
import numpy as np

def run_diagnostics():
    proc_5m_path = Path("data/processed/xau_5m_5y.parquet")
    df = pd.read_parquet(proc_5m_path)
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    df = df.sort_values('timestamp').reset_index(drop=True)
    df['year'] = df['timestamp'].dt.year
    df['hour'] = df['timestamp'].dt.hour

    n = len(df)
    closes = df['close'].values
    highs = df['high'].values
    lows = df['low'].values
    hours = df['hour'].values
    years = df['year'].values

    # H1 Trend
    df_h1 = df.resample('1h', on='timestamp').agg({'open':'first','high':'max','low':'min','close':'last'}).dropna().reset_index()
    df_h1['h1_ema21'] = df_h1['close'].ewm(span=21, adjust=False).mean()
    df_h1['h1_ema50'] = df_h1['close'].ewm(span=50, adjust=False).mean()
    df['h1_time'] = df['timestamp'].dt.floor('1h')
    df = pd.merge_asof(df, df_h1[['timestamp','h1_ema21','h1_ema50','close']].rename(columns={'timestamp':'h1_time','close':'h1_close'}), on='h1_time', direction='backward')
    h1_closes, h1_ema21s, h1_ema50s = df['h1_close'].values, df['h1_ema21'].values, df['h1_ema50'].values

    df['m5_ema21'] = df['close'].ewm(span=21, adjust=False).mean()
    m5_ema21s = df['m5_ema21'].values

    pip_size = 0.10
    total_friction = (2.5 + 1.0) * pip_size

    def simulate_mode(mode_name):
        total_pnl = 0.0
        tp1_hits, tp2_hits, tp3_hits = 0, 0, 0
        sl_hits = 0
        last_bar = -10

        for i in range(50, n):
            if years[i] != 2026: continue
            if not (6 <= hours[i] < 17): continue
            if i <= last_bar + 1: continue

            idx = i - 1
            htf_bull = (h1_closes[idx] > h1_ema21s[idx]) and (h1_ema21s[idx] > h1_ema50s[idx])
            htf_bear = (h1_closes[idx] < h1_ema21s[idx]) and (h1_ema21s[idx] < h1_ema50s[idx])
            if not (htf_bull or htf_bear): continue

            low_t, high_t = lows[idx], highs[idx]
            low_t2, high_t2 = lows[idx - 2], highs[idx - 2]

            bull_fvg = ((low_t - high_t2) / pip_size) >= 1.5
            bear_fvg = ((low_t2 - high_t) / pip_size) >= 1.5

            prior_5_low = np.min(lows[idx-5 : idx])
            prior_5_high = np.max(highs[idx-5 : idx])
            m5_e21 = m5_ema21s[idx]

            bull_sweep = prior_5_low <= m5_e21
            bear_sweep = prior_5_high >= m5_e21
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
                tp1 = entry + (sl_dist * 1.0)
                tp2 = entry + (sl_dist * 2.0)
                tp3 = entry + (sl_dist * 3.0)
            else:
                entry = low_t2 - total_friction
                sl_dist = np.clip(((recent_3_high + 0.50) - entry) / pip_size, 15.0, 80.0) * pip_size
                sl = entry + sl_dist
                tp1 = entry - (sl_dist * 1.0)
                tp2 = entry - (sl_dist * 2.0)
                tp3 = entry - (sl_dist * 3.0)

            risk = 33.33
            t1_hit, t2_hit, t3_hit = False, False, False
            t1_pnl, t2_pnl, t3_pnl = -risk, -risk, -risk
            sl_t2, sl_t3 = sl, sl

            for k in range(i, min(i + 36, n)):
                bh, bl = highs[k], lows[k]
                if direction == "BUY":
                    if not t1_hit:
                        if bl <= sl:
                            break
                        elif bh >= tp1:
                            t1_hit = True
                            t1_pnl = risk * 1.0
                            if mode_name == "BE_PLUS_5":
                                sl_t2, sl_t3 = entry + 0.50, entry + 0.50
                            elif mode_name == "TP1_PRICE":
                                sl_t2, sl_t3 = tp1, tp1

                    if t1_hit and not t2_hit:
                        if bl <= sl_t2:
                            t2_pnl = 0.0 if mode_name == "BE_PLUS_5" else risk * 1.0
                            t3_pnl = 0.0 if mode_name == "BE_PLUS_5" else risk * 1.0
                            break
                        elif bh >= tp2:
                            t2_hit = True
                            t2_pnl = risk * 2.0

                    if t2_hit and not t3_hit:
                        if bl <= sl_t3:
                            t3_pnl = 0.0 if mode_name == "BE_PLUS_5" else risk * 1.0
                            break
                        elif bh >= tp3:
                            t3_hit = True
                            t3_pnl = ticket_pnl = risk * 3.0
                            last_bar = k
                            break
                else:
                    if not t1_hit:
                        if bh >= sl:
                            break
                        elif bl <= tp1:
                            t1_hit = True
                            t1_pnl = risk * 1.0
                            if mode_name == "BE_PLUS_5":
                                sl_t2, sl_t3 = entry - 0.50, entry - 0.50
                            elif mode_name == "TP1_PRICE":
                                sl_t2, sl_t3 = tp1, tp1

                    if t1_hit and not t2_hit:
                        if bh >= sl_t2:
                            t2_pnl = 0.0 if mode_name == "BE_PLUS_5" else risk * 1.0
                            t3_pnl = 0.0 if mode_name == "BE_PLUS_5" else risk * 1.0
                            break
                        elif bl <= tp2:
                            t2_hit = True
                            t2_pnl = risk * 2.0

                    if t2_hit and not t3_hit:
                        if bh >= sl_t3:
                            t3_pnl = 0.0 if mode_name == "BE_PLUS_5" else risk * 1.0
                            break
                        elif bl <= tp3:
                            t3_hit = True
                            t3_pnl = risk * 3.0
                            last_bar = k
                            break

            total_pnl += (t1_pnl + t2_pnl + t3_pnl)
            if t1_hit: tp1_hits += 1
            if t2_hit: tp2_hits += 1
            if t3_hit: tp3_hits += 1
            if not t1_hit: sl_hits += 1

        print(f"--- MODE: {mode_name} ---")
        print(f" Net PnL: ${total_pnl:,.2f}")
        print(f" TP1: {tp1_hits} | TP2: {tp2_hits} | TP3: {tp3_hits} | SL: {sl_hits}\n")

    simulate_mode("FIXED_SL")
    simulate_mode("BE_PLUS_5")
    simulate_mode("TP1_PRICE")

if __name__ == "__main__":
    run_diagnostics()
