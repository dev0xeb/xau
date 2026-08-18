"""
Detailed Lot Sizing Audit for $20.00 Starting Capital (August 1 - 17, 2026)
Evaluates 3 Lot Sizing Modes on $20 Capital:
1. Fixed 1.0% Risk ($0.20 USD Risk per Setup = $0.067 per ticket)
2. Compounding 1.0% Risk (Re-invests account balance growth on every setup)
3. Micro-Lot Execution (Fixed 0.01 Lot per Ticket = 0.03 Lots per Setup)
"""

import sys
from pathlib import Path
import pandas as pd
import numpy as np

def run_20dollar_lot_sizing_audit():
    proc_5m_path = Path("data/processed/xau_5m_5y.parquet")
    if not proc_5m_path.exists():
        print("[ERROR] 5m dataset missing!")
        return

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

    closes = df_sub['close'].values
    highs = df_sub['high'].values
    lows = df_sub['low'].values
    hours = df_sub['hour'].values
    h1_closes = df_sub['h1_close'].values
    h1_ema21s = df_sub['h1_ema21'].values
    h1_ema50s = df_sub['h1_ema50'].values

    df_sub['m5_ema21'] = df_sub['close'].ewm(span=21, adjust=False).mean()
    m5_ema21s = df_sub['m5_ema21'].values

    # Daily VWAP
    tp_vol = (highs + lows + closes) / 3.0 * df_sub['volume'].values
    df_sub['tp_vol'] = tp_vol
    df_sub['cum_tp_vol'] = df_sub.groupby('date')['tp_vol'].cumsum()
    df_sub['cum_vol'] = df_sub.groupby('date')['volume'].cumsum()
    cum_vol_vals = df_sub['cum_vol'].values
    cum_vol_vals[cum_vol_vals == 0] = 1.0
    daily_vwaps = df_sub['cum_tp_vol'].values / cum_vol_vals

    pip_size = 0.10
    total_friction = (2.5 + 1.0) * pip_size
    n = len(df_sub)

    def simulate_lot_mode(is_prop=False, mode=0, lot_type='fixed_pct'):
        balance = 20.0
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

            # Determine Risk per Ticket based on Lot Sizing Mode
            if lot_type == 'fixed_pct':
                ticket_risk = 0.20 / 3.0 # Fixed $0.067 per ticket (1.0% of $20)
            elif lot_type == 'compound_pct':
                ticket_risk = (balance * 0.01) / 3.0 # Dynamic 1.0% compounding
            elif lot_type == 'micro_lots':
                # 0.01 lot per ticket = $1.00 per 1.00 USD price move on Gold
                ticket_risk = (sl_dist) * 1.0 # 0.01 lot value per ticket

            t1_hit, t2_hit, t3_hit = False, False, False
            t1_pnl, t2_pnl, t3_pnl = -ticket_risk, -ticket_risk, -ticket_risk
            sl_t3 = sl

            for k in range(i, min(i + 36, n)):
                bh, bl = highs[k], lows[k]
                if direction == "BUY":
                    if not t1_hit:
                        if bl <= sl: break
                        elif bh >= tp1: t1_hit = True; t1_pnl = ticket_risk * 1.0
                    if t1_hit and not t2_hit:
                        if bl <= sl: break
                        elif bh >= tp2: t2_hit = True; t2_pnl = ticket_risk * 2.0; sl_t3 = tp1 if mode == 3 else sl
                    if t2_hit and not t3_hit:
                        if bl <= sl_t3: t3_pnl = ticket_risk * 1.0 if mode == 3 else -ticket_risk; break
                        elif bh >= tp3: t3_hit = True; t3_pnl = ticket_risk * 3.0; last_bar = k; break
                else:
                    if not t1_hit:
                        if bh >= sl: break
                        elif bl <= tp1: t1_hit = True; t1_pnl = ticket_risk * 1.0
                    if t1_hit and not t2_hit:
                        if bh >= sl: break
                        elif bl <= tp2: t2_hit = True; t2_pnl = ticket_risk * 2.0; sl_t3 = tp1 if mode == 3 else sl
                    if t2_hit and not t3_hit:
                        if bh >= sl_t3: t3_pnl = ticket_risk * 1.0 if mode == 3 else -ticket_risk; break
                        elif bl <= tp3: t3_hit = True; t3_pnl = ticket_risk * 3.0; last_bar = k; break

            setup_pnl = t1_pnl + t2_pnl + t3_pnl
            balance += setup_pnl
            records.append({'pnl': setup_pnl, 't1': int(t1_hit)})

        df_r = pd.DataFrame(records)
        setups = len(df_r)
        wins = df_r['t1'].sum() if setups > 0 else 0
        wr = (wins / setups * 100.0) if setups > 0 else 0

        return setups, balance, balance - 20.0, wr

    print("=========================================================================================")
    print(" LOT SIZING COMPARISON FOR $20.00 STARTING CAPITAL (AUGUST 1 - 17, 2026)")
    print("=========================================================================================\n")

    for lt, name in [('fixed_pct', "Fixed 1.0% Risk ($0.20 Total Risk / Setup)"), ('compound_pct', "Compounding 1.0% Risk (Dynamic Balance Scaling)"), ('micro_lots', "Fixed Micro-Lots (0.01 Lot / Ticket = 0.03 Lots / Setup)")]:
        print(f"--- Mode: {name} ---")
        _, b_p0, p_p0, w_p0 = simulate_lot_mode(is_prop=False, mode=0, lot_type=lt)
        _, b_p3, p_p3, w_p3 = simulate_lot_mode(is_prop=False, mode=3, lot_type=lt)
        _, b_pr0, p_pr0, w_pr0 = simulate_lot_mode(is_prop=True, mode=0, lot_type=lt)
        _, b_pr3, p_pr3, w_pr3 = simulate_lot_mode(is_prop=True, mode=3, lot_type=lt)

        print(f"  1. Personal Engine (Mode 0: Fixed SL) : Final Bal: ${b_p0:,.2f} USD | Net Profit: +${p_p0:,.2f}")
        print(f"  2. Personal Engine (Mode 3: Trailing) : Final Bal: ${b_p3:,.2f} USD | Net Profit: +${p_p3:,.2f}")
        print(f"  3. Prop Engine     (Mode 0: Fixed SL) : Final Bal: ${b_pr0:,.2f} USD | Net Profit: +${p_pr0:,.2f}")
        print(f"  4. Prop Engine     (Mode 3: Trailing) : Final Bal: ${b_pr3:,.2f} USD | Net Profit: +${p_pr3:,.2f}\n")

if __name__ == "__main__":
    run_20dollar_lot_sizing_audit()
