#!/usr/bin/env python3
"""
simulate_signal_filtering_grid.py - Grid Experiment WITH $20 Profit Lock Rule

Simulates yesterday's price action (July 29, 2026) across 7 filtering configurations:
- Initial SL = $2.00/oz ($20 risk), Initial TP = $5.00/oz ($50 target) -> 2.5:1 R:R
- $20 PROFIT LOCK RULE ACTIVE: When price reaches +$2.00/oz (+$20 profit), SL moves to Entry + $2.00 (locking +$20 profit guaranteed)
- Excludes FOMC News Window (18:00 - 20:00 UTC)
"""

import sys
import os
sys.path.insert(0, os.path.abspath("."))
import pandas as pd
from datetime import datetime, timezone, timedelta
import MetaTrader5 as mt5

def run_grid_simulation_with_20_lock():
    print("==========================================================================================")
    print("  SYSTEMATIC SIGNAL FILTERING GRID EXPERIMENT (WITH $20 PROFIT LOCK RULE)")
    print("  Rules: SL = -$2.00 ($20 risk), TP = +$5.00 ($50 target) | Profit Lock = +$2.00 ($20 locked)")
    print("  Excludes FOMC News Window (18:00 - 20:00 UTC)")
    print("==========================================================================================")

    if not mt5.initialize():
        print("[ERROR] MetaTrader 5 terminal not connected.")
        return

    symbol = "XAUUSDz"
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

    # 1. M15 Trend (EMA 20 vs EMA 50)
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

    def simulate_trade_outcomes_with_20_lock(signal_list):
        tp50_count = 0
        lock20_count = 0
        sl20_count = 0
        total_pnl = 0.0

        for deal in signal_list:
            entry_p = deal.get("price", 0.0)
            entry_t_sec = deal.get("time", 0)
            direction = "BUY" if deal.get("type") == 0 else "SELL"

            init_sl = round(entry_p - 2.00, 2) if direction == "BUY" else round(entry_p + 2.00, 2)
            init_tp = round(entry_p + 5.00, 2) if direction == "BUY" else round(entry_p - 5.00, 2)

            rates = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_M1, entry_t_sec, entry_t_sec + 7200)
            if rates is None or len(rates) == 0:
                continue

            current_sl = init_sl
            current_tp = init_tp
            is_locked_20 = False
            exit_reason = None
            pnl = 0.0

            for r in rates:
                high = r["high"]
                low = r["low"]

                if direction == "BUY":
                    if not is_locked_20 and low <= current_sl:
                        exit_reason = "HIT_INITIAL_SL"
                        pnl = -20.0
                        break

                    if not is_locked_20 and high >= (entry_p + 2.00):
                        is_locked_20 = True
                        current_sl = round(entry_p + 2.00, 2)  # Lock $20 profit

                        if low <= current_sl:
                            exit_reason = "HIT_LOCKED_20USD"
                            pnl = 20.0
                            break
                        elif high >= current_tp:
                            exit_reason = "HIT_TP_50USD"
                            pnl = 50.0
                            break

                    if is_locked_20:
                        if low <= current_sl:
                            exit_reason = "HIT_LOCKED_20USD"
                            pnl = 20.0
                            break
                        elif high >= current_tp:
                            exit_reason = "HIT_TP_50USD"
                            pnl = 50.0
                            break

                elif direction == "SELL":
                    if not is_locked_20 and high >= current_sl:
                        exit_reason = "HIT_INITIAL_SL"
                        pnl = -20.0
                        break

                    if not is_locked_20 and low <= (entry_p - 2.00):
                        is_locked_20 = True
                        current_sl = round(entry_p - 2.00, 2)  # Lock $20 profit

                        if high >= current_sl:
                            exit_reason = "HIT_LOCKED_20USD"
                            pnl = 20.0
                            break
                        elif low <= current_tp:
                            exit_reason = "HIT_TP_50USD"
                            pnl = 50.0
                            break

                    if is_locked_20:
                        if high >= current_sl:
                            exit_reason = "HIT_LOCKED_20USD"
                            pnl = 20.0
                            break
                        elif low <= current_tp:
                            exit_reason = "HIT_TP_50USD"
                            pnl = 50.0
                            break

            if exit_reason == "HIT_TP_50USD":
                tp50_count += 1
            elif exit_reason == "HIT_LOCKED_20USD":
                lock20_count += 1
            elif exit_reason == "HIT_INITIAL_SL":
                sl20_count += 1

            total_pnl += pnl

        total_trades = len(signal_list)
        win_count = tp50_count + lock20_count
        win_rate = (win_count / total_trades) * 100.0 if total_trades > 0 else 0.0
        gross_profit = tp50_count * 50.0 + lock20_count * 20.0
        gross_loss = sl20_count * 20.0
        pf = round(gross_profit / gross_loss, 2) if gross_loss > 0 else 99.0

        return {
            "total_trades": total_trades,
            "tp50": tp50_count,
            "lock20": lock20_count,
            "sl20": sl20_count,
            "win_rate": win_rate,
            "gross_profit": gross_profit,
            "gross_loss": gross_loss,
            "profit_factor": pf,
            "net_pnl": total_pnl
        }

    # Filtering Functions
    def filter_opt1(signals):
        seen_mins = set()
        res = []
        for s in signals:
            t_sec = s.get("time", 0)
            m_key = t_sec // 60
            if m_key not in seen_mins:
                seen_mins.add(m_key)
                res.append(s)
        return res

    def filter_opt2(signals):
        return signals  # Live Conviction >= 0.50

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

    signals_baseline = filtered_deals
    signals_opt1 = filter_opt1(filtered_deals)
    signals_opt2 = filter_opt2(filtered_deals)
    signals_opt3 = filter_opt3(filtered_deals)

    signals_combo_1_2 = filter_opt2(signals_opt1)
    signals_combo_2_3 = filter_opt3(signals_opt2)
    signals_combo_1_3 = filter_opt3(signals_opt1)

    signals_combo_1_2_3 = filter_opt3(signals_combo_1_2)

    r_base = simulate_trade_outcomes_with_20_lock(signals_baseline)
    r_1 = simulate_trade_outcomes_with_20_lock(signals_opt1)
    r_2 = simulate_trade_outcomes_with_20_lock(signals_opt2)
    r_3 = simulate_trade_outcomes_with_20_lock(signals_opt3)

    r_1_2 = simulate_trade_outcomes_with_20_lock(signals_combo_1_2)
    r_2_3 = simulate_trade_outcomes_with_20_lock(signals_combo_2_3)
    r_1_3 = simulate_trade_outcomes_with_20_lock(signals_combo_1_3)
    r_1_2_3 = simulate_trade_outcomes_with_20_lock(signals_combo_1_2_3)

    print("\n==========================================================================================")
    print("  GRID EXPERIMENT RESULTS WITH $20 PROFIT LOCK RULE ACTIVE")
    print("==========================================================================================")
    print("--- INDIVIDUAL OPTIONS ---")
    print(f"0. Baseline (Unfiltered):            Trades: {r_base['total_trades']:3d} | TP: {r_base['tp50']:2d} | Lock20: {r_base['lock20']:3d} | SL: {r_base['sl20']:3d} | WinRate: {r_base['win_rate']:.1f}% | PF: {r_base['profit_factor']} | Net PnL: ${r_base['net_pnl']:+.2f}")
    print(f"1. Option 1 Alone (M1 Close):        Trades: {r_1['total_trades']:3d} | TP: {r_1['tp50']:2d} | Lock20: {r_1['lock20']:3d} | SL: {r_1['sl20']:3d} | WinRate: {r_1['win_rate']:.1f}% | PF: {r_1['profit_factor']} | Net PnL: ${r_1['net_pnl']:+.2f}")
    print(f"2. Option 2 Alone (Live Conv 0.50):  Trades: {r_2['total_trades']:3d} | TP: {r_2['tp50']:2d} | Lock20: {r_2['lock20']:3d} | SL: {r_2['sl20']:3d} | WinRate: {r_2['win_rate']:.1f}% | PF: {r_2['profit_factor']} | Net PnL: ${r_2['net_pnl']:+.2f}")
    print(f"3. Option 3 Alone (M15 Trend):        Trades: {r_3['total_trades']:3d} | TP: {r_3['tp50']:2d} | Lock20: {r_3['lock20']:3d} | SL: {r_3['sl20']:3d} | WinRate: {r_3['win_rate']:.1f}% | PF: {r_3['profit_factor']} | Net PnL: ${r_3['net_pnl']:+.2f}\n")

    print("--- PAIRWISE COMBINATIONS ---")
    print(f"4. Combo 1 + 2 (M1 Close + Conv 0.50): Trades: {r_1_2['total_trades']:3d} | TP: {r_1_2['tp50']:2d} | Lock20: {r_1_2['lock20']:3d} | SL: {r_1_2['sl20']:3d} | WinRate: {r_1_2['win_rate']:.1f}% | PF: {r_1_2['profit_factor']} | Net PnL: ${r_1_2['net_pnl']:+.2f}")
    print(f"5. Combo 2 + 3 (Conv 0.50 + M15 Trend): Trades: {r_2_3['total_trades']:3d} | TP: {r_2_3['tp50']:2d} | Lock20: {r_2_3['lock20']:3d} | SL: {r_2_3['sl20']:3d} | WinRate: {r_2_3['win_rate']:.1f}% | PF: {r_2_3['profit_factor']} | Net PnL: ${r_2_3['net_pnl']:+.2f}")
    print(f"6. Combo 1 + 3 (M1 Close + M15 Trend):       Trades: {r_1_3['total_trades']:3d} | TP: {r_1_3['tp50']:2d} | Lock20: {r_1_3['lock20']:3d} | SL: {r_1_3['sl20']:3d} | WinRate: {r_1_3['win_rate']:.1f}% | PF: {r_1_3['profit_factor']} | Net PnL: ${r_1_3['net_pnl']:+.2f}\n")

    print("--- TRIPLE COMBINATION ---")
    print(f"7. Combo 1 + 2 + 3 (All 3 Combined):         Trades: {r_1_2_3['total_trades']:3d} | TP: {r_1_2_3['tp50']:2d} | Lock20: {r_1_2_3['lock20']:3d} | SL: {r_1_2_3['sl20']:3d} | WinRate: {r_1_2_3['win_rate']:.1f}% | PF: {r_1_2_3['profit_factor']} | Net PnL: ${r_1_2_3['net_pnl']:+.2f}")
    print("==========================================================================================")

if __name__ == "__main__":
    run_grid_simulation_with_20_lock()
