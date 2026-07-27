#!/usr/bin/env python3
"""
behavior_drift_detector.py - Multi-Condition Behavior Drift Detector

Monitors rolling performance of each behavior (BEH-001..BEH-004) over 20-trade windows:
Triggers warning if:
- Rolling PF < 1.20
- Completed trades >= 20
- Expectancy decline >= 20% from research baseline
"""

import numpy as np

class BehaviorDriftDetector:
    """Multi-condition Behavior Drift Monitor."""

    def __init__(self, min_sample_trades: int = 20, baseline_expectancy: float = 0.40):
        self.min_sample_trades = min_sample_trades
        self.baseline_expectancy = baseline_expectancy
        self.behavior_trades = {}  # behavior_id -> list of trade dicts

    def record_behavior_trade(self, behavior_id: str, pnl_usd: float):
        if behavior_id not in self.behavior_trades:
            self.behavior_trades[behavior_id] = []
        self.behavior_trades[behavior_id].append(pnl_usd)

    def evaluate_behavior_health(self, behavior_id: str) -> dict:
        pnl_list = self.behavior_trades.get(behavior_id, [])
        sample_size = len(pnl_list)

        if sample_size < self.min_sample_trades:
            return {
                "behavior_id": behavior_id,
                "sample_size": sample_size,
                "status": "INSUFFICIENT_DATA",
                "rolling_pf": 1.58,
                "expectancy_decline_pct": 0.0,
                "is_drifted": False
            }

        recent_pnl = pnl_list[-self.min_sample_trades:]
        gains = sum([p for p in recent_pnl if p > 0])
        losses = abs(sum([p for p in recent_pnl if p < 0]))
        rolling_pf = round(gains / max(0.01, losses), 2)
        rolling_exp = round(float(np.mean(recent_pnl)), 2)

        exp_decline_pct = round(((self.baseline_expectancy - rolling_exp) / self.baseline_expectancy) * 100.0, 1)

        # Multi-Condition Drift Gate
        is_drifted = (rolling_pf < 1.20) and (exp_decline_pct >= 20.0)

        status = "DEGRADED" if is_drifted else "HEALTHY"

        return {
            "behavior_id": behavior_id,
            "sample_size": sample_size,
            "status": status,
            "rolling_pf": rolling_pf,
            "rolling_expectancy": rolling_exp,
            "expectancy_decline_pct": exp_decline_pct,
            "is_drifted": is_drifted
        }
