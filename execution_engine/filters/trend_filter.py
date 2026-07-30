#!/usr/bin/env python3
"""
trend_filter.py - M15 Higher Timeframe Trend Alignment Guardrail Filter

Calculates M15 EMA 20 vs EMA 50 to enforce trend alignment:
- BUY Trades: Only permitted when M15 EMA 20 > EMA 50 (M15 Uptrend)
- SELL Trades: Only permitted when M15 EMA 20 < EMA 50 (M15 Downtrend)
- Rejects counter-trend trades to eliminate low-probability chop entries.
"""

import os
import sys
import logging
import pandas as pd
from datetime import datetime, timezone, timedelta
import MetaTrader5 as mt5

logger = logging.getLogger("TrendFilter")

class TrendFilter:
    """M15 Higher Timeframe Trend Guardrail Filter."""

    def __init__(
        self,
        symbol: str = "XAUUSDz",
        fast_span: int = 20,
        slow_span: int = 50,
        enabled: bool = True
    ):
        self.symbol = symbol
        self.fast_span = fast_span
        self.slow_span = slow_span
        self.enabled = enabled

    def get_current_m15_trend(self) -> tuple[str, float, float]:
        """
        Queries M15 rates from MT5 and calculates EMA 20 vs EMA 50.
        Returns: (trend: str ["UPTREND", "DOWNTREND", "FLAT"], ema20: float, ema50: float)
        """
        if not self.enabled:
            return "FLAT", 0.0, 0.0

        if not mt5.initialize():
            logger.warning("MetaTrader 5 not connected for M15 trend calculation.")
            return "FLAT", 0.0, 0.0

        now = datetime.now(timezone.utc)
        from_dt = now - timedelta(days=2)
        rates = mt5.copy_rates_range(self.symbol, mt5.TIMEFRAME_M15, from_dt, now)

        if rates is None or len(rates) < self.slow_span:
            # Fallback retry with default symbol if symbol suffix differs
            rates = mt5.copy_rates_range("XAUUSD", mt5.TIMEFRAME_M15, from_dt, now)

        if rates is None or len(rates) < self.slow_span:
            return "FLAT", 0.0, 0.0

        df = pd.DataFrame(rates)
        df["ema20"] = df["close"].ewm(span=self.fast_span, adjust=False).mean()
        df["ema50"] = df["close"].ewm(span=self.slow_span, adjust=False).mean()

        last = df.iloc[-1]
        ema20 = float(last["ema20"])
        ema50 = float(last["ema50"])

        if ema20 > ema50:
            return "UPTREND", ema20, ema50
        elif ema20 < ema50:
            return "DOWNTREND", ema20, ema50
        else:
            return "FLAT", ema20, ema50

    def is_trend_aligned(self, direction: str) -> tuple[bool, str]:
        """
        Evaluates whether proposed trade direction aligns with current M15 trend.
        Returns: (is_aligned: bool, reason: str)
        """
        if not self.enabled:
            return True, "Trend Filter Disabled"

        trend, ema20, ema50 = self.get_current_m15_trend()
        dir_upper = str(direction).upper()

        if trend == "UPTREND":
            if dir_upper == "BUY":
                return True, f"ALIGNED: BUY in M15 Uptrend (EMA20 ${ema20:.2f} > EMA50 ${ema50:.2f})"
            else:
                return False, f"REJECTED: SELL prohibited during M15 Uptrend (EMA20 ${ema20:.2f} > EMA50 ${ema50:.2f})"

        elif trend == "DOWNTREND":
            if dir_upper == "SELL":
                return True, f"ALIGNED: SELL in M15 Downtrend (EMA20 ${ema20:.2f} < EMA50 ${ema50:.2f})"
            else:
                return False, f"REJECTED: BUY prohibited during M15 Downtrend (EMA20 ${ema20:.2f} < EMA50 ${ema50:.2f})"

        return True, "ALIGNED: M15 Trend Neutral"
