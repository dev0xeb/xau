#!/usr/bin/env python3
"""
market_quality_filter.py - Real-Time Market Quality Classifier

Evaluates market conditions:
GOOD | FAIR | POOR | UNTRADEABLE

Refuses execution if market quality is POOR or UNTRADEABLE based on:
- Current spread
- Tick frequency (ticks/min)
- Quote gaps (seconds)
- Latency (ms)
"""

from datetime import datetime, timezone

class MarketQualityGrade:
    GOOD = "GOOD"
    FAIR = "FAIR"
    POOR = "POOR"
    UNTRADEABLE = "UNTRADEABLE"

class MarketQualityFilter:
    """Evaluates real-time market quality and quote health."""

    def __init__(
        self,
        max_spread_good: float = 0.25,
        max_spread_fair: float = 0.35,
        max_spread_poor: float = 0.50,
        min_ticks_per_min: int = 10,
        max_quote_gap_sec: float = 5.0,
        max_latency_ms: float = 350.0
    ):
        self.max_spread_good = max_spread_good
        self.max_spread_fair = max_spread_fair
        self.max_spread_poor = max_spread_poor
        self.min_ticks_per_min = min_ticks_per_min
        self.max_quote_gap_sec = max_quote_gap_sec
        self.max_latency_ms = max_latency_ms

    def evaluate_market_quality(
        self,
        current_spread_usd: float,
        ticks_last_minute: int = 30,
        seconds_since_last_tick: float = 0.5,
        latency_ms: float = 45.0
    ) -> dict:
        """
        Evaluates market quote data and returns grade assignment.
        """
        reasons = []

        # 1. Quote staleness / gap
        if seconds_since_last_tick > self.max_quote_gap_sec:
            grade = MarketQualityGrade.UNTRADEABLE
            reasons.append(f"Stale quote gap: {seconds_since_last_tick:.1f}s > {self.max_quote_gap_sec}s")
            return {"grade": grade, "is_tradable": False, "reasons": reasons}

        # 2. Latency check
        if latency_ms > self.max_latency_ms:
            grade = MarketQualityGrade.UNTRADEABLE
            reasons.append(f"Excessive latency: {latency_ms:.1f}ms > {self.max_latency_ms}ms")
            return {"grade": grade, "is_tradable": False, "reasons": reasons}

        # 3. Tick frequency check
        if ticks_last_minute < self.min_ticks_per_min:
            grade = MarketQualityGrade.POOR
            reasons.append(f"Low tick frequency: {ticks_last_minute} ticks/min < {self.min_ticks_per_min}")

        # 4. Spread Evaluation
        if current_spread_usd > self.max_spread_poor:
            grade = MarketQualityGrade.UNTRADEABLE
            reasons.append(f"Severe spread breach: ${current_spread_usd:.2f} > ${self.max_spread_poor:.2f}")
        elif current_spread_usd > self.max_spread_fair:
            grade = MarketQualityGrade.POOR
            reasons.append(f"High spread: ${current_spread_usd:.2f} > ${self.max_spread_fair:.2f}")
        elif current_spread_usd > self.max_spread_good:
            grade = MarketQualityGrade.FAIR
            reasons.append(f"Moderate spread: ${current_spread_usd:.2f}")
        else:
            grade = MarketQualityGrade.GOOD

        is_tradable = grade in [MarketQualityGrade.GOOD, MarketQualityGrade.FAIR]
        return {
            "grade": grade,
            "is_tradable": is_tradable,
            "reasons": reasons,
            "evaluated_at_utc": datetime.now(timezone.utc).isoformat()
        }
