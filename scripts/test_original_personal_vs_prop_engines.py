"""
Comparison Matrix: Original Personal Engine vs Original Prop Firm Engine
(Before any additional 08-16 UTC / 20-pip min SL optimizations were added)
Evaluated on:
1. August 1, 2026 - August 17, 2026 ($100 Deposit)
2. 5-Year Full Benchmark Dataset (2021-2026, $10,000 Deposit)
"""

import sys
from pathlib import Path
import pandas as pd
import numpy as np

def run_original_engines_comparison():
    proc_5m_path = Path("data/processed/xau_5m_5y.parquet")
    if not proc_5m_path.exists():
        print("[ERROR] 5m dataset missing!")
        return

    df = pd.read_parquet(proc_5m_path)
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    df = df.sort_values('timestamp').reset_index(drop=True)

    df['date'] = df['timestamp'].dt.date
    df['hour'] = df['timestamp'].dt.hour
    df['year'] = df['timestamp'].dt.year

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
    tp_vol = (df['high'].values + df['low'].values + df['close'].values) / 3.0 * df['volume'].values
    df['tp_vol'] = tp_vol
    df['cum_tp_vol'] = df.groupby('date')['tp_vol'].cumsum()
    df['cum_vol'] = df.groupby('date')['volume'].cumsum()
    cum_vol_vals = df['cum_vol'].values
    cum_vol_vals[cum_vol_vals == 0] = 1.0
    df['daily_vwap'] = df['cum_tp_vol'].values / cum_vol_vals
    daily_vwap = df['daily_vwap'].values

    pip_size = 0.10
    total_friction = (2.5 + 1.0) * pip_size

    def simulate_original(is_prop=False, mode=0, start_date=None, end_date=None, init_bal=100.0):
        df_sub = df.copy()
        if start_date and end_date:
            df_sub = df_sub[(df_sub['timestamp'] >= pd.to_datetime(start_date, utc=True)) & (df_sub['timestamp'] <= pd.to_datetime(end_date, utc=True))].reset_index(drop=True)

        closes = df_sub['close'].values
        highs = df_sub['high'].values
        lows = df_sub['low'].values
        hours = df_sub['hour'].values
        h1_closes = df_sub['h1_close'].values
        h1_ema21s = df_sub['h1_ema21'].values
        h1_ema50s = df_sub['h1_ema50'].values
        m5_ema21s = df_sub['m5_ema21'].values
        daily_vwaps = df_sub['daily_vwap'].values
        n = len(df_sub)

        balance = init_bal
        last_trade_bar = -10
        records = []

        for i in range(50, n):
            hour = hours[i]
            if not (6 <= hour < 17): continue # Original 06:00 - 17:00 UTC Killzone
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
            c_vwap = daily_vwaps[idx]
            m5_close = closes[idx]

            if is_prop:
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
                sl_dist = np.clip((entry - (recent_3_low - 0.50)) / pip_size, 15.0, 80.0) * pip_size # Original 15 pip min SL
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

            ticket_risk = (balance * 0.01) / 3.0 if init_bal >= 1000.0 else 1.0 / 3.0
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
                        elif bh <= tp2:
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
        net_profit = balance - init_bal
        win_rate = (tp1_cnt / total_setups * 100.0) if total_setups > 0 else 0

        gross_profit = df_r[df_r['pnl'] > 0]['pnl'].sum() if total_setups > 0 else 0
        gross_loss = abs(df_r[df_r['pnl'] < 0]['pnl'].sum()) if total_setups > 0 else 0
        profit_factor = gross_profit / (gross_loss + 1e-9)

        return total_setups, balance, net_profit, win_rate, profit_factor, tp1_cnt, tp2_cnt, tp3_cnt, sl_cnt

    print("=========================================================================================")
    print(" ORIGINAL ENGINES COMPARISON MATRIX (BEFORE EXTRA 08-16 UTC / 20-PIP MIN SL FILTERING)")
    print("=========================================================================================\n")

    # August 1 - 17 Period ($100 Deposit)
    p_m0_aug = simulate_original(is_prop=False, mode=0, start_date='2026-08-01', end_date='2026-08-17 23:59:59', init_bal=100.0)
    p_m3_aug = simulate_original(is_prop=False, mode=3, start_date='2026-08-01', end_date='2026-08-17 23:59:59', init_bal=100.0)
    pr_m0_aug = simulate_original(is_prop=True, mode=0, start_date='2026-08-01', end_date='2026-08-17 23:59:59', init_bal=100.0)
    pr_m3_aug = simulate_original(is_prop=True, mode=3, start_date='2026-08-01', end_date='2026-08-17 23:59:59', init_bal=100.0)

    print("--- 1. AUGUST 1, 2026 - AUGUST 17, 2026 ($100 DEPOSIT) ---")
    print(f" A. Original Personal Engine (Fixed SL - Mode 0) : Bal: ${p_m0_aug[1]:.2f} | Net: +${p_m0_aug[2]:.2f} (+{p_m0_aug[2]:.2f}%) | Setups: {p_m0_aug[0]} | WR: {p_m0_aug[3]:.1f}% | PF: {p_m0_aug[4]:.2f} | TP1:{p_m0_aug[5]} TP2:{p_m0_aug[6]} TP3:{p_m0_aug[7]} SL:{p_m0_aug[8]}")
    print(f" B. Original Personal Engine (Trailing - Mode 3) : Bal: ${p_m3_aug[1]:.2f} | Net: +${p_m3_aug[2]:.2f} (+{p_m3_aug[2]:.2f}%) | Setups: {p_m3_aug[0]} | WR: {p_m3_aug[3]:.1f}% | PF: {p_m3_aug[4]:.2f} | TP1:{p_m3_aug[5]} TP2:{p_m3_aug[6]} TP3:{p_m3_aug[7]} SL:{p_m3_aug[8]}")
    print(f" C. Original Prop Firm Engine (Fixed SL - Mode 0): Bal: ${pr_m0_aug[1]:.2f} | Net: +${pr_m0_aug[2]:.2f} (+{pr_m0_aug[2]:.2f}%) | Setups: {pr_m0_aug[0]} | WR: {pr_m0_aug[3]:.1f}% | PF: {pr_m0_aug[4]:.2f} | TP1:{pr_m0_aug[5]} TP2:{pr_m0_aug[6]} TP3:{pr_m0_aug[7]} SL:{pr_m0_aug[8]}")
    print(f" D. Original Prop Firm Engine (Trailing - Mode 3): Bal: ${pr_m3_aug[1]:.2f} | Net: +${pr_m3_aug[2]:.2f} (+{pr_m3_aug[2]:.2f}%) | Setups: {pr_m3_aug[0]} | WR: {pr_m3_aug[3]:.1f}% | PF: {pr_m3_aug[4]:.2f} | TP1:{pr_m3_aug[5]} TP2:{pr_m3_aug[6]} TP3:{pr_m3_aug[7]} SL:{pr_m3_aug[8]}\n")

    # 5-Year Full Benchmark ($10,000 Deposit)
    p_m0_5y = simulate_original(is_prop=False, mode=0, init_bal=10000.0)
    pr_m0_5y = simulate_original(is_prop=True, mode=0, init_bal=10000.0)

    print("--- 2. 5-YEAR MASTER BENCHMARK (2021 - 2026, $10,000 STARTING DEPOSIT) ---")
    print(f" A. Original Personal Engine (Pure H1 Trend + FVG Sweep):")
    print(f"    - Net Profit ($) : +${p_m0_5y[2]:,.2f} USD")
    print(f"    - Total Setups   : {p_m0_5y[0]} Setups ({p_m0_5y[0]*3} Tickets)")
    print(f"    - Win Rate (%)   : {p_m0_5y[3]:.2f}% | Profit Factor: {p_m0_5y[4]:.2f}\n")

    print(f" B. Original Prop Firm Engine (Personal + Daily VWAP Filter):")
    print(f"    - Net Profit ($) : +${pr_m0_5y[2]:,.2f} USD")
    print(f"    - Total Setups   : {pr_m0_5y[0]} Setups ({pr_m0_5y[0]*3} Tickets)")
    print(f"    - Win Rate (%)   : {pr_m0_5y[3]:.2f}% (UP FROM {p_m0_5y[3]:.2f}%!) | Profit Factor: {pr_m0_5y[4]:.2f}\n")

if __name__ == "__main__":
    run_original_engines_comparison()
