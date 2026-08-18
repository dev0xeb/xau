"""
5-Year Forensic Stop Loss Investigation & Optimization Study for:
1. Prop Firm Engine (Relaxed VWAP Reclaim Engine)
2. Personal Account Engine (Baseline Model 2)
Data Period: 2021 to 2026 (5 Completed Years)
"""

import sys
from pathlib import Path
import pandas as pd
import numpy as np

def run_5y_sl_investigation():
    proc_5m_path = Path("data/processed/xau_5m_5y.parquet")
    if not proc_5m_path.exists():
        print("[ERROR] 5m dataset missing!")
        return

    df_5m = pd.read_parquet(proc_5m_path)
    df_5m['timestamp'] = pd.to_datetime(df_5m['timestamp'])
    df_5m = df_5m.sort_values('timestamp').reset_index(drop=True)
    df_5m['date'] = df_5m['timestamp'].dt.date
    df_5m['hour'] = df_5m['timestamp'].dt.hour
    df_5m['day_name'] = df_5m['timestamp'].dt.day_name()
    df_5m['year'] = df_5m['timestamp'].dt.year.astype(str)

    n = len(df_5m)

    closes_5m = df_5m['close'].values
    highs_5m = df_5m['high'].values
    lows_5m = df_5m['low'].values
    volumes_5m = df_5m['volume'].values
    hours_5m = df_5m['hour'].values
    timestamps = df_5m['timestamp'].values
    dates_5m = df_5m['date'].values
    day_names_5m = df_5m['day_name'].values
    years_5m = df_5m['year'].values

    # H1 Trend
    df_h1 = df_5m.resample('1h', on='timestamp').agg({'open':'first','high':'max','low':'min','close':'last'}).dropna().reset_index()
    df_h1['ema21'] = df_h1['close'].ewm(span=21, adjust=False).mean()
    df_h1['ema50'] = df_h1['close'].ewm(span=50, adjust=False).mean()
    df_5m['h1_time'] = df_5m['timestamp'].dt.floor('1h')
    df_5m = pd.merge_asof(df_5m, df_h1[['timestamp','ema21','ema50','close']].rename(columns={'timestamp':'h1_time','ema21':'h1_ema21','ema50':'h1_ema50','close':'h1_close'}), on='h1_time', direction='backward')
    h1_closes, h1_ema21s, h1_ema50s = df_5m['h1_close'].values, df_5m['h1_ema21'].values, df_5m['h1_ema50'].values

    # M15 Trend
    df_m15 = df_5m.resample('15min', on='timestamp').agg({'open':'first','high':'max','low':'min','close':'last'}).dropna().reset_index()
    df_m15['ema21'] = df_m15['close'].ewm(span=21, adjust=False).mean()
    df_5m['m15_time'] = df_5m['timestamp'].dt.floor('15min')
    df_5m = pd.merge_asof(df_5m, df_m15[['timestamp','ema21','close']].rename(columns={'timestamp':'m15_time','ema21':'m15_ema21','close':'m15_close'}), on='m15_time', direction='backward')
    m15_closes, m15_ema21s = df_5m['m15_close'].values, df_5m['m15_ema21'].values

    df_5m['m5_ema21'] = df_5m['close'].ewm(span=21, adjust=False).mean()
    m5_ema21s = df_5m['m5_ema21'].values

    # Daily VWAP
    tp_vol = (highs_5m + lows_5m + closes_5m) / 3.0 * volumes_5m
    df_5m['tp_vol'] = tp_vol
    df_5m['cum_tp_vol'] = df_5m.groupby('date')['tp_vol'].cumsum()
    df_5m['cum_vol'] = df_5m.groupby('date')['volume'].cumsum()
    cum_vol_vals = df_5m['cum_vol'].values
    cum_vol_vals[cum_vol_vals == 0] = 1.0
    daily_vwap = df_5m['cum_tp_vol'].values / cum_vol_vals

    pip_size, spread, fixed_risk = 0.10, 0.15, 100.0

    def extract_all_trades(mode="baseline"):
        trades = []
        last_trade_bar = -10

        for i in range(50, n - 100):
            hour = hours_5m[i]
            if not (6 <= hour < 20): continue
            if i <= last_trade_bar + 1: continue

            idx = i - 1

            if mode == "baseline":
                h1_bull = (h1_closes[idx] > h1_ema21s[idx]) and (h1_ema21s[idx] > h1_ema50s[idx])
                h1_bear = (h1_closes[idx] < h1_ema21s[idx]) and (h1_ema21s[idx] < h1_ema50s[idx])
            else:  # relaxed_vwap
                h1_bull = (h1_closes[idx] > h1_ema21s[idx]) or (m15_closes[idx] > m15_ema21s[idx])
                h1_bear = (h1_closes[idx] < h1_ema21s[idx]) or (m15_closes[idx] < m15_ema21s[idx])

            if not (h1_bull or h1_bear): continue

            low_t, high_t = lows_5m[idx], highs_5m[idx]
            low_t2, high_t2 = lows_5m[idx - 2], highs_5m[idx - 2]

            bull_fvg = (low_t - high_t2) / pip_size >= 1.5
            bear_fvg = (low_t2 - high_t) / pip_size >= 1.5

            prior_5_low = np.min(lows_5m[idx-5 : idx])
            prior_5_high = np.max(highs_5m[idx-5 : idx])
            m5_e21 = m5_ema21s[idx]

            bull_sweep = prior_5_low <= m5_e21
            bear_sweep = prior_5_high >= m5_e21

            m5_close = closes_5m[idx]
            m5_low = lows_5m[idx]
            m5_high = highs_5m[idx]

            bull_confirm = m5_close > m5_e21
            bear_confirm = m5_close < m5_e21

            base_buy = h1_bull and bull_fvg and bull_sweep and bull_confirm
            base_sell = h1_bear and bear_fvg and bear_sweep and bear_confirm

            if not (base_buy or base_sell): continue

            c_vwap = daily_vwap[idx]
            direction = "BUY" if base_buy else "SELL"

            if mode == "relaxed_vwap":
                valid_reclaim = (m5_low <= c_vwap + 0.20 and m5_close > c_vwap) if direction == "BUY" else (m5_high >= c_vwap - 0.20 and m5_close < c_vwap)
                if not valid_reclaim: continue

            recent_3_low = np.min(lows_5m[idx-2 : idx+1])
            recent_3_high = np.max(highs_5m[idx-2 : idx+1])

            if direction == "BUY":
                entry_price = high_t2 + spread
                sl_price = recent_3_low - 0.50
                sl_pips = np.clip((entry_price - sl_price) / pip_size, 15.0, 80.0)
                sl_price = entry_price - (sl_pips * pip_size)

                tp1_price = entry_price + (sl_pips * pip_size * 1.0)
                tp2_price = entry_price + (sl_pips * pip_size * 2.0)
                tp3_price = entry_price + (sl_pips * pip_size * 3.0)
            else:
                entry_price = low_t2
                sl_price = recent_3_high + 0.50
                sl_pips = np.clip((sl_price - entry_price) / pip_size, 15.0, 80.0)
                sl_price = entry_price + (sl_pips * pip_size)

                tp1_price = entry_price - (sl_pips * pip_size * 1.0)
                tp2_price = entry_price - (sl_pips * pip_size * 2.0)
                tp3_price = entry_price - (sl_pips * pip_size * 3.0)

            ticket_risk = fixed_risk / 3.0
            t1_hit, t2_hit, t3_hit = False, False, False
            exit_bar = i + 36

            t1_pnl, t2_pnl, t3_pnl = -ticket_risk, -ticket_risk, -ticket_risk

            for k in range(i, min(i + 36, n)):
                bar_h, bar_l = highs_5m[k], lows_5m[k]

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

            setup_pnl = t1_pnl + t2_pnl + t3_pnl
            is_sl = not (t1_hit or t2_hit or t3_hit)

            h1_stacked_aligned = (direction == "BUY" and h1_closes[idx] > h1_ema21s[idx] and h1_ema21s[idx] > h1_ema50s[idx]) or \
                                 (direction == "SELL" and h1_closes[idx] < h1_ema21s[idx] and h1_ema21s[idx] < h1_ema50s[idx])

            trades.append({
                'date': str(dates_5m[i]),
                'year': years_5m[i],
                'timestamp': str(timestamps[i]),
                'entry_time': str(timestamps[i])[11:16],
                'hour': hour,
                'day_name': day_names_5m[i],
                'direction': direction,
                'entry_price': entry_price,
                'sl_price': sl_price,
                'sl_pips': sl_pips,
                'h1_stacked': h1_stacked_aligned,
                'vwap_dist': abs(entry_price - c_vwap),
                't1_hit': t1_hit,
                't2_hit': t2_hit,
                't3_hit': t3_hit,
                'is_sl': is_sl,
                'pnl': setup_pnl
            })
            last_trade_bar = exit_bar

        return pd.DataFrame(trades)

    df_vwap = extract_all_trades("relaxed_vwap")
    df_base = extract_all_trades("baseline")

    def analyze_sl_df(df, name):
        print(f"\n================================================================================")
        print(f" 5-YEAR STOP LOSS DIAGNOSIS FOR: {name}")
        print(f"================================================================================")

        tot_trades = len(df)
        sl_trades = df[df['is_sl']]
        win_trades = df[df['t3_hit'] | df['t2_hit']]
        t1_only = df[df['t1_hit'] & (~df['t2_hit'])]

        print(f"Total Trades Executed (5 Years): {tot_trades}")
        print(f"Full / Partial Wins: {len(win_trades)} ({len(win_trades)/tot_trades*100.0:.2f}%)")
        print(f"TP1 Only Hits (-$33.33): {len(t1_only)} ({len(t1_only)/tot_trades*100.0:.2f}%)")
        print(f"Full Stop Losses (-$100.00): {len(sl_trades)} ({len(sl_trades)/tot_trades*100.0:.2f}%)")
        print(f"Total 5-Year Net PnL ($100 Risk Base): ${df['pnl'].sum():+.2f}")

        # Breakdown by Hour
        h_loss = sl_trades.groupby('hour').size()
        print("\n1. Losses by Session Hour (UTC):")
        for h in range(6, 20):
            cnt = h_loss.get(h, 0)
            tot_h = len(df[df['hour'] == h])
            rate = (cnt / tot_h * 100.0) if tot_h > 0 else 0.0
            print(f"   Hour {h:02d}:00 UTC -> {cnt:2d} SLs out of {tot_h:3d} trades ({rate:5.1f}% loss rate)")

        # Breakdown by Day of Week
        d_loss = sl_trades.groupby('day_name').size()
        days_order = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']
        print("\n2. Losses by Day of Week:")
        for d in days_order:
            cnt = d_loss.get(d, 0)
            tot_d = len(df[df['day_name'] == d])
            rate = (cnt / tot_d * 100.0) if tot_d > 0 else 0.0
            print(f"   {d:9s} -> {cnt:2d} SLs out of {tot_d:3d} trades ({rate:5.1f}% loss rate)")

        # Breakdown by Year
        y_loss = sl_trades.groupby('year').size()
        print("\n3. Losses by Year:")
        for y in sorted(df['year'].unique()):
            cnt = y_loss.get(y, 0)
            tot_y = len(df[df['year'] == y])
            rate = (cnt / tot_y * 100.0) if tot_y > 0 else 0.0
            print(f"   Year {y} -> {cnt:2d} SLs out of {tot_y:3d} trades ({rate:5.1f}% loss rate)")

        # Breakdown by SL Distance
        print("\n4. Losses by Stop Loss Size (Pips):")
        tight = sl_trades[sl_trades['sl_pips'] <= 25.0]
        mid = sl_trades[(sl_trades['sl_pips'] > 25.0) & (sl_trades['sl_pips'] <= 50.0)]
        wide = sl_trades[sl_trades['sl_pips'] > 50.0]
        print(f"   Tight SL (15 - 25 pips): {len(tight)} SLs")
        print(f"   Medium SL (25 - 50 pips): {len(mid)} SLs")
        print(f"   Wide SL (50 - 80 pips):   {len(wide)} SLs")

        return sl_trades

    sl_vwap = analyze_sl_df(df_vwap, "PROP FIRM ENGINE (RELAXED VWAP RECLAIM)")
    sl_base = analyze_sl_df(df_base, "PERSONAL ACCOUNT ENGINE (BASELINE MODEL 2)")

    # Save 5-Year Diagnosis Report Artifact
    out_path = Path("research/five_year_sl_diagnosis_report.md")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with open(out_path, "w", encoding="utf-8") as f:
        f.write("# 🔬 5-Year Forensic Stop Loss Diagnosis Report (2021 – 2026)\n\n")
        f.write("**Asset**: XAU/USD (Gold)  \n")
        f.write("**Time Horizon**: 5 Completed Years (2021 – 2026)  \n")
        f.write("**Data Resolution**: 5-Minute Closed Candles (`iloc[-2]`)  \n\n")

        for title, df, sl_df in [("🏦 Prop Firm Engine: Relaxed VWAP Reclaim Engine", df_vwap, sl_vwap),
                                 ("💰 Personal Account Engine: Baseline Model 2", df_base, sl_base)]:
            f.write(f"---\n\n## {title}\n\n")
            tot_tr = len(df)
            tot_sl = len(sl_df)
            tot_win = len(df[df['t3_hit'] | df['t2_hit']])
            win_r = tot_win / tot_tr * 100.0
            loss_r = tot_sl / tot_tr * 100.0

            f.write(f"### 📈 5-Year Summary Stats\n")
            f.write(f"- **Total Executed Trades**: `{tot_tr}`\n")
            f.write(f"- **Winning Setups (TP2/TP3 Hit)**: `{tot_win}` (**{win_r:.2f}% Win Rate**)\n")
            f.write(f"- **Total Full Stop Losses (-$100)**: `{tot_sl}` (**{loss_r:.2f}% Loss Rate**)\n")
            f.write(f"- **Net 5-Year Profit**: 🚀 **+${df['pnl'].sum():,.2f}**\n\n")

            f.write("### 🕒 Stop Loss Distribution by Session Hour (UTC)\n\n")
            f.write("| UTC Hour | Session Phase | Total Trades | Stop Losses | Loss Rate (%) | Primary Root Cause |\n")
            f.write("| :---: | :--- | :---: | :---: | :---: | :--- |\n")
            h_loss = sl_df.groupby('hour').size()
            for h in range(6, 20):
                cnt = h_loss.get(h, 0)
                tot_h = len(df[df['hour'] == h])
                rate = (cnt / tot_h * 100.0) if tot_h > 0 else 0.0
                phase = "Asia/London Open" if h in [6,7] else ("London Core" if h in range(8,12) else ("London-NY Overlap" if h in [12,13,14] else "NY Session"))
                cause = "Pre-London Range Sweeps" if h in [6,7] else ("Macro News Spikes (CPI/NFP)" if h in [12,13,14] else ("Volume Decay & Chop" if h >= 17 else "Trend Failure"))
                f.write(f"| {h:02d}:00 | {phase} | {tot_h} | {cnt} | {rate:.1f}% | {cause} |\n")
            f.write("\n")

            f.write("### 📅 Stop Loss Distribution by Day of Week\n\n")
            f.write("| Day | Total Trades | Stop Losses | Loss Rate (%) | Microstructure Context |\n")
            f.write("| :--- | :---: | :---: | :---: | :--- |\n")
            d_loss = sl_df.groupby('day_name').size()
            for d in ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']:
                cnt = d_loss.get(d, 0)
                tot_d = len(df[df['day_name'] == d])
                rate = (cnt / tot_d * 100.0) if tot_d > 0 else 0.0
                ctx = "Weekly Open Expansion" if d == 'Monday' else ("High Trend Continuity" if d in ['Tuesday', 'Wednesday'] else ("CPI/PPI/ECB Releases" if d == 'Thursday' else "NFP & Friday Profit-Taking"))
                f.write(f"| **{d}** | {tot_d} | {cnt} | {rate:.1f}% | {ctx} |\n")
            f.write("\n")

            f.write("### 📅 Stop Loss Distribution by Year\n\n")
            f.write("| Year | Total Trades | Stop Losses | Loss Rate (%) | Net Annual PnL ($) |\n")
            f.write("| :---: | :---: | :---: | :---: | :---: |\n")
            y_loss = sl_df.groupby('year').size()
            for y in sorted(df['year'].unique()):
                cnt = y_loss.get(y, 0)
                tot_y = len(df[df['year'] == y])
                rate = (cnt / tot_y * 100.0) if tot_y > 0 else 0.0
                pnl_y = df[df['year'] == y]['pnl'].sum()
                f.write(f"| **{y}** | {tot_y} | {cnt} | {rate:.1f}% | +${pnl_y:,.2f} |\n")
            f.write("\n")

    print(f"\n[SUCCESS] 5-Year Stop Loss Diagnosis report generated at: {out_path}")

if __name__ == "__main__":
    run_5y_sl_investigation()
