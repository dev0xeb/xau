"""
Script to compute Top 20 Best & Worst Days, Weeks, Months, and Yearly PnL Stats for:
1. Baseline Model 2 (Personal Account Engine)
2. Relaxed VWAP Reclaim Engine (Prop Firm Engine)
"""

import sys
from pathlib import Path
import pandas as pd
import numpy as np

def run_extreme_stats():
    proc_5m_path = Path("data/processed/xau_5m_5y.parquet")
    if not proc_5m_path.exists():
        print("[ERROR] 5m dataset missing!")
        return

    df_5m = pd.read_parquet(proc_5m_path)
    df_5m['timestamp'] = pd.to_datetime(df_5m['timestamp'])
    df_5m = df_5m.sort_values('timestamp').reset_index(drop=True)
    df_5m['hour'] = df_5m['timestamp'].dt.hour
    df_5m['date'] = df_5m['timestamp'].dt.date

    n = len(df_5m)
    closes_5m = df_5m['close'].values
    highs_5m = df_5m['high'].values
    lows_5m = df_5m['low'].values
    volumes_5m = df_5m['volume'].values
    hours_5m = df_5m['hour'].values
    timestamps = df_5m['timestamp'].values

    # H1 Trend
    df_h1 = df_5m.resample('1h', on='timestamp').agg({
        'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last'
    }).dropna().reset_index()
    df_h1['ema21'] = df_h1['close'].ewm(span=21, adjust=False).mean()
    df_h1['ema50'] = df_h1['close'].ewm(span=50, adjust=False).mean()
    df_5m['h1_time'] = df_5m['timestamp'].dt.floor('1h')
    df_5m = pd.merge_asof(
        df_5m,
        df_h1[['timestamp', 'ema21', 'ema50', 'close']].rename(columns={'timestamp': 'h1_time', 'ema21': 'h1_ema21', 'ema50': 'h1_ema50', 'close': 'h1_close'}),
        on='h1_time', direction='backward'
    )
    h1_closes = df_5m['h1_close'].values
    h1_ema21s = df_5m['h1_ema21'].values
    h1_ema50s = df_5m['h1_ema50'].values

    # M15 Trend
    df_m15 = df_5m.resample('15min', on='timestamp').agg({
        'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last'
    }).dropna().reset_index()
    df_m15['ema21'] = df_m15['close'].ewm(span=21, adjust=False).mean()
    df_5m['m15_time'] = df_5m['timestamp'].dt.floor('15min')
    df_5m = pd.merge_asof(
        df_5m,
        df_m15[['timestamp', 'ema21', 'close']].rename(columns={'timestamp': 'm15_time', 'ema21': 'm15_ema21', 'close': 'm15_close'}),
        on='m15_time', direction='backward'
    )
    m15_closes = df_5m['m15_close'].values
    m15_ema21s = df_5m['m15_ema21'].values

    df_5m['m5_ema21'] = df_5m['close'].ewm(span=21, adjust=False).mean()
    m5_ema21s = df_5m['m5_ema21'].values

    # Daily VWAP
    typical_prices = (highs_5m + lows_5m + closes_5m) / 3.0
    tp_vol = typical_prices * volumes_5m
    df_5m['tp_vol'] = tp_vol
    df_5m['cum_tp_vol'] = df_5m.groupby('date')['tp_vol'].cumsum()
    df_5m['cum_vol'] = df_5m.groupby('date')['volume'].cumsum()
    cum_vol_vals = df_5m['cum_vol'].values
    cum_vol_vals[cum_vol_vals == 0] = 1.0
    daily_vwap = df_5m['cum_tp_vol'].values / cum_vol_vals

    pip_size = 0.10
    spread = 0.15

    def get_trades(mode="baseline", fixed_risk=100.0):
        trades = []
        last_trade_bar = -10
        balance = 10000.0

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

            low_t = lows_5m[idx]
            high_t = highs_5m[idx]
            low_t2 = lows_5m[idx - 2]
            high_t2 = highs_5m[idx - 2]

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
                bar_h = highs_5m[k]
                bar_l = lows_5m[k]

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
                else:  # SELL
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
            balance += setup_pnl
            trades.append({
                'timestamp': timestamps[i],
                'date': str(timestamps[i])[:10],
                'year': timestamps[i].astype('datetime64[Y]').astype(str),
                'month': str(timestamps[i])[:7],
                'week': str(pd.to_datetime(timestamps[i]).to_period('W')),
                'pnl': setup_pnl
            })
            last_trade_bar = exit_bar

        return pd.DataFrame(trades)

    df_base = get_trades("baseline", fixed_risk=100.0)
    df_vwap = get_trades("relaxed_vwap", fixed_risk=100.0)

    def analyze_df(df, name):
        print(f"\n================================================================================")
        print(f"  ANALYSIS FOR: {name}")
        print(f"================================================================================")

        # Daily
        daily_pnl = df.groupby('date')['pnl'].sum().reset_index()
        daily_pnl_sorted = daily_pnl.sort_values('pnl', ascending=False).reset_index(drop=True)
        top20_best_days = daily_pnl_sorted.head(20)
        top20_worst_days = daily_pnl_sorted.tail(20).iloc[::-1].reset_index(drop=True)

        # Weekly
        weekly_pnl = df.groupby('week')['pnl'].sum().reset_index()
        weekly_pnl_sorted = weekly_pnl.sort_values('pnl', ascending=False).reset_index(drop=True)
        top20_best_weeks = weekly_pnl_sorted.head(20)
        top20_worst_weeks = weekly_pnl_sorted.tail(20).iloc[::-1].reset_index(drop=True)

        # Monthly
        monthly_pnl = df.groupby('month')['pnl'].sum().reset_index()
        monthly_pnl_sorted = monthly_pnl.sort_values('pnl', ascending=False).reset_index(drop=True)

        # Yearly
        yearly_pnl = df.groupby('year')['pnl'].sum().reset_index()

        return {
            'best_days': top20_best_days,
            'worst_days': top20_worst_days,
            'best_weeks': top20_best_weeks,
            'worst_weeks': top20_worst_weeks,
            'monthly': monthly_pnl_sorted,
            'yearly': yearly_pnl
        }

    res_base = analyze_df(df_base, "BASELINE MODEL 2 (PERSONAL ACCOUNT ENGINE)")
    res_vwap = analyze_df(df_vwap, "RELAXED VWAP RECLAIM ENGINE (PROP FIRM ENGINE)")

    # Write Markdown Report
    out_path = Path("research/extreme_pnl_stats_report.md")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with open(out_path, "w", encoding="utf-8") as f:
        f.write("# 📊 Top 20 Best & Worst Days, Weeks, Months, and Years PnL Analysis\n\n")
        f.write("**Asset**: XAU/USD (Gold)  \n")
        f.write("**Timeframe**: M5 Execution  \n")
        f.write("**Data Horizon**: 5 Completed Years (2021 – 2026)  \n")
        f.write("**Sizing Base**: $100 Flat Risk Per Setup (1.0% Base Equity)  \n\n")

        for title, res in [("🏦 Prop Firm Engine: Relaxed VWAP Reclaim Engine", res_vwap),
                          ("💰 Personal Account Engine: Baseline Model 2", res_base)]:
            f.write(f"---\n\n## {title}\n\n")

            # Yearly
            f.write("### 📅 Yearly Breakdown\n\n")
            f.write("| Year | Net PnL ($) | Total Return (% on $10k) |\n")
            f.write("| :--- | :---: | :---: |\n")
            for _, r in res['yearly'].iterrows():
                f.write(f"| **{r['year']}** | +${r['pnl']:,.2f} | +{r['pnl']/100:.2f}% |\n")
            f.write("\n")

            # Top 5 Best / Worst Months
            f.write("### 📆 Monthly PnL Summary (Best & Worst Months)\n\n")
            f.write("#### 🌟 Top 5 Best Months\n")
            f.write("| Rank | Month | Net PnL ($) |\n| :---: | :---: | :---: |\n")
            for idx, r in res['monthly'].head(5).iterrows():
                f.write(f"| #{idx+1} | {r['month']} | +${r['pnl']:,.2f} |\n")
            f.write("\n#### ⚠️ Top 5 Worst Months\n")
            f.write("| Rank | Month | Net PnL ($) |\n| :---: | :---: | :---: |\n")
            for idx, r in res['monthly'].tail(5).iloc[::-1].reset_index(drop=True).iterrows():
                f.write(f"| #{idx+1} | {r['month']} | ${r['pnl']:,.2f} |\n")
            f.write("\n")

            # Top 20 Best & Worst Weeks
            f.write("### 📊 Top 20 Best & Worst Weeks\n\n")
            f.write("| Rank | 🌟 Top 20 Best Weeks (Date & PnL) | ⚠️ Top 20 Worst Weeks (Date & PnL) |\n")
            f.write("| :---: | :--- | :--- |\n")
            for i in range(20):
                bw = res['best_weeks'].iloc[i] if i < len(res['best_weeks']) else None
                ww = res['worst_weeks'].iloc[i] if i < len(res['worst_weeks']) else None
                bw_str = f"**{bw['week']}**: +${bw['pnl']:,.2f}" if bw is not None else "-"
                ww_str = f"**{ww['week']}**: ${ww['pnl']:,.2f}" if ww is not None else "-"
                f.write(f"| #{i+1} | {bw_str} | {ww_str} |\n")
            f.write("\n")

            # Top 20 Best & Worst Days
            f.write("### 📈 Top 20 Best & Worst Days\n\n")
            f.write("| Rank | 🌟 Top 20 Best Days (Date & PnL) | ⚠️ Top 20 Worst Days (Date & PnL) |\n")
            f.write("| :---: | :--- | :--- |\n")
            for i in range(20):
                bd = res['best_days'].iloc[i] if i < len(res['best_days']) else None
                wd = res['worst_days'].iloc[i] if i < len(res['worst_days']) else None
                bd_str = f"**{bd['date']}**: +${bd['pnl']:,.2f}" if bd is not None else "-"
                wd_str = f"**{wd['date']}**: ${wd['pnl']:,.2f}" if wd is not None else "-"
                f.write(f"| #{i+1} | {bd_str} | {wd_str} |\n")
            f.write("\n")

    print(f"\n[SUCCESS] Extreme stats report generated at: {out_path}")

if __name__ == "__main__":
    run_extreme_stats()
