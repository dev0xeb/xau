"""
Empirical Benchmark for Date Range: August 1, 2026 to August 17, 2026
Testing Option 3 (Trailing SL to TP1 Price AFTER TP2 Hit) vs Option 0 (Fixed SL)
for Personal Engine and Prop Firm Engine on XAU/USD.
"""

import sys
from pathlib import Path
import pandas as pd
import numpy as np

def run_august_test():
    proc_5m_path = Path("data/processed/xau_5m_5y.parquet")
    if not proc_5m_path.exists():
        print("[ERROR] 5m dataset missing!")
        return

    df = pd.read_parquet(proc_5m_path)
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    df = df.sort_values('timestamp').reset_index(drop=True)

    # Filter strictly for August 1, 2026 to August 17, 2026
    df = df[(df['timestamp'] >= '2026-08-01') & (df['timestamp'] <= '2026-08-17 23:59:59')].reset_index(drop=True)

    df['hour'] = df['timestamp'].dt.hour

    n = len(df)
    closes = df['close'].values
    highs = df['high'].values
    lows = df['low'].values
    hours = df['hour'].values
    timestamps = df['timestamp'].values

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

    def simulate_august_engine(is_prop=False, mode=3):
        initial_balance = 100.0
        balance = initial_balance
        last_trade_bar = -10
        records = []

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

            ticket_risk = 1.0 / 3.0 # $1.00 total risk on $100 balance = $0.33 per ticket
            t1_hit, t2_hit, t3_hit = False, False, False
            t1_pnl, t2_pnl, t3_pnl = -ticket_risk, -ticket_risk, -ticket_risk
            sl_t3 = sl

            for k in range(i, min(i + 36, n)):
                bh, bl = highs[k], lows[k]
                if direction == "BUY":
                    if not t1_hit:
                        if bl <= sl: break
                        elif bh >= tp1:
                            t1_hit = True
                            t1_pnl = ticket_risk * 1.0
                    if t1_hit and not t2_hit:
                        if bl <= sl: break
                        elif bh >= tp2:
                            t2_hit = True
                            t2_pnl = ticket_risk * 2.0
                            if mode == 3: sl_t3 = tp1 # Trail SL for Ticket 3 to TP1 Price!
                            elif mode == 4: sl_t3 = entry + 0.50 # BE+5 pips
                    if t2_hit and not t3_hit:
                        if bl <= sl_t3:
                            t3_pnl = ticket_risk * 1.0 if mode == 3 else 0.0
                            break
                        elif bh >= tp3:
                            t3_hit = True
                            t3_pnl = ticket_risk * 3.0
                            last_bar = k
                            break
                else:
                    if not t1_hit:
                        if bh >= sl: break
                        elif bl <= tp1:
                            t1_hit = True
                            t1_pnl = ticket_risk * 1.0
                    if t1_hit and not t2_hit:
                        if bh >= sl: break
                        elif bl <= tp2:
                            t2_hit = True
                            t2_pnl = ticket_risk * 2.0
                            if mode == 3: sl_t3 = tp1
                            elif mode == 4: sl_t3 = entry - 0.50
                    if t2_hit and not t3_hit:
                        if bh >= sl_t3:
                            t3_pnl = ticket_risk * 1.0 if mode == 3 else 0.0
                            break
                        elif bl <= tp3:
                            t3_hit = True
                            t3_pnl = ticket_risk * 3.0
                            last_bar = k
                            break

            setup_pnl = t1_pnl + t2_pnl + t3_pnl
            balance += setup_pnl
            records.append({
                'pnl': setup_pnl,
                't1': int(t1_hit),
                't2': int(t2_hit),
                't3': int(t3_hit)
            })

        df_r = pd.DataFrame(records)
        total_setups = len(df_r)
        tp1_cnt = df_r['t1'].sum()
        tp2_cnt = df_r['t2'].sum()
        tp3_cnt = df_r['t3'].sum()
        sl_cnt = total_setups - tp1_cnt
        net_profit = balance - initial_balance

        return total_setups, balance, net_profit, tp1_cnt, tp2_cnt, tp3_cnt, sl_cnt

    print("=========================================================================================")
    print(" AUGUST 1, 2026 - AUGUST 17, 2026 EMPIRICAL BENCHMARK ($100 DEPOSIT)")
    print("=========================================================================================\n")

    for mode_val, mode_lbl in [(0, "Fixed SL (Mode 0)"), (3, "TP1 Price AFTER TP2 Hit (Mode 3)"), (4, "BE+5 Pips AFTER TP2 Hit (Mode 4)")]:
        print(f"--- MODE {mode_val}: {mode_lbl} ---")
        setups, bal, net_p, t1, t2, t3, sl = simulate_august_engine(is_prop=False, mode=mode_val)
        print(f"   - Final Balance  : ${bal:.2f} USD (+{net_p:.2f}% Return)")
        print(f"   - Total Setups   : {setups} Setups ({setups * 3} Tickets)")
        print(f"   - Target Breakdown: TP1: {t1} | TP2: {t2} | TP3: {t3} | SL Hits: {sl}\n")

if __name__ == "__main__":
    run_august_test()
