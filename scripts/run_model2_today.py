"""
Run Baseline Model 2 on Today's / Most Recent Trading Day Data.

Evaluates:
- H1 Macro Trend Filter (EMA 21 vs 50)
- M5 Session Killzone (06:00 - 20:00 UTC)
- M5 FVG Displacement (>= 1.5 pips)
- M5 EMA(21) Liquidity Sweep
- M5 Micro-structure Close Confirmation
- 3-Burst Target Matrix (1.0x / 2.0x / 3.0x SL)
"""

import sys
from pathlib import Path
from datetime import datetime, date
import pandas as pd
import numpy as np
import time

def run_today_model2():
    proc_5m_path = Path("data/processed/xau_5m_5y.parquet")
    if not proc_5m_path.exists():
        print("[ERROR] 5m dataset missing!")
        return

    print("================================================================================")
    print("      BASELINE MODEL 2 (M5 SCALP HYBRID) - TODAY'S TRADE EVALUATION")
    print("================================================================================")

    df_5m = pd.read_parquet(proc_5m_path)
    df_5m['timestamp'] = pd.to_datetime(df_5m['timestamp'])
    df_5m = df_5m.sort_values('timestamp').reset_index(drop=True)

    df_5m['hour'] = df_5m['timestamp'].dt.hour
    df_5m['minute'] = df_5m['timestamp'].dt.minute
    df_5m['date'] = df_5m['timestamp'].dt.date

    # Find the most recent trading date in dataset
    available_dates = sorted(df_5m['date'].unique())
    latest_date = available_dates[-1]

    print(f" -> Most Recent Trading Date in Dataset: {latest_date}")

    # Extract 5m candles for latest_date
    df_today = df_5m[df_5m['date'] == latest_date].copy().reset_index(drop=True)
    print(f" -> Total M5 Bars Today ({latest_date}): {len(df_today)} candles")

    # Resample H1 for macro trend
    df_h1 = df_5m.resample('1h', on='timestamp').agg({
        'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last'
    }).dropna().reset_index()

    df_h1['ema21'] = df_h1['close'].ewm(span=21, adjust=False).mean()
    df_h1['ema50'] = df_h1['close'].ewm(span=50, adjust=False).mean()

    df_5m['h1_time'] = df_5m['timestamp'].dt.floor('1h')
    df_5m = pd.merge_asof(
        df_5m,
        df_h1[['timestamp', 'ema21', 'ema50', 'close']].rename(columns={
            'timestamp': 'h1_time', 'ema21': 'h1_ema21', 'ema50': 'h1_ema50', 'close': 'h1_close'
        }),
        on='h1_time', direction='backward'
    )

    df_5m['m5_ema21'] = df_5m['close'].ewm(span=21, adjust=False).mean()

    # Get index positions for today's bars in df_5m
    today_mask = df_5m['date'] == latest_date
    today_indices = np.where(today_mask)[0]

    closes_5m = df_5m['close'].values
    opens_5m = df_5m['open'].values
    highs_5m = df_5m['high'].values
    lows_5m = df_5m['low'].values
    hours_5m = df_5m['hour'].values
    minutes_5m = df_5m['minute'].values
    timestamps = df_5m['timestamp'].dt.strftime('%H:%M UTC').values

    h1_closes = df_5m['h1_close'].values
    h1_ema21s = df_5m['h1_ema21'].values
    h1_ema50s = df_5m['h1_ema50'].values
    m5_ema21s = df_5m['m5_ema21'].values

    n = len(df_5m)
    pip_size = 0.10
    spread = 0.15

    trades_today = []
    traded_today = False

    print("\n--------------------------------------------------------------------------------")
    print(f" SCANNING INTRADAY SETUPS FOR TODAY ({latest_date}):")
    print("--------------------------------------------------------------------------------")

    for i in today_indices:
        hour = hours_5m[i]
        minute = minutes_5m[i]
        t_str = timestamps[i]

        if not (6 <= hour < 20):
            continue

        idx = i - 1  # iloc[-2] closed candle

        h1_c = h1_closes[idx]
        h1_e21 = h1_ema21s[idx]
        h1_e50 = h1_ema50s[idx]

        h1_bullish = (h1_c > h1_e21) and (h1_e21 > h1_e50)
        h1_bearish = (h1_c < h1_e21) and (h1_e21 < h1_e50)

        # M5 FVG Displacement
        low_t = lows_5m[idx]
        high_t = highs_5m[idx]
        low_t2 = lows_5m[idx - 2]
        high_t2 = highs_5m[idx - 2]

        bull_fvg_pips = (low_t - high_t2) / pip_size
        bear_fvg_pips = (low_t2 - high_t) / pip_size

        is_bull_fvg = bull_fvg_pips >= 1.5
        is_bear_fvg = bear_fvg_pips >= 1.5

        # Institutional Liquidity Sweep
        prior_5_low = np.min(lows_5m[idx-5 : idx])
        prior_5_high = np.max(highs_5m[idx-5 : idx])
        m5_e21 = m5_ema21s[idx]

        bull_sweep = prior_5_low <= m5_e21
        bear_sweep = prior_5_high >= m5_e21

        # Micro-structure Close Confirmation
        m5_close = closes_5m[idx]
        bull_confirm = m5_close > m5_e21
        bear_confirm = m5_close < m5_e21

        buy_signal = h1_bullish and is_bull_fvg and bull_sweep and bull_confirm
        sell_signal = h1_bearish and is_bear_fvg and bear_sweep and bear_confirm

        if buy_signal or sell_signal:
            direction = "BUY" if buy_signal else "SELL"
            recent_3_low = np.min(lows_5m[idx-2 : idx+1])
            recent_3_high = np.max(highs_5m[idx-2 : idx+1])

            if buy_signal:
                entry_price = high_t2 + spread
                sl_price = recent_3_low - 0.50
                sl_pips = np.clip((entry_price - sl_price) / pip_size, 15.0, 80.0)
                sl_price = entry_price - (sl_pips * pip_size)

                tp1 = entry_price + (sl_pips * pip_size * 1.0)
                tp2 = entry_price + (sl_pips * pip_size * 2.0)
                tp3 = entry_price + (sl_pips * pip_size * 3.0)

            else:
                entry_price = low_t2
                sl_price = recent_3_high + 0.50
                sl_pips = np.clip((sl_price - entry_price) / pip_size, 15.0, 80.0)
                sl_price = entry_price + (sl_pips * pip_size)

                tp1 = entry_price - (sl_pips * pip_size * 1.0)
                tp2 = entry_price - (sl_pips * pip_size * 2.0)
                tp3 = entry_price - (sl_pips * pip_size * 3.0)

            # Evaluate Trade Outcomes Forward
            t1_hit, t2_hit, t3_hit = False, False, False
            sl_hit = False
            risk_per_ticket = 33.33
            t1_pnl, t2_pnl, t3_pnl = -33.33, -33.33, -33.33

            for k in range(i, min(i + 36, n)):
                bar_h = highs_5m[k]
                bar_l = lows_5m[k]

                if direction == "BUY":
                    if bar_l <= sl_price:
                        sl_hit = True
                        break
                    if not t1_hit and bar_h >= tp1:
                        t1_hit = True
                        t1_pnl = risk_per_ticket * 1.0
                    if t1_hit and not t2_hit and bar_h >= tp2:
                        t2_hit = True
                        t2_pnl = risk_per_ticket * 2.0
                    if t2_hit and not t3_hit and bar_h >= tp3:
                        t3_hit = True
                        t3_pnl = risk_per_ticket * 3.0
                        break
                else:  # SELL
                    if bar_h >= sl_price:
                        sl_hit = True
                        break
                    if not t1_hit and bar_l <= tp1:
                        t1_hit = True
                        t1_pnl = risk_per_ticket * 1.0
                    if t1_hit and not t2_hit and bar_l <= tp2:
                        t2_hit = True
                        t2_pnl = risk_per_ticket * 2.0
                    if t2_hit and not t3_hit and bar_l <= tp3:
                        t3_hit = True
                        t3_pnl = risk_per_ticket * 3.0
                        break

            trade_pnl = t1_pnl + t2_pnl + t3_pnl

            trades_today.append({
                'time': t_str,
                'direction': direction,
                'entry_price': entry_price,
                'sl_price': sl_price,
                'sl_pips': sl_pips,
                'tp1': tp1,
                'tp2': tp2,
                'tp3': tp3,
                't1_hit': t1_hit,
                't2_hit': t2_hit,
                't3_hit': t3_hit,
                'sl_hit': sl_hit,
                'pnl': trade_pnl,
                'is_win': trade_pnl > 0
            })

            print(f" -> [{t_str}] SIGNAL: {direction} @ ${entry_price:.2f} | SL: ${sl_price:.2f} ({sl_pips:.1f} pips)")
            print(f"    Targets: TP1=${tp1:.2f} | TP2=${tp2:.2f} | TP3=${tp3:.2f}")
            print(f"    Outcome: {'WIN (+ $' + str(round(trade_pnl, 2)) + ')' if trade_pnl > 0 else 'LOSS (- $100.00)'} (TP1: {t1_hit}, TP2: {t2_hit}, TP3: {t3_hit})")
            print("--------------------------------------------------------------------------------")

    if len(trades_today) == 0:
        print(f" -> No Model 2 setups triggered today ({latest_date}) within session hours (06:00 - 20:00 UTC).")
        print("    Market condition: High timeframe trend or M5 liquidity sweep conditions did not align.")
    else:
        df_res = pd.DataFrame(trades_today)
        net_pnl = df_res['pnl'].sum()
        win_count = len(df_res[df_res['is_win']])
        print(f"\n================================================================================")
        print(f" SUMMARY FOR TODAY ({latest_date}):")
        print(f" -> Total Setups Triggered: {len(df_res)}")
        print(f" -> Win/Loss Count:       {win_count} Wins / {len(df_res) - win_count} Losses")
        print(f" -> Today's Net PnL:       {'+$' if net_pnl >= 0 else '-$'}{abs(net_pnl):.2f}")
        print("================================================================================")

if __name__ == "__main__":
    run_today_model2()
