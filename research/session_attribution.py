#!/usr/bin/env python3
"""
session_attribution.py - Micro-Session Classification & Performance Attribution

Classifies trade timestamps into 8 micro-sessions:
1. Asian (22:00 - 07:00 UTC)
2. London Open (07:00 - 09:00 UTC)
3. London Mid (09:00 - 12:00 UTC)
4. London Close (12:00 - 13:00 UTC)
5. London/NY Overlap (13:00 - 16:00 UTC)
6. NY Open (13:30 - 15:30 UTC)
7. NY Mid (16:00 - 19:00 UTC)
8. NY Close (19:00 - 21:00 UTC)
"""

from datetime import datetime, timezone

class SessionAttributionEngine:
    """Micro-Session Classifier and Attribution Engine."""

    @staticmethod
    def classify_micro_session(timestamp_utc_str: str) -> str:
        """
        Classifies UTC timestamp string into micro-session bucket.
        """
        try:
            dt = datetime.fromisoformat(timestamp_utc_str)
        except Exception:
            dt = datetime.now(timezone.utc)

        hour = dt.hour
        minute = dt.minute
        time_decimal = hour + (minute / 60.0)

        if 7.0 <= time_decimal < 9.0:
            return "London Open"
        elif 9.0 <= time_decimal < 12.0:
            return "London Mid"
        elif 12.0 <= time_decimal < 13.0:
            return "London Close"
        elif 13.0 <= time_decimal < 16.0:
            if 13.5 <= time_decimal <= 15.5:
                return "NY Open"
            return "Overlap"
        elif 16.0 <= time_decimal < 19.0:
            return "NY Mid"
        elif 19.0 <= time_decimal < 21.0:
            return "NY Close"
        else:
            return "Asian"

    @staticmethod
    def calculate_session_performance(trade_records: list) -> dict:
        """
        Aggregates PnL and trade counts per micro-session.
        """
        breakdown = {}
        for r in trade_records:
            t_str = r.get("created_at_utc") or r.get("timestamp_utc", "")
            session = SessionAttributionEngine.classify_micro_session(t_str)

            if session not in breakdown:
                breakdown[session] = {"trades": 0, "wins": 0, "pnl_usd": 0.0}

            breakdown[session]["trades"] += 1
            pnl = r.get("pnl_usd", 0.0)
            breakdown[session]["pnl_usd"] += pnl
            if pnl > 0:
                breakdown[session]["wins"] += 1

        for s, data in breakdown.items():
            data["win_rate_pct"] = round((data["wins"] / max(1, data["trades"])) * 100.0, 1)
            data["pnl_usd"] = round(data["pnl_usd"], 2)

        return breakdown
