#!/usr/bin/env python3
"""
bos_filter.py - Strictly Causal M5 Change of Character & Break of Structure Filter

Tracks M5 5-bar fractal swing highs and swing lows using strictly causal past data.
Evaluates real-time structural breakouts (CHOCH / BOS) for STRAT-002:
- Bullish BOS/CHOCH: M5 close breaks above previous confirmed swing high -> returns "BUY"
- Bearish BOS/CHOCH: M5 close breaks below previous confirmed swing low -> returns "SELL"

Includes automatic broker symbol resolution (e.g., 'XAUUSDz' vs 'XAUUSD').
"""

import os
import sys
import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta

try:
    import MetaTrader5 as mt5
    HAS_MT5 = True
except ImportError:
    HAS_MT5 = False

class M5StructureBreakoutFilter:
    """
    Strictly Causal M5 CHOCH / BOS Breakout Filter.
    """

    def __init__(self, symbol: str = "XAUUSDz"):
        self.raw_symbol = symbol
        self.symbol = self.resolve_broker_symbol(symbol)
        self.last_confirmed_sh = None
        self.last_confirmed_sl = None

    def resolve_broker_symbol(self, requested_symbol: str) -> str:
        """
        Queries MT5 to check if the requested symbol (e.g. 'XAUUSDz') is available.
        If not, falls back to alternative symbol naming variants like 'XAUUSD'.
        """
        if not HAS_MT5:
            return requested_symbol

        if not mt5.initialize():
            return requested_symbol

        info = mt5.symbol_info(requested_symbol)
        if info is not None:
            return requested_symbol

        symbol_candidates = [requested_symbol, "XAUUSD", "XAUUSDz", "GOLD", "XAUUSD.a", "XAUUSD.ecn", "XAUUSDm"]
        for cand in symbol_candidates:
            cand_info = mt5.symbol_info(cand)
            if cand_info is not None:
                print(f"[SYMBOL RESOLVER] Auto-discovered broker Gold symbol: '{cand}'")
                return cand

        return requested_symbol

    def check_structure_breakout(self) -> dict:
        """
        Fetches M5 rates from MT5 terminal and calculates causal swing high/low breakouts.

        Returns:
            dict: {
                "active": bool,
                "bos_type": "BUY" | "SELL" | "NONE",
                "swing_high": float,
                "swing_low": float,
                "breakout_price": float
            }
        """
        default_res = {
            "active": False,
            "bos_type": "NONE",
            "swing_high": 0.0,
            "swing_low": 0.0,
            "breakout_price": 0.0
        }

        if not HAS_MT5:
            return default_res

        if not mt5.initialize():
            return default_res

        # Fetch last 30 M5 bars
        rates = mt5.copy_rates_from_pos(self.symbol, mt5.TIMEFRAME_M5, 0, 30)
        if rates is None or len(rates) < 10:
            return default_res

        df = pd.DataFrame(rates)

        # Strictly causal 5-bar fractal swing calculation on past completed bars (exclude bar 0, active bar)
        # Bar 1 is the last completed bar.
        df_comp = df.iloc[:-1].copy().reset_index(drop=True)

        # Causal fractal swing high at bar i-2 if high[i-2] > high[i-4], high[i-3], high[i-1], high[i]
        df_comp["causal_sh"] = np.where(
            (df_comp["high"].shift(2) > df_comp["high"].shift(4)) &
            (df_comp["high"].shift(2) > df_comp["high"].shift(3)) &
            (df_comp["high"].shift(2) > df_comp["high"].shift(1)) &
            (df_comp["high"].shift(2) > df_comp["high"]),
            df_comp["high"].shift(2), np.nan
        )

        df_comp["causal_sl"] = np.where(
            (df_comp["low"].shift(2) < df_comp["low"].shift(4)) &
            (df_comp["low"].shift(2) < df_comp["low"].shift(3)) &
            (df_comp["low"].shift(2) < df_comp["low"].shift(1)) &
            (df_comp["low"].shift(2) < df_comp["low"]),
            df_comp["low"].shift(2), np.nan
        )

        df_comp["confirmed_sh"] = df_comp["causal_sh"].ffill()
        df_comp["confirmed_sl"] = df_comp["causal_sl"].ffill()

        last_sh = df_comp["confirmed_sh"].dropna().iloc[-1] if not df_comp["confirmed_sh"].dropna().empty else 0.0
        last_sl = df_comp["confirmed_sl"].dropna().iloc[-1] if not df_comp["confirmed_sl"].dropna().empty else 0.0

        prev_sh = df_comp["confirmed_sh"].shift(1).dropna().iloc[-1] if len(df_comp["confirmed_sh"].dropna()) > 1 else last_sh
        prev_sl = df_comp["confirmed_sl"].shift(1).dropna().iloc[-1] if len(df_comp["confirmed_sl"].dropna()) > 1 else last_sl

        last_close = df_comp["close"].iloc[-1]
        prev_close = df_comp["close"].iloc[-2]

        self.last_confirmed_sh = last_sh
        self.last_confirmed_sl = last_sl

        # Bullish BOS: last_close > prev_sh and prev_close <= prev_sh
        is_bull_bos = (prev_sh > 0) and (last_close > prev_sh) and (prev_close <= prev_sh)

        # Bearish BOS: last_close < prev_sl and prev_close >= prev_sl
        is_bear_bos = (prev_sl > 0) and (last_close < prev_sl) and (prev_close >= prev_sl)

        last_bar_time = int(df_comp["time"].iloc[-1]) if "time" in df_comp.columns else 0

        if is_bull_bos:
            return {
                "active": True,
                "bos_type": "BUY",
                "swing_high": last_sh,
                "swing_low": last_sl,
                "breakout_price": last_close,
                "bar_time": last_bar_time
            }
        elif is_bear_bos:
            return {
                "active": True,
                "bos_type": "SELL",
                "swing_high": last_sh,
                "swing_low": last_sl,
                "breakout_price": last_close,
                "bar_time": last_bar_time
            }

        return {
            "active": False,
            "bos_type": "NONE",
            "swing_high": last_sh,
            "swing_low": last_sl,
            "breakout_price": last_close,
            "bar_time": last_bar_time
        }
