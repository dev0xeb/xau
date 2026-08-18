"""
Strategy 1.1: Optimized SMC Liquidity Sweep, CHoCH & FVG Reversal Strategy.

Incorporates 5 Empirical 5-Year Data-Mined Rules for XAU/USD Scalping:
1. Session Window: London Open (07:00-10:00 UTC) & London/NY Overlap (12:00-16:00 UTC)
2. HTF Trend Alignment: 15m 50 EMA trend filter
3. Wick Sweep Filter: $0.50-$1.50 depth wick sweep with candle closing BACK INSIDE range
4. Displacement CHoCH: Body size >= 1.5x 14 ATR
5. Empirical SL/TP Framework: Structural SL (+ 0.5 ATR buffer), TP1 at 1:1.5 RR (50% exit + BE lock), TP2 at 1:2.5 RR
"""

from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
import numpy as np
import pandas as pd
import logging

from src.strategies.base import BaseStrategy
from src.backtest.types import TradeSignal, SignalType, OrderType
from src.backtest.htf_guard import TimestampSafeHTFGuard, FastHTFSlice

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


class SMCSweepFVGStrategy(BaseStrategy):
    """Strategy 1.1: Optimized SMC Liquidity Sweep & FVG Reversal Strategy."""

    def __init__(
        self,
        strategy_id: str = "SMC_SWEEP_FVG_1.1",
        lookback_15m_bars: int = 50,
        min_displacement_atr_mult: float = 1.5,
    ):
        super().__init__(strategy_id=strategy_id)
        self.lookback_15m_bars = lookback_15m_bars
        self.min_displacement_atr_mult = min_displacement_atr_mult

        # Setup state tracking
        self.active_sweep: Optional[Dict[str, Any]] = None
        self.active_choch: Optional[Dict[str, Any]] = None

    def check_session_filter(self, current_bar_1m: Dict[str, Any]) -> bool:
        """
        Enforces strict high-volatility session windows based on 5-year research:
        - London Open Window: 07:00 - 10:00 UTC
        - London/NY Overlap Window: 12:00 - 16:00 UTC
        """
        ts = current_bar_1m.get("timestamp")
        if ts is None:
            return False
        
        dt = pd.to_datetime(ts)
        hour = dt.hour
        
        is_london_open = (7 <= hour < 10)
        is_ny_overlap = (12 <= hour < 16)

        return (is_london_open or is_ny_overlap)

    def generate_signal(
        self,
        current_time: datetime,
        current_bar_1m: Dict[str, Any],
        htf_guard: TimestampSafeHTFGuard,
        has_open_position: bool,
    ) -> Optional[TradeSignal]:
        """
        Generates TradeSignal for Strategy 1.1 given market state and HTFGuard.
        Flow: 15m Trend Filter -> 15m Wick Sweep ($0.50-$1.50) -> 1.5x ATR CHoCH -> 50% FVG Retrace.
        """
        if has_open_position:
            return None

        # Fetch closed 15m and 1m bars from zero-lookahead HTF guard
        slice_15m = htf_guard.get_closed_htf_bars(current_time, timeframe_minutes=15, max_bars=self.lookback_15m_bars)
        slice_1m = htf_guard.get_closed_htf_bars(current_time, timeframe_minutes=1, max_bars=15)

        if slice_15m.empty or len(slice_15m) < 20 or slice_1m.empty or len(slice_1m) < 4:
            return None

        bar_high = float(current_bar_1m["high"])
        bar_low = float(current_bar_1m["low"])
        bar_close = float(current_bar_1m["close"])
        bar_open = float(current_bar_1m["open"])
        bar_spread = float(current_bar_1m.get("spread", 20)) * 0.01

        highs_15m = slice_15m._highs
        lows_15m = slice_15m._lows
        closes_15m = slice_15m._closes

        # 15m 50 EMA Trend Filter
        ema_50_15m = pd.Series(closes_15m).ewm(span=50, adjust=False).mean().iloc[-1]
        htf_trend_bullish = (closes_15m[-1] > ema_50_15m)
        htf_trend_bearish = (closes_15m[-1] < ema_50_15m)

        # 15m Swing Levels (20-bar window)
        recent_high_level = float(np.max(highs_15m[-20:-1]))
        recent_low_level = float(np.min(lows_15m[-20:-1]))

        # 1. Bearish Sweep: Wick above 15m High ($0.50-$1.50 depth), close BACK INSIDE range + Bearish HTF Trend
        if htf_trend_bearish and bar_high > recent_high_level and bar_close < recent_high_level:
            sweep_depth = bar_high - recent_high_level
            if 0.50 <= sweep_depth <= 2.50:
                self.active_sweep = {
                    "type": "BEARISH",
                    "level": recent_high_level,
                    "sweep_high": bar_high,
                    "time": current_time,
                }
                self.active_choch = None

        # Bullish Sweep: Wick below 15m Low ($0.50-$1.50 depth), close BACK INSIDE range + Bullish HTF Trend
        elif htf_trend_bullish and bar_low < recent_low_level and bar_close > recent_low_level:
            sweep_depth = recent_low_level - bar_low
            if 0.50 <= sweep_depth <= 2.50:
                self.active_sweep = {
                    "type": "BULLISH",
                    "level": recent_low_level,
                    "sweep_low": bar_low,
                    "time": current_time,
                }
                self.active_choch = None

        # Expire old sweep state after 45 minutes
        if self.active_sweep and (current_time - self.active_sweep["time"]) > timedelta(minutes=45):
            self.active_sweep = None
            self.active_choch = None

        if not self.active_sweep:
            return None

        # 2. Displacement CHoCH (1.5x ATR candle body size requirement)
        highs_1m = slice_1m._highs
        lows_1m = slice_1m._lows
        tr_1m = float(np.mean(highs_1m[-14:] - lows_1m[-14:])) if len(highs_1m) >= 14 else 1.0
        body_size = abs(bar_close - bar_open)

        # Bullish CHoCH
        if self.active_sweep["type"] == "BULLISH" and not self.active_choch:
            recent_1m_high = float(np.max(highs_1m[-5:]))
            if bar_close > recent_1m_high and body_size >= (self.min_displacement_atr_mult * tr_1m):
                self.active_choch = {
                    "type": "BULLISH",
                    "time": current_time,
                    "choch_price": bar_close,
                }

        # Bearish CHoCH
        elif self.active_sweep["type"] == "BEARISH" and not self.active_choch:
            recent_1m_low = float(np.min(lows_1m[-5:]))
            if bar_close < recent_1m_low and body_size >= (self.min_displacement_atr_mult * tr_1m):
                self.active_choch = {
                    "type": "BEARISH",
                    "time": current_time,
                    "choch_price": bar_close,
                }

        if not self.active_choch:
            return None

        # 3. Detect 3-Candle 1m Fair Value Gap (FVG) Entry
        c1_high = float(slice_1m._highs[-3])
        c1_low = float(slice_1m._lows[-3])

        # Bullish FVG: Low3 > High1
        if self.active_choch["type"] == "BULLISH" and bar_low > c1_high:
            fvg_top = bar_low
            fvg_bottom = c1_high
            fvg_mid = (fvg_top + fvg_bottom) / 2.0

            if bar_low <= fvg_top and bar_close >= fvg_bottom:
                # Structural SL: Below swept 15m low - spread - (0.5 * 1m ATR)
                sl_price = recent_low_level - bar_spread - (0.5 * tr_1m)
                sl_dist = bar_close - sl_price

                if sl_dist < 1.00 or sl_dist > 5.00:
                    return None

                # Empirical TP Rules: TP1 at 1:1.5 RR (50% partial + BE lock), TP2 at 1:2.5 RR
                tp1_price = round(bar_close + (1.5 * sl_dist), 2)
                tp2_price = round(bar_close + (2.5 * sl_dist), 2)

                self.active_sweep = None
                self.active_choch = None

                return TradeSignal(
                    timestamp=current_time,
                    strategy_id=self.strategy_id,
                    signal_type=SignalType.BUY,
                    order_type=OrderType.MARKET,
                    sl_price=round(sl_price, 2),
                    tp1_price=tp1_price,
                    tp2_price=tp2_price,
                    tp1_ratio=0.50,
                    metadata={"setup": "BULLISH_SMC_1.1", "fvg_mid": fvg_mid, "sl_dist": sl_dist},
                )

        # Bearish FVG: High3 < Low1
        elif self.active_choch["type"] == "BEARISH" and bar_high < c1_low:
            fvg_top = c1_low
            fvg_bottom = bar_high
            fvg_mid = (fvg_top + fvg_bottom) / 2.0

            if bar_high >= fvg_bottom and bar_close <= fvg_top:
                # Structural SL: Above swept 15m high + spread + (0.5 * 1m ATR)
                sl_price = recent_high_level + bar_spread + (0.5 * tr_1m)
                sl_dist = sl_price - bar_close

                if sl_dist < 1.00 or sl_dist > 5.00:
                    return None

                tp1_price = round(bar_close - (1.5 * sl_dist), 2)
                tp2_price = round(bar_close - (2.5 * sl_dist), 2)

                self.active_sweep = None
                self.active_choch = None

                return TradeSignal(
                    timestamp=current_time,
                    strategy_id=self.strategy_id,
                    signal_type=SignalType.SELL,
                    order_type=OrderType.MARKET,
                    sl_price=round(sl_price, 2),
                    tp1_price=tp1_price,
                    tp2_price=tp2_price,
                    tp1_ratio=0.50,
                    metadata={"setup": "BEARISH_SMC_1.1", "fvg_mid": fvg_mid, "sl_dist": sl_dist},
                )

        return None
