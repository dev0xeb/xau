#!/usr/bin/env python3
"""
infrastructure_reliability_scorer.py - Infrastructure Reliability Scorer

Tracks daily system operational metrics:
- Uptime % (target: >= 99.9%)
- Tick loss % (target: <= 0.05%)
- Reconnect count
- Heartbeat failures
- Broker disconnects
- Overall Infrastructure Score (0 - 100)
"""

class InfrastructureReliabilityScorer:
    """Calculates daily system infrastructure reliability score."""

    @staticmethod
    def calculate_reliability_score(
        total_active_seconds: float = 86400.0,
        downtime_seconds: float = 0.0,
        expected_ticks: int = 100000,
        received_ticks: int = 99990,
        reconnect_count: int = 0,
        heartbeat_failures: int = 0,
        broker_disconnects: int = 0
    ) -> dict:
        uptime_pct = round(((total_active_seconds - downtime_seconds) / max(1.0, total_active_seconds)) * 100.0, 3)
        tick_loss_pct = round(((expected_ticks - received_ticks) / max(1, expected_ticks)) * 100.0, 3)

        # Deduct penalties from base score 100.0
        score = 100.0
        score -= (100.0 - uptime_pct) * 10.0
        score -= tick_loss_pct * 20.0
        score -= reconnect_count * 2.0
        score -= heartbeat_failures * 5.0
        score -= broker_disconnects * 5.0

        final_score = max(0.0, min(100.0, round(score, 1)))

        return {
            "uptime_pct": uptime_pct,
            "tick_loss_pct": tick_loss_pct,
            "reconnect_count": reconnect_count,
            "heartbeat_failures": heartbeat_failures,
            "broker_disconnects": broker_disconnects,
            "reliability_score": final_score,
            "is_healthy": final_score >= 95.0
        }
