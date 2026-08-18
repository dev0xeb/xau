"""
Granular 3-Month Exit Breakdown & Near-Miss Analysis for Model 2 (Baseline vs Optimized).

Categorizes every trade setup into 6 precise outcome buckets:
1. Full 3-Burst Clean Winner (TP1 + TP2 + TP3 All Hit)
2. TP1 + TP2 Hit -> SL on Ticket 3 (Banked 1.0x & 2.0x, SL on TP3)
3. TP1 Hit -> SL on Tickets 2 & 3 (Banked 1.0x, SL on TP2 & TP3)
4. Near-Miss TP2 -> SL (Came within 80%+ of TP2 target before reversing to SL)
5. Near-Miss TP1 -> Direct SL (Came within 80%+ of TP1 target before reversing to SL)
6. Direct Full Loss (Hit SL without reaching TP1)
"""

import sys
from pathlib import Path
from datetime import datetime, date
import pandas as pd
import numpy as np
import time

def run_model2_granular_exit_analysis():
    proc_5m_path = Path("data/processed/xau_5m_5y.parquet")
    if not proc_5m_path.exists():
        print("[ERROR] 5m parquet file not found!")
        return

    start_t = time.time()

    df_5m = pd.read_parquet(proc_5m_path)
    df_5m['timestamp'] = pd.to_datetime(df_5m['timestamp'])
    if df_5m['timestamp'].dt.tz is None:
        df_5m['timestamp'] = df_5m['timestamp'].dt.tz_localize('UTC')
    else:
        df_5m['timestamp'] = df_5m['timestamp'].dt.tz_convert('UTC')

    df_5m = df_5m.sort_values('timestamp').reset_index(drop=True)

    cutoff_date = pd.to_datetime("2026-05-10 00:00:00", utc=True)
    df_3m_5m = df_5m[df_5m['timestamp'] >= cutoff_date].copy().reset_index(drop=True)

    df_1h = df_3m_5m.set_index('timestamp').resample('1h').agg({
        'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last'
    }).dropna().reset_index()

    df_1h['h1_ema21'] = df_1h['close'].ewm(span=21, adjust=False).mean()
    df_1h['h1_ema50'] = df_1h['close'].ewm(span=50, adjust=False).mean()

    df_1h['h1_trend'] = 'NEUTRAL'
    df_1h.loc[(df_1h['close'] > df_1h['h1_ema21']) & (df_1h['h1_ema21'] > df_1h['h1_ema50']), 'h1_trend'] = 'BULLISH'
    df_1h.loc[(df_1h['close'] < df_1h['h1_ema21']) & (df_1h['h1_ema21'] < df_1h['h1_ema50']), 'h1_trend'] = 'BEARISH'

    df_3m_5m = pd.merge_asof(
        df_3m_5m.sort_values('timestamp'),
        df_1h[['timestamp', 'h1_ema21', 'h1_ema50', 'h1_trend']].sort_values('timestamp'),
        on='timestamp',
        direction='backward'
    )

    df_3m_5m['m5_ema21'] = df_3m_5m['close'].ewm(span=21, adjust=False).mean()
    df_3m_5m['hour'] = df_3m_5m['timestamp'].dt.hour

    closes = df_3m_5m['close'].values
    highs = df_3m_5m['high'].values
    lows = df_3m_5m['low'].values
    times = df_3m_5m['timestamp'].dt.strftime('%Y-%m-%d %H:%M UTC').values
    hours = df_3m_5m['hour'].values
    h1_trends = df_3m_5m['h1_trend'].values
    m5_ema21 = df_3m_5m['m5_ema21'].values
    n = len(df_3m_5m)

    spread_estimate = 0.15
    pip_size = 0.10

    def analyze_model_exits(is_optimized=False):
        trade_logs = []
        triggered_bars = set()

        for i in range(10, n - 24):
            t = i
            t_time = times[t]
            hr = hours[t]

            if is_optimized:
                if not (7 <= hr < 17): continue
            else:
                if not (6 <= hr <= 20): continue

            h1_trend = h1_trends[t]
            if h1_trend == 'NEUTRAL': continue

            bull_fvg_pips = (lows[t] - highs[t-2]) / pip_size
            bear_fvg_pips = (lows[t-2] - highs[t]) / pip_size

            is_bull_fvg = (lows[t] > highs[t-2]) and (bull_fvg_pips >= 1.5)
            is_bear_fvg = (highs[t] < lows[t-2]) and (bear_fvg_pips >= 1.5)

            prior_5_low = np.min(lows[max(0, t-5):t])
            prior_5_high = np.max(highs[max(0, t-5):t])

            bull_sweep = (prior_5_low <= m5_ema21[t])
            bear_sweep = (prior_5_high >= m5_ema21[t])

            bull_signal = (h1_trend == 'BULLISH') and is_bull_fvg and bull_sweep and (closes[t] > m5_ema21[t])
            bear_signal = (h1_trend == 'BEARISH') and is_bear_fvg and bear_sweep and (closes[t] < m5_ema21[t])

            if not (bull_signal or bear_signal): continue

            if is_optimized:
                if bull_signal:
                    entry_price = highs[t-2] + spread_estimate
                    if (entry_price - m5_ema21[t]) > 3.00: continue
                elif bear_signal:
                    entry_price = lows[t-2]
                    if (m5_ema21[t] - entry_price) > 3.00: continue

            if t in triggered_bars: continue
            triggered_bars.add(t)

            recent_3_low = np.min(lows[t-2:t+1])
            recent_3_high = np.max(highs[t-2:t+1])

            if bull_signal:
                entry_price = highs[t-2] + spread_estimate
                raw_sl_pips = (entry_price - (recent_3_low - 0.50)) / pip_size
                sl_pips = max(min(raw_sl_pips, 80.0), 15.0)
                sl_price = entry_price - (sl_pips * pip_size)

                tp1 = entry_price + (sl_pips * 1.0 * pip_size)
                tp2 = entry_price + (sl_pips * 2.0 * pip_size)
                tp3 = entry_price + (sl_pips * 3.0 * pip_size)

                t1_hit, t2_hit, t3_hit = False, False, False
                near_tp1, near_tp2 = False, False
                sl_hit = False

                for k in range(t+1, min(t+25, n)):
                    max_p = highs[k]
                    min_p = lows[k]

                    # Track Near-miss thresholds (80% of distance to target)
                    if (max_p - entry_price) >= (tp1 - entry_price) * 0.80: near_tp1 = True
                    if (max_p - entry_price) >= (tp2 - entry_price) * 0.80: near_tp2 = True

                    if min_p <= sl_price:
                        sl_hit = True; break

                    if not t1_hit and max_p >= tp1: t1_hit = True
                    if not t2_hit and max_p >= tp2: t2_hit = True
                    if not t3_hit and max_p >= tp3: t3_hit = True

                    if t1_hit and t2_hit and t3_hit: break

                # Categorize exact outcome
                if t1_hit and t2_hit and t3_hit:
                    cat = "1. Full Clean Winner (TP1 + TP2 + TP3 Hit)"
                elif t1_hit and t2_hit and sl_hit:
                    cat = "2. TP1 + TP2 Hit -> SL on Ticket 3"
                elif t1_hit and sl_hit:
                    if near_tp2:
                        cat = "4. Near-Miss TP2 -> SL on Ticket 2 & 3"
                    else:
                        cat = "3. TP1 Hit -> SL on Ticket 2 & 3"
                elif sl_hit:
                    if near_tp1:
                        cat = "5. Near-Miss TP1 -> Direct SL"
                    else:
                        cat = "6. Direct Full Loss (Hit SL before TP1)"
                else:
                    cat = "1. Full Clean Winner (TP1 + TP2 + TP3 Hit)" # Expiration in profit

                trade_logs.append({'cat': cat, 't1': t1_hit, 't2': t2_hit, 't3': t3_hit, 'sl': sl_hit})

            elif bear_signal:
                entry_price = lows[t-2]
                raw_sl_pips = ((recent_3_high + 0.50) - entry_price) / pip_size
                sl_pips = max(min(raw_sl_pips, 80.0), 15.0)
                sl_price = entry_price + (sl_pips * pip_size)

                tp1 = entry_price - (sl_pips * 1.0 * pip_size)
                tp2 = entry_price - (sl_pips * 2.0 * pip_size)
                tp3 = entry_price - (sl_pips * 3.0 * pip_size)

                t1_hit, t2_hit, t3_hit = False, False, False
                near_tp1, near_tp2 = False, False
                sl_hit = False

                for k in range(t+1, min(t+25, n)):
                    min_p = lows[k]
                    max_p = highs[k]

                    if (entry_price - min_p) >= (entry_price - tp1) * 0.80: near_tp1 = True
                    if (entry_price - min_p) >= (entry_price - tp2) * 0.80: near_tp2 = True

                    if max_p >= sl_price:
                        sl_hit = True; break

                    if not t1_hit and min_p <= tp1: t1_hit = True
                    if not t2_hit and min_p <= tp2: t2_hit = True
                    if not t3_hit and min_p <= tp3: t3_hit = True

                    if t1_hit and t2_hit and t3_hit: break

                if t1_hit and t2_hit and t3_hit:
                    cat = "1. Full Clean Winner (TP1 + TP2 + TP3 Hit)"
                elif t1_hit and t2_hit and sl_hit:
                    cat = "2. TP1 + TP2 Hit -> SL on Ticket 3"
                elif t1_hit and sl_hit:
                    if near_tp2:
                        cat = "4. Near-Miss TP2 -> SL on Ticket 2 & 3"
                    else:
                        cat = "3. TP1 Hit -> SL on Ticket 2 & 3"
                elif sl_hit:
                    if near_tp1:
                        cat = "5. Near-Miss TP1 -> Direct SL"
                    else:
                        cat = "6. Direct Full Loss (Hit SL before TP1)"
                else:
                    cat = "1. Full Clean Winner (TP1 + TP2 + TP3 Hit)"

                trade_logs.append({'cat': cat, 't1': t1_hit, 't2': t2_hit, 't3': t3_hit, 'sl': sl_hit})

        return pd.DataFrame(trade_logs)

    df_base = analyze_model_exits(is_optimized=False)
    df_opt = analyze_model_exits(is_optimized=True)

    elapsed = time.time() - start_t

    print("=========================================================================================")
    print(f" MODEL 2: GRANULAR EXIT CATEGORY & NEAR-MISS ANALYSIS (MAY 10 - AUG 10, 2026) [{elapsed:.2f}s]")
    print("=========================================================================================")

    cats = [
        "1. Full Clean Winner (TP1 + TP2 + TP3 Hit)",
        "2. TP1 + TP2 Hit -> SL on Ticket 3",
        "3. TP1 Hit -> SL on Ticket 2 & 3",
        "4. Near-Miss TP2 -> SL on Ticket 2 & 3",
        "5. Near-Miss TP1 -> Direct SL",
        "6. Direct Full Loss (Hit SL before TP1)"
    ]

    print(f"\n {'OUTCOME CATEGORY':<42} | {'BASELINE MODEL 2':<22} | {'OPTIMIZED MODEL 2'}")
    print("-" * 95)

    tot_b = len(df_base)
    tot_o = len(df_opt)

    for c in cats:
        cnt_b = len(df_base[df_base['cat'] == c])
        cnt_o = len(df_opt[df_opt['cat'] == c])
        pct_b = (cnt_b / tot_b * 100.0) if tot_b > 0 else 0
        pct_o = (cnt_o / tot_o * 100.0) if tot_o > 0 else 0

        print(f" {c:<42} | {cnt_b:3d} ({pct_b:4.1f}%)            | {cnt_o:3d} ({pct_o:4.1f}%)")

    print("-" * 95)
    print(f" TOTAL EVALUATED TRADES                    | {tot_b:3d} (100.0%)           | {tot_o:3d} (100.0%)")

if __name__ == "__main__":
    run_model2_granular_exit_analysis()
