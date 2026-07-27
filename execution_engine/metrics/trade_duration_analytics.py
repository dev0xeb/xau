#!/usr/bin/env python3
"""
trade_duration_analytics.py - Trade Hold Duration Analytics Engine

Calculates duration statistics across trade records:
- median_hold_min
- average_hold_min
- winning_hold_min
- losing_hold_min
- longest_hold_min
"""

import numpy as np
from datetime import datetime

class TradeDurationAnalytics:
    """Calculates trade hold duration metrics."""

    @staticmethod
    def calculate_duration_metrics(trade_records: list) -> dict:
        if not trade_records:
            return {
                "median_hold_min": 0.0,
                "average_hold_min": 0.0,
                "winning_hold_min": 0.0,
                "losing_hold_min": 0.0,
                "longest_hold_min": 0.0
            }

        all_durations = []
        win_durations = []
        loss_durations = []

        for r in trade_records:
            duration_min = r.get("duration_min")
            if duration_min is None:
                # Attempt calculation from timestamps
                t_open = r.get("created_at_utc")
                t_close = r.get("closed_at_utc")
                if t_open and t_close:
                    try:
                        d1 = datetime.fromisoformat(t_open)
                        d2 = datetime.fromisoformat(t_close)
                        duration_min = max(0.1, (d2 - d1).total_seconds() / 60.0)
                    except Exception:
                        duration_min = 5.0
                else:
                    duration_min = 5.0

            all_durations.append(duration_min)
            if r.get("pnl_usd", 0.0) > 0:
                win_durations.append(duration_min)
            else:
                loss_durations.append(duration_min)

        return {
            "median_hold_min": round(float(np.median(all_durations)), 1),
            "average_hold_min": round(float(np.mean(all_durations)), 1),
            "winning_hold_min": round(float(np.mean(win_durations)), 1) if win_durations else 0.0,
            "losing_hold_min": round(float(np.mean(loss_durations)), 1) if loss_durations else 0.0,
            "longest_hold_min": round(float(np.max(all_durations)), 1)
        }
