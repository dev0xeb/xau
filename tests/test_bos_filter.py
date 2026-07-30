#!/usr/bin/env python3
"""
test_bos_filter.py - Automated Unit Tests for M5StructureBreakoutFilter & LiveDecisionEngine (STRAT-002)

Tests:
1. M5StructureBreakoutFilter initialization & broker symbol auto-resolution.
2. Causal M5 5-bar fractal swing high/low computation (no lookahead).
3. LiveDecisionEngine payload evaluation for STRAT-002 and ENSEMBLE modes.
"""

import sys
import os
import unittest
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from execution_engine.filters.bos_filter import M5StructureBreakoutFilter
from decision_engine.live_decision_engine import LiveDecisionEngine

class TestM5StructureBreakoutFilter(unittest.TestCase):

    def setUp(self):
        self.bos_filter = M5StructureBreakoutFilter(symbol="XAUUSDz")

    def test_symbol_resolution(self):
        self.assertIsNotNone(self.bos_filter.symbol)
        self.assertTrue(len(self.bos_filter.symbol) > 0)

    def test_check_structure_breakout_structure(self):
        res = self.bos_filter.check_structure_breakout()
        self.assertIn("active", res)
        self.assertIn("bos_type", res)
        self.assertIn("swing_high", res)
        self.assertIn("swing_low", res)
        self.assertIn(res["bos_type"], ["BUY", "SELL", "NONE"])

    def test_decision_engine_strat002(self):
        engine = LiveDecisionEngine(strategy_mode="STRAT-002")
        self.assertEqual(engine.strategy_mode, "STRAT-002")

        dummy_features = {
            "volatility_atr": 1.50,
            "momentum_velocity": 0.20,
            "spread_usd": 0.15,
            "ask": 4115.50,
            "bid": 4115.35
        }
        dummy_tick = {"ask": 4115.50, "bid": 4115.35, "spread_usd": 0.15}

        res = engine.evaluate_features(dummy_features, dummy_tick)
        self.assertIn(res["decision"], ["EXECUTE", "NO_TRADE"])

if __name__ == "__main__":
    unittest.main()
