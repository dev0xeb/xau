"""
Empirical Comparison: Fixed SL vs Breakeven+5Pips vs TP1 Price SL Trailing
for Model 2 (Personal Engine & Prop Firm Engine) on 2026 Out-of-Sample Data.
"""

import sys
from pathlib import Path
import pandas as pd
import numpy as np

def run_trailing_sl_experiment():
    proc_5m_path = Path("data/processed/xau_5m_5y.parquet")
    if not proc_5m_path.exists():
        print("[ERROR] 5m dataset missing!")
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

    # H1 Trend (60 min)
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

    def simulate_trailing_mode(is_prop=False, trailing_mode="FIXED"):
        records = []
        last_trade_bar = -10

        for i in range(50, n):
            hour = hours[i]
            if not (6 <= hour < 17): continue
            if i <= last_trade_bar + 1: continue
            if years[i] != 2026: continue

            idx = i - 1
            htf_bull = (h1_closes[idx] > h1_ema21s[idx]) and (h1_ema21s[idx] > h1_ema50s[idx])
            htf_bear = (h1_closes[idx] < h1_ema21s[idx]) and (h1_ema21s[idx] < h1_ema50s[idx])

            if not (htf_bull or htf_bear): continue

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

            ticket_risk = 100.0 / 3.0
            t1_hit, t2_hit, t3_hit = False, False, False
            t1_pnl, t2_pnl, t3_pnl = -ticket_risk, -ticket_risk, -ticket_risk
            exit_bar = i + 36

            # Dynamic SL per ticket
            sl_t1 = sl_price
            sl_t2 = sl_price
            sl_t3 = sl_price

            for k in range(i, min(i + 36, n)):
                bar_h, bar_l = highs[k], lows[k]

                if direction == "BUY":
                    # Check Ticket 1
                    if not t1_hit:
                        if bar_l <= sl_t1:
                            t1_hit = False
                            t1_pnl = -ticket_risk
                        elif bar_h >= tp1_price:
                            t1_hit = True
                            t1_pnl = ticket_risk * 1.0
                            # Adjust SL for T2 and T3 if trailing mode enabled
                            if trailing_mode == "BE_PLUS_5":
                                be_sl = entry_price + 0.50  # +5 pips
                                sl_t2 = max(sl_t2, be_sl)
                                sl_t3 = max(sl_t3, be_sl)
                            elif trailing_mode == "TP1_PRICE":
                                sl_t2 = max(sl_t2, tp1_price)
                                sl_t3 = max(sl_t3, tp1_price)

                    # Check Ticket 2
                    if not t2_hit:
                        if bar_l <= sl_t2:
                            if t1_hit and trailing_mode == "BE_PLUS_5":
                                t2_pnl = (0.50 / (sl_pips * pip_size)) * ticket_risk
                            elif t1_hit and trailing_mode == "TP1_PRICE":
                                t2_pnl = ticket_risk * 1.0
                            else:
                                t2_pnl = -ticket_risk
                            t2_hit = False
                        elif bar_h >= tp2_price:
                            t2_hit = True
                            t2_pnl = ticket_risk * 2.0

                    # Check Ticket 3
                    if not t3_hit:
                        if bar_l <= sl_t3:
                            if t1_hit and trailing_mode == "BE_PLUS_5":
                                t3_pnl = (0.50 / (sl_pips * pip_size)) * ticket_risk
                            elif t1_hit and trailing_mode == "TP1_PRICE":
                                t3_pnl = ticket_risk * 1.0
                            else:
                                t3_pnl = -ticket_risk
                            t3_hit = False
                        elif bar_h >= tp3_price:
                            t3_hit = True
                            t3_pnl = ticket_risk * 3.0
                            exit_bar = k
                            break
                else: # SELL
                    if not t1_hit:
                        if bar_h >= sl_t1:
                            t1_hit = False
                            t1_pnl = -ticket_risk
                        elif bar_l <= tp1_price:
                            t1_hit = True
                            t1_pnl = ticket_risk * 1.0
                            if trailing_mode == "BE_PLUS_5":
                                be_sl = entry_price - 0.50
                                sl_t2 = min(sl_t2, be_sl)
                                sl_t3 = min(sl_t3, be_sl)
                            elif trailing_mode == "TP1_PRICE":
                                sl_t2 = min(sl_t2, tp1_price)
                                sl_t3 = min(sl_t3, tp1_price)

                    if not t2_hit:
                        if bar_h >= sl_t2:
                            if t1_hit and trailing_mode == "BE_PLUS_5":
                                t2_pnl = (0.50 / (sl_pips * pip_size)) * ticket_risk
                            elif t1_hit and trailing_mode == "TP1_PRICE":
                                t2_pnl = ticket_risk * 1.0
                            else:
                                t2_pnl = -ticket_risk
                            t2_hit = False
                        elif bar_l <= tp2_price:
                            t2_hit = True
                            t2_pnl = ticket_risk * 2.0

                    if not t3_hit:
                        if bar_h >= sl_t3:
                            if t1_hit and trailing_mode == "BE_PLUS_5":
                                t3_pnl = (0.50 / (sl_pips * pip_size)) * ticket_risk
                            elif t1_hit and trailing_mode == "TP1_PRICE":
                                t3_pnl = ticket_risk * 1.0
                            else:
                                t3_pnl = -ticket_risk
                            t3_hit = False
                        elif bar_l <= tp3_price:
                            t3_hit = True
                            t3_pnl = ticket_risk * 3.0
                            exit_bar = k
                            break

            setup_pnl = t1_pnl + t2_pnl + t3_pnl
            records.append({
                'pnl': setup_pnl,
                't1_hit': int(t1_hit),
                't2_hit': int(t2_hit),
                't3_hit': int(t3_hit)
            })
            last_trade_bar = exit_bar

        df_rec = pd.DataFrame(records)
        total_setups = len(df_rec)
        total_pnl = df_rec['pnl'].sum()
        tp1_hits = df_rec['t1_hit'].sum()
        tp2_hits = df_rec['t2_hit'].sum()
        tp3_hits = df_rec['t3_hit'].sum()
        gross_profit = df_rec[df_rec['pnl'] > 0]['pnl'].sum()
        gross_loss = abs(df_rec[df_rec['pnl'] < 0]['pnl'].sum())
        profit_factor = gross_profit / (gross_loss + 1e-9)

        return total_setups, total_pnl, tp1_hits, tp2_hits, tp3_hits, profit_factor

    print("=========================================================================================")
    print(" EMPIRICAL TRAILING STOP EXPERIMENT: FIXED SL vs BE+5 PIPS vs TP1 PRICE SL TRAILING")
    print("=========================================================================================\n")

    for eng_name, is_p in [("Personal Account Engine", False), ("Prop Firm Engine", True)]:
        print(f"--- {eng_name.upper()} ---")
        s_fix, pnl_fix, t1_fix, t2_fix, t3_fix, pf_fix = simulate_trailing_mode(is_p, "FIXED")
        s_be, pnl_be, t1_be, t2_be, t3_be, pf_be = simulate_trailing_mode(is_p, "BE_PLUS_5")
        s_tp1, pnl_tp1, t1_tp1, t2_tp1, t3_tp1, pf_tp1 = simulate_trailing_mode(is_p, "TP1_PRICE")

        print(f" 1. Baseline Fixed SL:")
        print(f"    - Net PnL ($)  : +${pnl_fix:+,.2f} | Profit Factor: {pf_fix:.2f}")
        print(f"    - Target Hits  : TP1: {t1_fix} | TP2: {t2_fix} | TP3: {t3_fix}\n")

        print(f" 2. Trailing SL to BE + 5 Pips ($0.50) on TP1 Hit:")
        print(f"    - Net PnL ($)  : +${pnl_be:+,.2f} | Profit Factor: {pf_be:.2f}")
        print(f"    - Target Hits  : TP1: {t1_be} | TP2: {t2_be} | TP3: {t3_be}\n")

        print(f" 3. Trailing SL to TP1 Price on TP1 Hit:")
        print(f"    - Net PnL ($)  : +${pnl_tp1:+,.2f} | Profit Factor: {pf_tp1:.2f}")
        print(f"    - Target Hits  : TP1: {t1_tp1} | TP2: {t2_tp1} | TP3: {t3_tp1}\n")

if __name__ == "__main__":
    run_trailing_sl_experiment()
