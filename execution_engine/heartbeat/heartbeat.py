#!/usr/bin/env python3
"""
heartbeat.py - Production System Multi-Subsystem Health & Heartbeat Monitor

Tracks System Subsystem Health with Monotonic Generation Counter:
- broker_heartbeat
- market_data_heartbeat
- oms_heartbeat
- execution_queue_heartbeat
- decision_engine_heartbeat
- heartbeat_generation (monotonic sequence integer)
"""

import os
import json
from datetime import datetime, timezone

class HeartbeatMonitor:

    def __init__(self, output_dir: str = "execution_engine/heartbeat"):
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)
        self.generation = 0

    def record_heartbeat(
        self,
        broker_alive: bool = True,
        market_data_alive: bool = True,
        oms_alive: bool = True,
        execution_queue_alive: bool = True,
        decision_engine_alive: bool = True,
        queue_depth: int = 0,
        latency_ms: float = 85.0
    ) -> dict:
        self.generation += 1
        now_utc = datetime.now(timezone.utc).isoformat()

        all_subsystems_healthy = all([
            broker_alive,
            market_data_alive,
            oms_alive,
            execution_queue_alive,
            decision_engine_alive
        ])

        health_status = {
            "timestamp_utc": now_utc,
            "heartbeat_generation": self.generation,
            "subsystems": {
                "broker_heartbeat": broker_alive,
                "market_data_heartbeat": market_data_alive,
                "oms_heartbeat": oms_alive,
                "execution_queue_heartbeat": execution_queue_alive,
                "decision_engine_heartbeat": decision_engine_alive
            },
            "queue_depth": queue_depth,
            "last_latency_ms": latency_ms,
            "system_health": "HEALTHY" if (all_subsystems_healthy and queue_depth < 50) else "DEGRADED"
        }

        hb_file = os.path.join(self.output_dir, "system_heartbeat.json")
        with open(hb_file, "w") as f:
            json.dump(health_status, f, indent=2)

        return health_status
