"""
fvg_filter.py - M5 Fair Value Gap (FVG) Imbalance Filter Module

Calculates 3-bar 5-minute (M5) Fair Value Gap displacement gaps in real-time.
Identifies institutional liquidity imbalances on XAUUSD:
- Bullish FVG: M5 Low[bar1] - M5 High[bar3] > $0.50 / oz
- Bearish FVG: M5 Low[bar3] - M5 High[bar1] > $0.50 / oz
"""

import logging
from typing import Dict, Any, Optional
import pandas as pd
import numpy as np
import MetaTrader5 as mt5
from execution_engine.adapters.mt5_adapter import resolve_broker_symbol

logger = logging.getLogger("M5FairValueGapFilter")

class M5FairValueGapFilter:
    """
    Real-time M5 Fair Value Gap Imbalance Filter.
    Ensures trade execution only occurs when a valid M5 FVG displacement gap (> $0.50) exists.
    """
    def __init__(self, symbol: str = "XAUUSD", fvg_min_usd: float = 0.50):
        self.requested_symbol = symbol or "XAUUSD"
        self.symbol = resolve_broker_symbol(self.requested_symbol)
        self.fvg_min_usd = fvg_min_usd

    def check_fvg_status(self) -> Dict[str, Any]:
        """
        Queries MT5 for recent M5 candles and evaluates active FVG imbalance gaps.
        Returns:
            Dict containing:
                - is_fvg_active: bool
                - fvg_type: str ("BUY", "SELL", or "NONE")
                - fvg_gap_size: float
        """
        rates = mt5.copy_rates_from_pos(self.symbol, mt5.TIMEFRAME_M5, 0, 5)
        if rates is None or len(rates) < 4:
            logger.warning(f"[M5_FVG] Unable to fetch M5 rates from MT5 for '{self.symbol}'. Defaulting to NONE.")
            return {"is_fvg_active": False, "fvg_type": "NONE", "fvg_gap_size": 0.0, "bar_time": 0}

        df = pd.DataFrame(rates)
        last_bar_time = int(df["time"].iloc[-2]) if "time" in df.columns else 0

        low1 = df["low"].iloc[-2]
        high3 = df["high"].iloc[-4]
        high1 = df["high"].iloc[-2]
        low3 = df["low"].iloc[-4]

        bullish_gap = round(low1 - high3, 2)
        bearish_gap = round(low3 - high1, 2)

        if bullish_gap >= self.fvg_min_usd:
            logger.info(f"[M5_FVG] Bullish FVG Active! Gap: ${bullish_gap:.2f}/oz")
            return {"is_fvg_active": True, "fvg_type": "BUY", "fvg_gap_size": bullish_gap, "bar_time": last_bar_time}

        if bearish_gap >= self.fvg_min_usd:
            logger.info(f"[M5_FVG] Bearish FVG Active! Gap: ${bearish_gap:.2f}/oz")
            return {"is_fvg_active": True, "fvg_type": "SELL", "fvg_gap_size": bearish_gap, "bar_time": last_bar_time}

        return {"is_fvg_active": False, "fvg_type": "NONE", "fvg_gap_size": 0.0, "bar_time": last_bar_time}

    def is_signal_allowed(self, direction: str) -> bool:
        """
        Validates if proposed direction aligns with active M5 FVG.
        """
        status = self.check_fvg_status()
        if not status["is_fvg_active"]:
            return False
        return status["fvg_type"].upper() == direction.upper()
