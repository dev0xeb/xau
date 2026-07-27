#!/usr/bin/env python3
"""
regime_database.py - Market Regime History Logger & Database

Maintains continuous market regime timeline logs (regimes/YYYY-MM-DD.json):
- TREND_UP
- TREND_DOWN
- RANGE
- HIGH_VOLATILITY
- NEWS

Enables post-campaign regime attribution analysis across all trades.
"""

import os
import json
from datetime import datetime, timezone

class MarketRegimeDatabase:
    """Market Regime Timeline Logger and Manager."""

    def __init__(self, regime_dir: str = "regimes"):
        self.regime_dir = regime_dir
        os.makedirs(self.regime_dir, exist_ok=True)
        self.current_regime = "NORMAL"

    def record_regime_transition(self, regime_name: str, metrics_snapshot: dict = None) -> dict:
        """Records a market regime transition event."""
        now_dt = datetime.now(timezone.utc)
        date_str = now_dt.strftime("%Y-%m-%d")
        time_str = now_dt.strftime("%H:%M:%S")

        entry = {
            "timestamp_utc": now_dt.isoformat(),
            "time_key": time_str,
            "regime": regime_name,
            "prev_regime": self.current_regime,
            "metrics": metrics_snapshot or {}
        }
        self.current_regime = regime_name

        file_path = os.path.join(self.regime_dir, f"{date_str}.json")
        entries = []
        if os.path.exists(file_path):
            try:
                with open(file_path, "r") as f:
                    entries = json.load(f)
            except Exception:
                entries = []

        entries.append(entry)
        with open(file_path, "w") as f:
            json.dump(entries, f, indent=2)

        return entry

    def get_current_regime(self) -> str:
        return self.current_regime
