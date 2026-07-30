#!/usr/bin/env python3
"""
simulate_2to1_rr_grid.py - 2:1 R:R Ratio Grid Experiment ($4.00 TP vs $2.00 SL)

Simulates yesterday's price action (July 29, 2026) under 2:1 R:R ($40 TP / $20 SL):
- Initial SL = $2.00/oz ($20 risk on 0.1 lot)
- Initial TP = $4.00/oz ($40 target on 0.1 lot) -> 2:1 R:R Ratio
- NO Trailing Stop | NO $20 Profit Lock | Excludes FOMC News Window (18:00 - 20:00 UTC)
"""

import sys
import os
sys.path.insert(0, os.path.abspath("."))
import pandas as pd
from datetime import datetime, timezone, timedelta
import MetaTrader5 as mt5

def run_2to1_rr_simulation():
    print("==========================================================================================")
    print("  SIMULATION AUDIT: 2:1 R:R RATIO ($4.00 TP vs $2.00 SL)")
    print("  Comparing 2:1 R:R ($40 TP) vs 2.5:1 R:R ($50 TP) across all filtering configurations")
    print("==========================================================================================")

    if not mt5.initialize():
        print("[ERROR] MetaTrader 5 terminal not connected.")
        return

    symbol = "XAUUSDz"
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

    # 1. Fetch M15 Trend (EMA 20 vs EMA 50)
    m15_rates = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_M15, today_start - timedelta(days=2), today_start + timedelta(days=1))
    df_m15 = pd.DataFrame(m15_rates)
    df_m15["time_dt"] = pd.to_datetime(df_m15["time"], unit="s", utc=True)
    df_m15["ema20"] = df_m15["close"].ewm(span=20, adjust=False).mean()
    df_m15["ema50"] = df_m15["close"].ewm(span=50, adjust=False).mean()

    def get_m15_trend(t_dt):
        sub = df_m15[df_m15["time_dt"] <= t_dt]
        if sub.empty:
            return "FLAT"
        last = sub.iloc[-1]
        return "UPTREND" if last["ema20"] > last["ema50"] else "DOWNTREND"

    # 2. Raw Base Signals outside FOMC
    deals = mt5.history_deals_get(today_start, datetime.now(timezone.utc) + timedelta(days=1)) or []
    bot_deals = [d._asdict() for d in deals if (d.magic == 1001 or "CAND-LIVE" in str(d.comment)) and d.entry == 0]

    filtered_deals = []
    for d in bot_deals:
        t_sec = d.get("time", 0)
        t_dt = datetime.fromtimestamp(t_sec, tz=timezone.utc)
        if 18 <= t_dt.hour < 20:
            continue
        filtered_deals.append(d)

    def simulate_rr(signal_list, tp_dist_usd):
        tp_count = 0
        sl_count = 0
        total_pnl = 0.0

        for deal in signal_list:
            entry_p = deal.get("price", 0.0)
            entry_t_sec = deal.get("time", 0)
            direction = "BUY" if deal.get("type") == 0 else "SELL"

            init_sl = round(entry_p - 2.00, 2) if direction == "BUY" else round(entry_p + 2.00, 2)
            init_tp = round(entry_p + tp_dist_usd, 2) if direction == "BUY" else round(entry_p - tp_dist_usd, 2)

            rates = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_M1, entry_t_sec, entry_t_sec + 7200)
            if rates is None or len(rates) == 0:
                continue

            exit_reason = None
            pnl = 0.0

            for r in rates:
                high = r["high"]
                low = r["low"]

                if direction == "BUY":
                    if low <= init_sl:
                        exit_reason = "HIT_SL"
                        pnl = -20.0
                        break
                    if high >= init_tp:
                        exit_reason = "HIT_TP"
                        pnl = tp_dist_usd * 10.0
                        break
                elif direction == "SELL":
                    if high >= init_sl:
                        exit_reason = "HIT_SL"
                        pnl = -20.0
                        break
                    if low <= init_tp:
                        exit_reason = "HIT_TP"
                        pnl = tp_dist_usd * 10.0
                        break

            if exit_reason == "HIT_TP":
                tp_count += 1
            elif exit_reason == "HIT_SL":
                sl_count += 1

            total_pnl += pnl

        total_trades = len(signal_list)
        win_rate = (tp_count / total_trades) * 100.0 if total_trades > 0 else 0.0
        gross_profit = tp_count * (tp_dist_usd * 10.0)
        gross_loss = sl_count * 20.0
        pf = round(gross_profit / gross_loss, 2) if gross_loss > 0 else 99.0

        return {
            "total_trades": total_trades,
            "tp": tp_count,
            "sl": sl_count,
            "win_rate": win_rate,
            "profit_factor": pf,
            "net_pnl": total_pnl
        }

    # Filtering Logic
    def filter_opt1(signals):
        seen = set()
        res = []
        for s in signals:
            t_sec = s.get("time", 0)
            m_key = t_sec // 60
            if m_key not in seen:
                seen.add(m_key)
                res.append(s)
        return res

    def filter_opt3(signals):
        res = []
        for s in signals:
            t_sec = s.get("time", 0)
            t_dt = datetime.fromtimestamp(t_sec, tz=timezone.utc)
            direction = "BUY" if s.get("type") == 0 else "SELL"
            trend = get_m15_trend(t_dt)
            if (direction == "BUY" and trend == "UPTREND") or (direction == "SELL" and trend == "DOWNTREND"):
                res.append(s)
        return res

    signals_base = filtered_deals
    signals_opt3 = filter_opt3(filtered_deals)

    # 2.5:1 R:R ($50 TP)
    res_25_base = simulate_rr(signals_base, tp_dist_usd=5.00)
    res_25_opt3 = simulate_rr(signals_opt3, tp_dist_usd=5.00)

    # 2:1 R:R ($40 TP)
    res_20_base = simulate_rr(signals_base, tp_dist_usd=4.00)
    res_20_opt3 = simulate_rr(signals_opt3, tp_dist_usd=4.00)

    print("==========================================================================================")
    print("  SIDE-BY-SIDE COMPARISON: 2.5:1 R:R ($50 TP) vs 2:1 R:R ($40 TP)")
    print("==========================================================================================")
    print("1. BASELINE (UNFILTERED RAW SIGNALS):")
    print(f"   - 2.5:1 R:R ($50 TP): Trades: {res_25_base['total_trades']} | TP: {res_25_base['tp']} | SL: {res_25_base['sl']} | WinRate: {res_25_base['win_rate']:.1f}% | PF: {res_25_base['profit_factor']} | Net PnL: ${res_25_base['net_pnl']:+.2f}")
    print(f"   - 2.0:1 R:R ($40 TP): Trades: {res_20_base['total_trades']} | TP: {res_20_base['tp']} | SL: {res_20_base['sl']} | WinRate: {res_20_base['win_rate']:.1f}% | PF: {res_20_base['profit_factor']} | Net PnL: ${res_20_base['net_pnl']:+.2f}\n")

    print("2. OPTION 3 (M15 TREND ALIGNMENT):")
    print(f"   - 2.5:1 R:R ($50 TP): Trades: {res_25_opt3['total_trades']} | TP: {res_25_opt3['tp']} | SL: {res_25_opt3['sl']} | WinRate: {res_25_opt3['win_rate']:.1f}% | PF: {res_25_opt3['profit_factor']} | Net PnL: ${res_25_opt3['net_pnl']:+.2f}")
    print(f"   - 2.0:1 R:R ($40 TP): Trades: {res_20_opt3['total_trades']} | TP: {res_20_opt3['tp']} | SL: {res_20_opt3['sl']} | WinRate: {res_20_opt3['win_rate']:.1f}% | PF: {res_20_opt3['profit_factor']} | Net PnL: ${res_20_opt3['net_pnl']:+.2f}")
    print("==========================================================================================")

if __name__ == "__main__":
    run_2to1_rr_simulation()
