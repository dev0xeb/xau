#!/usr/bin/env python3
"""
realtime_feature_pipeline.py - Real-Time Rolling Feature Extraction Pipeline

Maintains rolling buffers for ticks and M1 candles to produce the exact feature vector
schema used during research without indicator code duplication:
- volatility_atr
- momentum_velocity
- compression_ratio
- spread_usd
- session_high_dist
- session_low_dist
"""

from collections import deque
import numpy as np

class RealtimeFeaturePipeline:
    """Computes real-time rolling feature vectors from streaming market data."""

    def __init__(self, candle_buffer_size: int = 100):
        self.candle_buffer_size = candle_buffer_size
        self.candles = deque(maxlen=candle_buffer_size)

    def process_m1_candle(self, m1_candle: dict, current_tick: dict = None) -> dict:
        """
        Appends completed M1 candle to buffer and computes real-time feature vector.
        """
        self.candles.append(m1_candle)
        closes = [c["close"] for c in self.candles]
        highs = [c["high"] for c in self.candles]
        lows = [c["low"] for c in self.candles]

        # 1. Volatility ATR (14 period)
        if len(self.candles) >= 14:
            tr_list = []
            for i in range(1, len(self.candles)):
                h = highs[i]
                l = lows[i]
                prev_c = closes[i-1]
                tr = max(h - l, abs(h - prev_c), abs(l - prev_c))
                tr_list.append(tr)
            volatility_atr = round(float(np.mean(tr_list[-14:])), 3)
        else:
            volatility_atr = 1.50

        # 2. Momentum Velocity (5 period price delta)
        if len(closes) >= 5:
            momentum_velocity = round(closes[-1] - closes[-5], 3)
        else:
            momentum_velocity = 0.0

        # 3. Compression Ratio (High-Low range vs ATR)
        range_5 = max(highs[-5:]) - min(lows[-5:]) if len(highs) >= 5 else 2.0
        compression_ratio = round(range_5 / max(0.1, volatility_atr), 3)

        # 4. Spread
        spread_usd = current_tick["spread_usd"] if current_tick else 0.15

        # 5. Session High / Low Distances
        session_high = max(highs)
        session_low = min(lows)
        session_high_dist = round(session_high - closes[-1], 3)
        session_low_dist = round(closes[-1] - session_low, 3)

        return {
            "timestamp_utc": m1_candle.get("minute_key"),
            "close": closes[-1],
            "volatility_atr": volatility_atr,
            "momentum_velocity": momentum_velocity,
            "compression_ratio": compression_ratio,
            "spread_usd": spread_usd,
            "session_high_dist": session_high_dist,
            "session_low_dist": session_low_dist
        }
