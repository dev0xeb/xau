#!/usr/bin/env python3
"""
decision_quality_analyzer.py - Decision Quality & EV Variance Analyzer

Compares Expected EV vs Actual PnL per trade:
- Calculates Expected EV ($/trade)
- Measures EV Deviation (Actual PnL - Expected EV)
- Classifies Variance Attribution (MODEL_OPTIMISM | EXECUTION_SLIPPAGE | REGIME_SHIFT | NOMINAL_ALIGNMENT)
"""

class DecisionQualityAnalyzer:
    """Evaluates decision expected value vs empirical trade output."""

    @staticmethod
    def analyze_trade_decision_quality(
        expected_ev_usd: float,
        actual_pnl_usd: float,
        slippage_usd: float = 0.02,
        market_regime: str = "NORMAL"
    ) -> dict:
        """
        Calculates EV variance and attributes divergence.
        """
        ev_deviation = round(actual_pnl_usd - expected_ev_usd, 2)
        pct_deviation = round((ev_deviation / max(0.1, abs(expected_ev_usd))) * 100.0, 1)

        # Variance Attribution Logic
        if actual_pnl_usd >= expected_ev_usd * 0.90:
            attribution = "NOMINAL_ALIGNMENT"
            recommendation = "Model EV aligned with empirical results."
        elif slippage_usd >= 0.15:
            attribution = "EXECUTION_SLIPPAGE"
            recommendation = "High slippage dragged EV. Inspect broker order execution."
        elif market_regime in ["HIGH_VOLATILITY", "NEWS"]:
            attribution = "REGIME_SHIFT"
            recommendation = "Market regime shift impacted trade EV."
        else:
            attribution = "MODEL_OPTIMISM"
            recommendation = "Research decision model over-predicted trade outcome."

        return {
            "expected_ev_usd": expected_ev_usd,
            "actual_pnl_usd": actual_pnl_usd,
            "ev_deviation_usd": ev_deviation,
            "pct_deviation": pct_deviation,
            "attribution": attribution,
            "recommendation": recommendation
        }
