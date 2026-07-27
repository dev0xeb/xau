#!/usr/bin/env python3
"""
circuit_breaker.py - Production Execution Circuit Breakers

Monitors:
- 5 order rejects within 60 seconds
- Spread > $0.35 / oz
- Latency > 400 ms
- MT5 disconnection

Trips circuit breaker to block order execution when thresholds are breached.
"""

import time
from datetime import datetime, timezone

class CircuitBreaker:

    def __init__(self, max_rejects: int = 5, reject_window_sec: float = 60.0, max_spread_usd: float = 0.35, max_latency_ms: float = 400.0):
        self.max_rejects = max_rejects
        self.reject_window_sec = reject_window_sec
        self.max_spread_usd = max_spread_usd
        self.max_latency_ms = max_latency_ms

        self.reject_timestamps = []
        self.is_tripped = False
        self.trip_reason = ""

    def record_reject(self, reason: str = "BROKER_REJECT"):
        now = time.time()
        self.reject_timestamps.append(now)
        # Purge old rejects
        self.reject_timestamps = [t for t in self.reject_timestamps if now - t <= self.reject_window_sec]

        if len(self.reject_timestamps) >= self.max_rejects:
            self.is_tripped = True
            self.trip_reason = f"EXCEEDED_MAX_REJECTS ({len(self.reject_timestamps)} rejects in 60s)"
            print(f"[CIRCUIT BREAKER TRIPPED] {self.trip_reason}")

    def verify_market_conditions(self, current_spread_usd: float, execution_latency_ms: float, is_connected: bool) -> bool:
        if self.is_tripped:
            return False

        if not is_connected:
            self.is_tripped = True
            self.trip_reason = "BROKER_DISCONNECTED"
            print(f"[CIRCUIT BREAKER TRIPPED] {self.trip_reason}")
            return False

        if current_spread_usd > self.max_spread_usd:
            print(f"[CIRCUIT BREAKER WARN] Spread breach: ${current_spread_usd:.2f} > ${self.max_spread_usd:.2f}")
            return False

        if execution_latency_ms > self.max_latency_ms:
            print(f"[CIRCUIT BREAKER WARN] Latency breach: {execution_latency_ms:.1f}ms > {self.max_latency_ms:.1f}ms")
            return False

        return True

    def reset(self):
        self.reject_timestamps = []
        self.is_tripped = False
        self.trip_reason = ""
        print("[CIRCUIT BREAKER RESET] System restored to active monitoring.")
