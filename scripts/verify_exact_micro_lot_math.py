"""
Exact Step-by-Step Mathematical Verification of 0.01 Micro-Lot Execution on $20 Capital
"""

import sys
from pathlib import Path
import pandas as pd
import numpy as np

def verify_micro_lot_math():
    proc_5m_path = Path("data/processed/xau_5m_5y.parquet")
    if not proc_5m_path.exists():
        print("[ERROR] 5m dataset missing!")
        return

    df = pd.read_parquet(proc_5m_path)
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    df = df.sort_values('timestamp').reset_index(drop=True)

    df_sub = df[(df['timestamp'] >= pd.to_datetime('2026-08-01', utc=True)) & (df['timestamp'] <= pd.to_datetime('2026-08-17 23:59:59', utc=True))].reset_index(drop=True)

    closes = df_sub['close'].values
    highs = df_sub['high'].values
    lows = df_sub['low'].values
    hours = df_sub['timestamp'].dt.hour.values

    # H1 Trend
    df_h1 = df_sub.resample('1h', on='timestamp').agg({'open':'first','high':'max','low':'min','close':'last'}).dropna().reset_index()
    df_h1['h1_ema21'] = df_h1['close'].ewm(span=21, adjust=False).mean()
    df_h1['h1_ema50'] = df_h1['close'].ewm(span=50, adjust=False).mean()
    df_sub['h1_time'] = df_sub['timestamp'].dt.floor('1h')
    df_sub = pd.merge_asof(df_sub, df_h1[['timestamp','h1_ema21','h1_ema50','close']].rename(columns={'timestamp':'h1_time','close':'h1_close'}), on='h1_time', direction='backward')

    h1_closes = df_sub['h1_close'].values
    h1_ema21s = df_sub['h1_ema21'].values
    h1_ema50s = df_sub['h1_ema50'].values

    df_sub['m5_ema21'] = df_sub['close'].ewm(span=21, adjust=False).mean()
    m5_ema21s = df_sub['m5_ema21'].values

    pip_size = 0.10
    total_friction = (2.5 + 1.0) * pip_size
    n = len(df_sub)

    balance = 20.0
    last_trade_bar = -10
    trade_logs = []

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

        # 0.01 Lot per Ticket on Gold: $1.00 per $1.00 move in Gold price
        risk_per_ticket_usd = sl_dist * 1.0 # 0.01 lot value
        
        t1_hit, t2_hit, t3_hit = False, False, False
        t1_pnl, t2_pnl, t3_pnl = -risk_per_ticket_usd, -risk_per_ticket_usd, -risk_per_ticket_usd

        for k in range(i, min(i + 36, n)):
            bh, bl = highs[k], lows[k]
            if direction == "BUY":
                if not t1_hit:
                    if bl <= sl: break
                    elif bh >= tp1: t1_hit = True; t1_pnl = risk_per_ticket_usd * 1.0
                if t1_hit and not t2_hit:
                    if bl <= sl: break
                    elif bh >= tp2: t2_hit = True; t2_pnl = risk_per_ticket_usd * 2.0
                if t2_hit and not t3_hit:
                    if bl <= sl: break
                    elif bh >= tp3: t3_hit = True; t3_pnl = risk_per_ticket_usd * 3.0; last_bar = k; break
            else:
                if not t1_hit:
                    if bh >= sl: break
                    elif bl <= tp1: t1_hit = True; t1_pnl = risk_per_ticket_usd * 1.0
                if t1_hit and not t2_hit:
                    if bh >= sl: break
                    elif bl <= tp2: t2_hit = True; t2_pnl = risk_per_ticket_usd * 2.0
                if t2_hit and not t3_hit:
                    if bh >= sl: break
                    elif bl <= tp3: t3_hit = True; t3_pnl = risk_per_ticket_usd * 3.0; last_bar = k; break

        setup_pnl = t1_pnl + t2_pnl + t3_pnl
        start_bal = balance
        balance += setup_pnl
        trade_logs.append({
            'num': len(trade_logs) + 1,
            'direction': direction,
            'sl_dist': sl_dist,
            'risk_usd': risk_per_ticket_usd * 3.0,
            'pnl': setup_pnl,
            'start_bal': start_bal,
            'end_bal': balance
        })

    df_trades = pd.DataFrame(trade_logs)
    print("=========================================================================================")
    print(" STEP-BY-STEP MATHEMATICAL PROOF OF 0.01 MICRO-LOT EXECUTION ON GOLD ($20 DEPOSIT)")
    print("=========================================================================================\n")

    print(f" Total Setups Evaluated : {len(df_trades)} Setups")
    print(f" Starting Balance       : ${df_trades['start_bal'].iloc[0]:.2f} USD")
    print(f" Final Balance          : ${df_trades['end_bal'].iloc[-1]:,.2f} USD")
    print(f" Net Cash Profit        : +${df_trades['pnl'].sum():,.2f} USD\n")

    print(" First 5 Trade Executions (Trade-by-Trade Math):")
    for row in df_trades.head(5).itertuples():
        print(f"   Trade #{row.num} ({row.direction}): SL Dist: ${row.sl_dist:.2f} | Setup Risk: ${row.risk_usd:.2f} | Setup PnL: +${row.pnl:.2f} | Bal: ${row.start_bal:.2f} -> ${row.end_bal:.2f}")

if __name__ == "__main__":
    verify_micro_lot_math()
