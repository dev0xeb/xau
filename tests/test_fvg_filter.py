"""
test_fvg_filter.py - Automated Unit Test Suite for M5FairValueGapFilter
"""

import sys
import os
sys.path.insert(0, os.path.abspath("."))

import unittest
from unittest.mock import MagicMock, patch
from execution_engine.filters.fvg_filter import M5FairValueGapFilter
from decision_engine.live_decision_engine import LiveDecisionEngine

class TestM5FairValueGapFilter(unittest.TestCase):

    def test_fvg_filter_bullish_gap(self):
        filter_engine = M5FairValueGapFilter(symbol="XAUUSD")
        
        # Mock MT5 rates response (5 candles: bar0 current, bar1 last completed, bar2, bar3)
        mock_rates = [
            {"time": 100, "open": 2350.0, "high": 2352.0, "low": 2349.0, "close": 2351.0}, # bar4
            {"time": 200, "open": 2351.0, "high": 2353.0, "low": 2350.0, "close": 2352.0}, # bar3 (high = 2353.0)
            {"time": 300, "open": 2352.0, "high": 2357.0, "low": 2352.0, "close": 2356.0}, # bar2 (displacement)
            {"time": 400, "open": 2356.0, "high": 2359.0, "low": 2354.0, "close": 2358.0}, # bar1 (low = 2354.0)
            {"time": 500, "open": 2358.0, "high": 2360.0, "low": 2357.0, "close": 2359.0}, # bar0 (current)
        ]
        # Bullish gap = bar1.low (2354.0) - bar3.high (2353.0) = 1.00 USD (> 0.50 min)

        with patch("MetaTrader5.copy_rates_from_pos", return_value=mock_rates):
            status = filter_engine.check_fvg_status()
            self.assertTrue(status["is_fvg_active"])
            self.assertEqual(status["fvg_type"], "BUY")
            self.assertEqual(status["fvg_gap_size"], 1.00)
            self.assertTrue(filter_engine.is_signal_allowed("BUY"))
            self.assertFalse(filter_engine.is_signal_allowed("SELL"))

    def test_fvg_filter_bearish_gap(self):
        filter_engine = M5FairValueGapFilter(symbol="XAUUSD")
        
        # Mock MT5 rates response for Bearish FVG
        mock_rates = [
            {"time": 100, "open": 2360.0, "high": 2362.0, "low": 2359.0, "close": 2361.0}, # bar4
            {"time": 200, "open": 2361.0, "high": 2362.0, "low": 2358.0, "close": 2359.0}, # bar3 (low = 2358.0)
            {"time": 300, "open": 2359.0, "high": 2359.0, "low": 2353.0, "close": 2354.0}, # bar2 (displacement)
            {"time": 400, "open": 2354.0, "high": 2356.8, "low": 2352.0, "close": 2353.0}, # bar1 (high = 2356.8)
            {"time": 500, "open": 2353.0, "high": 2354.0, "low": 2351.0, "close": 2352.0}, # bar0 (current)
        ]
        # Bearish gap = bar3.low (2358.0) - bar1.high (2356.8) = 1.20 USD (> 0.50 min)

        with patch("MetaTrader5.copy_rates_from_pos", return_value=mock_rates):
            status = filter_engine.check_fvg_status()
            self.assertTrue(status["is_fvg_active"])
            self.assertEqual(status["fvg_type"], "SELL")
            self.assertEqual(status["fvg_gap_size"], 1.20)
            self.assertTrue(filter_engine.is_signal_allowed("SELL"))
            self.assertFalse(filter_engine.is_signal_allowed("BUY"))

    def test_live_decision_engine_fvg_integration(self):
        mock_fvg = MagicMock()
        mock_fvg.check_fvg_status.return_value = {"is_fvg_active": True, "fvg_type": "BUY", "fvg_gap_size": 1.50}

        mock_news = MagicMock()
        mock_news.is_news_blocked.return_value = (False, "")

        engine = LiveDecisionEngine(
            fvg_filter=mock_fvg,
            news_filter=mock_news,
            cooldown_seconds=300.0,
            positions_per_signal=3
        )

        tick = {"ask": 2350.50, "bid": 2350.35, "spread_usd": 0.15}
        features = {"volatility_atr": 1.50}

        candidate = engine.evaluate_features(features, tick)

        self.assertEqual(candidate["decision"], "EXECUTE")
        self.assertEqual(candidate["direction"], "BUY")
        self.assertEqual(candidate["strategy_version"], "STRAT-XAU-FVG-BURST")
        self.assertEqual(candidate["positions_per_signal"], 3)
        self.assertEqual(candidate["sl"], 2349.00)  # 2350.50 - $1.50
        self.assertEqual(candidate["tp"], 2352.75)  # 2350.50 + $2.25

if __name__ == "__main__":
    unittest.main()
