"""
Empirical Comparison: 45-Minute (M45) HTF Trend Filter vs 1-Hour (H1) HTF Trend Filter 
for Model 2 (M5 Scalp Hybrid Strategy Engine) on XAU/USD.
"""

import sys
from pathlib import Path
import pandas as pd
import numpy as np

def run_htf_comparison():
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

    # M45 Trend (45 min)
    df_m45 = df.resample('45min', on='timestamp').agg({'open':'first','high':'max','low':'min','close':'last'}).dropna().reset_index()
    df_m45['m45_ema21'] = df_m45['close'].ewm(span=21, adjust=False).mean()
    df_m45['m45_ema50'] = df_m45['close'].ewm(span=50, adjust=False).mean()
    df['m45_time'] = df['timestamp'].dt.floor('45min')
    df = pd.merge_asof(df, df_m45[['timestamp','m45_ema21','m45_ema50','close']].rename(columns={'timestamp':'m45_time','close':'m45_close'}), on='m45_time', direction='backward')
    m45_closes, m45_ema21s, m45_ema50s = df['m45_close'].values, df['m45_ema21'].values, df['m45_ema50'].values

    # M30 Trend (30 min)
    df_m30 = df.resample('30min', on='timestamp').agg({'open':'first','high':'max','low':'min','close':'last'}).dropna().reset_index()
    df_m30['m30_ema21'] = df_m30['close'].ewm(span=21, adjust=False).mean()
    df_m30['m30_ema50'] = df_m30['close'].ewm(span=50, adjust=False).mean()
    df['m30_time'] = df['timestamp'].dt.floor('30min')
    df = pd.merge_asof(df, df_m30[['timestamp','m30_ema21','m30_ema50','close']].rename(columns={'timestamp':'m30_time','close':'m30_close'}), on='m30_time', direction='backward')
    m30_closes, m30_ema21s, m30_ema50s = df['m30_close'].values, df['m30_ema21'].values, df['m30_ema50'].values

    df['m5_ema21'] = df['close'].ewm(span=21, adjust=False).mean()
    m5_ema21s = df['m5_ema21'].values

    pip_size = 0.10
    total_friction = (2.5 + 1.0) * pip_size

    def evaluate_strategy(htf_type="H1"):
        records = []
        last_trade_bar = -10

        for i in range(50, n):
            hour = hours[i]
            if not (6 <= hour < 17): continue
            if i <= last_trade_bar + 1: continue

            idx = i - 1
            if htf_type == "H1":
                htf_bull = (h1_closes[idx] > h1_ema21s[idx]) and (h1_ema21s[idx] > h1_ema50s[idx])
                htf_bear = (h1_closes[idx] < h1_ema21s[idx]) and (h1_ema21s[idx] < h1_ema50s[idx])
            elif htf_type == "M45":
                htf_bull = (m45_closes[idx] > m45_ema21s[idx]) and (m45_ema21s[idx] > m45_ema50s[idx])
                htf_bear = (m45_closes[idx] < m45_ema21s[idx]) and (m45_ema21s[idx] < m45_ema50s[idx])
            else:
                htf_bull = (m30_closes[idx] > m30_ema21s[idx]) and (m30_ema21s[idx] > m30_ema50s[idx])
                htf_bear = (m30_closes[idx] < m30_ema21s[idx]) and (m30_ema21s[idx] < m30_ema50s[idx])

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
            m5_close = closes[idx]

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
            exit_bar = i + 36

            t1_pnl, t2_pnl, t3_pnl = -ticket_risk, -ticket_risk, -ticket_risk

            for k in range(i, min(i + 36, n)):
                bar_h, bar_l = highs[k], lows[k]
                if direction == "BUY":
                    if bar_l <= sl_price:
                        exit_bar = k
                        break
                    if not t1_hit and bar_h >= tp1_price:
                        t1_hit = True
                        t1_pnl = ticket_risk * 1.0
                    if t1_hit and not t2_hit and bar_h >= tp2_price:
                        t2_hit = True
                        t2_pnl = ticket_risk * 2.0
                    if t2_hit and not t3_hit and bar_h >= tp3_price:
                        t3_hit = True
                        t3_pnl = ticket_risk * 3.0
                        exit_bar = k
                        break
                else:
                    if bar_h >= sl_price:
                        exit_bar = k
                        break
                    if not t1_hit and bar_l <= tp1_price:
                        t1_hit = True
                        t1_pnl = ticket_risk * 1.0
                    if t1_hit and not t2_hit and bar_l <= tp2_price:
                        t2_hit = True
                        t2_pnl = ticket_risk * 2.0
                    if t2_hit and not t3_hit and bar_l <= tp3_price:
                        t3_hit = True
                        t3_pnl = ticket_risk * 3.0
                        exit_bar = k
                        break

            records.append({
                'year': years[i],
                'pnl': t1_pnl + t2_pnl + t3_pnl,
                'is_win': int(t2_hit or t3_hit)
            })
            last_trade_bar = exit_bar

        df_rec = pd.DataFrame(records)
        df_2026 = df_rec[df_rec['year'] == 2026]

        total_trades = len(df_2026)
        total_pnl = df_2026['pnl'].sum()
        win_rate = (df_2026['is_win'].sum() / total_trades) * 100.0 if total_trades > 0 else 0
        gross_profit = df_2026[df_2026['pnl'] > 0]['pnl'].sum()
        gross_loss = abs(df_2026[df_2026['pnl'] < 0]['pnl'].sum())
        profit_factor = gross_profit / (gross_loss + 1e-9)

        return total_trades, total_pnl, win_rate, profit_factor

    print("=========================================================================================")
    print(" EMPIRICAL TEST: 1-HOUR (H1) HTF vs 45-MINUTE (M45) HTF TREND FILTER")
    print(" Evaluated under Exness Friction on 2026 Out-of-Sample Data")
    print("=========================================================================================\n")

    h1_trades, h1_pnl, h1_win, h1_pf = evaluate_strategy("H1")
    m45_trades, m45_pnl, m45_win, m45_pf = evaluate_strategy("M45")
    m30_trades, m30_pnl, m30_win, m30_pf = evaluate_strategy("M30")

    print(f" 1. Baseline H1 (60-Min) HTF Trend Filter:")
    print(f"    - Total Trades : {h1_trades} Trades")
    print(f"    - Net PnL ($)  : +${h1_pnl:+,.2f}")
    print(f"    - Win Rate (%) : {h1_win:.2f}%")
    print(f"    - Profit Factor: {h1_pf:.2f}\n")

    print(f" 2. Alternative M45 (45-Min) HTF Trend Filter:")
    print(f"    - Total Trades : {m45_trades} Trades")
    print(f"    - Net PnL ($)  : +${m45_pnl:+,.2f}")
    print(f"    - Win Rate (%) : {m45_win:.2f}%")
    print(f"    - Profit Factor: {m45_pf:.2f}\n")

    print(f" 3. Alternative M30 (30-Min) HTF Trend Filter:")
    print(f"    - Total Trades : {m30_trades} Trades")
    print(f"    - Net PnL ($)  : +${m30_pnl:+,.2f}")
    print(f"    - Win Rate (%) : {m30_win:.2f}%")
    print(f"    - Profit Factor: {m30_pf:.2f}\n")

if __name__ == "__main__":
    run_htf_comparison()
