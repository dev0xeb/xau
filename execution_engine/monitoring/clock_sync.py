#!/usr/bin/env python3
"""
clock_sync.py - UTC Clock Synchronization & Drift Monitor

Ensures clock alignment across Broker Time, Server Time, and Local Machine UTC.
Action threshold tiers:
- Drift < 250ms: OK
- 250ms <= Drift < 500ms: WARNING
- 500ms <= Drift < 1000ms: CRITICAL
- Drift >= 1000ms: EXECUTION_HALT
"""

from datetime import datetime, timezone

class ClockSyncMonitor:
    """UTC Clock Drift Verification Engine."""

    def __init__(
        self,
        warning_threshold_ms: float = 250.0,
        critical_threshold_ms: float = 500.0,
        halt_threshold_ms: float = 1000.0
    ):
        self.warning_threshold_ms = warning_threshold_ms
        self.critical_threshold_ms = critical_threshold_ms
        self.halt_threshold_ms = halt_threshold_ms

    def evaluate_clock_drift(self, broker_time_utc: datetime, local_time_utc: datetime = None) -> dict:
        """
        Calculates drift between local UTC clock and broker UTC clock.
        Returns drift evaluation status dict.
        """
        if local_time_utc is None:
            local_time_utc = datetime.now(timezone.utc)

        drift_sec = abs((local_time_utc - broker_time_utc).total_seconds())
        drift_ms = round(drift_sec * 1000.0, 1)

        if drift_ms >= self.halt_threshold_ms:
            status = "EXECUTION_HALT"
            message = f"HALT: Clock drift ({drift_ms}ms) breaches halt threshold ({self.halt_threshold_ms}ms)."
        elif drift_ms >= self.critical_threshold_ms:
            status = "CRITICAL"
            message = f"CRITICAL: Clock drift ({drift_ms}ms) breaches critical threshold ({self.critical_threshold_ms}ms)."
        elif drift_ms >= self.warning_threshold_ms:
            status = "WARNING"
            message = f"WARNING: Clock drift ({drift_ms}ms) breaches warning threshold ({self.warning_threshold_ms}ms)."
        else:
            status = "OK"
            message = f"OK: Clock drift within nominal bounds ({drift_ms}ms)."

        return {
            "status": status,
            "drift_ms": drift_ms,
            "message": message,
            "broker_time_utc": broker_time_utc.isoformat(),
            "local_time_utc": local_time_utc.isoformat()
        }
