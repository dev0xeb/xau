"""
4-Way Comparison Table for August 1, 2026 - August 17, 2026 ($100 Deposit)
Compares:
1. Baseline Engine (Mode 0: Fixed SL - No Trailing)
2. Baseline Engine (Mode 3: Trailing SL to TP1 Price AFTER TP2 Hit)
3. Enforced Low-Loss Engine (Mode 0: Fixed SL - No Trailing)
4. Enforced Low-Loss Engine (Mode 3: Trailing SL to TP1 Price AFTER TP2 Hit)
"""

import sys
from pathlib import Path
import pandas as pd
import numpy as np

def run_4way_table():
    proc_5m_path = Path("data/processed/xau_5m_5y.parquet")
    if not proc_5m_path.exists():
        print("[ERROR] 5m dataset missing!")
        return

    df = pd.read_parquet(proc_5m_path)
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    df = df.sort_values('timestamp').reset_index(drop=True)

    df = df[(df['timestamp'] >= '2026-08-01') & (df['timestamp'] <= '2026-08-17 23:59:59')].reset_index(drop=True)

    df['date'] = df['timestamp'].dt.date
    df['hour'] = df['timestamp'].dt.hour

    n = len(df)
    closes = df['close'].values
    highs = df['high'].values
    lows = df['low'].values
    volumes = df['volume'].values
    hours = df['hour'].values

    # H1 Trend
    df_h1 = df.resample('1h', on='timestamp').agg({'open':'first','high':'max','low':'min','close':'last'}).dropna().reset_index()
    df_h1['h1_ema21'] = df_h1['close'].ewm(span=21, adjust=False).mean()
    df_h1['h1_ema50'] = df_h1['close'].ewm(span=50, adjust=False).mean()
    df['h1_time'] = df['timestamp'].dt.floor('1h')
    df = pd.merge_asof(df, df_h1[['timestamp','h1_ema21','h1_ema50','close']].rename(columns={'timestamp':'h1_time','close':'h1_close'}), on='h1_time', direction='backward')
    h1_closes, h1_ema21s, h1_ema50s = df['h1_close'].values, df['h1_ema21'].values, df['h1_ema50'].values

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

    pip_size = 0.10
    total_friction = (2.5 + 1.0) * pip_size

    def simulate_variant(is_enforced=False, mode=0):
        initial_balance = 100.0
        balance = initial_balance
        last_trade_bar = -10
        records = []

        start_h = 8 if is_enforced else 6
        end_h = 16 if is_enforced else 17
        min_sl_pips = 20.0 if is_enforced else 15.0

        for i in range(50, n):
            hour = hours[i]
            if not (start_h <= hour < end_h): continue
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
            c_vwap = daily_vwap[idx]
            m5_close = closes[idx]

            if is_enforced:
                vwap_bull = m5_close > c_vwap
                vwap_bear = m5_close < c_vwap
                base_buy = htf_bull and bull_fvg and bull_sweep and (m5_close > m5_e21) and vwap_bull
                base_sell = htf_bear and bear_fvg and bear_sweep and (m5_close < m5_e21) and vwap_bear
            else:
                base_buy = htf_bull and bull_fvg and bull_sweep and (m5_close > m5_e21)
                base_sell = htf_bear and bear_fvg and bear_sweep and (m5_close < m5_e21)

            if not (base_buy or base_sell): continue

            direction = "BUY" if base_buy else "SELL"
            recent_3_low = np.min(lows[idx-2 : idx+1])
            recent_3_high = np.max(highs[idx-2 : idx+1])

            if direction == "BUY":
                entry = high_t2 + total_friction
                sl_dist = np.clip((entry - (recent_3_low - 0.50)) / pip_size, min_sl_pips, 80.0) * pip_size
                sl = entry - sl_dist
                tp1 = entry + (sl_dist * 1.0)
                tp2 = entry + (sl_dist * 2.0)
                tp3 = entry + (sl_dist * 3.0)
            else:
                entry = low_t2 - total_friction
                sl_dist = np.clip(((recent_3_high + 0.50) - entry) / pip_size, min_sl_pips, 80.0) * pip_size
                sl = entry + sl_dist
                tp1 = entry - (sl_dist * 1.0)
                tp2 = entry - (sl_dist * 2.0)
                tp3 = entry - (sl_dist * 3.0)

            ticket_risk = 1.0 / 3.0 # $0.33 per ticket
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
                            if mode == 3: sl_t3 = tp1
                    if t2_hit and not t3_hit:
                        if bl <= sl_t3:
                            t3_pnl = ticket_risk * 1.0 if mode == 3 else -ticket_risk
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
                    if t2_hit and not t3_hit:
                        if bh >= sl_t3:
                            t3_pnl = ticket_risk * 1.0 if mode == 3 else -ticket_risk
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
        tp1_cnt = df_r['t1'].sum() if total_setups > 0 else 0
        tp2_cnt = df_r['t2'].sum() if total_setups > 0 else 0
        tp3_cnt = df_r['t3'].sum() if total_setups > 0 else 0
        sl_cnt = total_setups - tp1_cnt
        net_profit = balance - initial_balance
        win_rate = (tp1_cnt / total_setups * 100.0) if total_setups > 0 else 0

        gross_profit = df_r[df_r['pnl'] > 0]['pnl'].sum() if total_setups > 0 else 0
        gross_loss = abs(df_r[df_r['pnl'] < 0]['pnl'].sum()) if total_setups > 0 else 0
        profit_factor = gross_profit / (gross_loss + 1e-9)

        return total_setups, balance, net_profit, win_rate, profit_factor, tp1_cnt, tp2_cnt, tp3_cnt, sl_cnt

    print("=========================================================================================")
    print(" AUGUST 1, 2026 - AUGUST 17, 2026 4-WAY COMPARISON MATRIX ($100 DEPOSIT)")
    print("=========================================================================================\n")

    res_b0 = simulate_variant(is_enforced=False, mode=0)
    res_b3 = simulate_variant(is_enforced=False, mode=3)
    res_e0 = simulate_variant(is_enforced=True, mode=0)
    res_e3 = simulate_variant(is_enforced=True, mode=3)

    print(f"1. Baseline Engine (Mode 0: Fixed SL - No Trailing):")
    print(f"   Final Balance: ${res_b0[1]:.2f} USD (+{res_b0[2]:.2f}% Return) | Setups: {res_b0[0]} | WinRate: {res_b0[3]:.2f}% | PF: {res_b0[4]:.2f} | TP1: {res_b0[5]} | TP2: {res_b0[6]} | TP3: {res_b0[7]} | SL: {res_b0[8]}")

    print(f"2. Baseline Engine (Mode 3: Trailing SL AFTER TP2 Hit):")
    print(f"   Final Balance: ${res_b3[1]:.2f} USD (+{res_b3[2]:.2f}% Return) | Setups: {res_b3[0]} | WinRate: {res_b3[3]:.2f}% | PF: {res_b3[4]:.2f} | TP1: {res_b3[5]} | TP2: {res_b3[6]} | TP3: {res_b3[7]} | SL: {res_b3[8]}")

    print(f"3. Enforced Low-Loss Engine (Mode 0: Fixed SL - No Trailing):")
    print(f"   Final Balance: ${res_e0[1]:.2f} USD (+{res_e0[2]:.2f}% Return) | Setups: {res_e0[0]} | WinRate: {res_e0[3]:.2f}% | PF: {res_e0[4]:.2f} | TP1: {res_e0[5]} | TP2: {res_e0[6]} | TP3: {res_e0[7]} | SL: {res_e0[8]}")

    print(f"4. Enforced Low-Loss Engine (Mode 3: Trailing SL AFTER TP2 Hit):")
    print(f"   Final Balance: ${res_e3[1]:.2f} USD (+{res_e3[2]:.2f}% Return) | Setups: {res_e3[0]} | WinRate: {res_e3[3]:.2f}% | PF: {res_e3[4]:.2f} | TP1: {res_e3[5]} | TP2: {res_e3[6]} | TP3: {res_e3[7]} | SL: {res_e3[8]}")

if __name__ == "__main__":
    run_4way_table()
