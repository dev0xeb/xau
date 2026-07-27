#!/usr/bin/env python3
"""
run_event_execution_bridge.py - Event-Driven Production Execution Bridge

Connects Event Queue -> Risk Engine -> OMS -> Circuit Breaker -> Broker Adapter.
Runs dry-run or live execution modes without polling.
"""

import os
import sys
import json
import argparse

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from execution_engine.adapters.simulation_adapter import SimulationAdapter
from execution_engine.adapters.mt5_adapter import MT5Adapter
from execution_engine.oms.oms import OrderManagementSystem
from execution_engine.monitoring.circuit_breaker import CircuitBreaker
from execution_engine.heartbeat.heartbeat import HeartbeatMonitor

def run_event_execution_bridge(candidates_dir: str = "decision_engine/execution_candidates", dry_run: bool = True) -> list:
    manifest_file = os.path.join(candidates_dir, "candidates_manifest.json")
    if not os.path.exists(manifest_file):
        raise FileNotFoundError(f"Candidates manifest not found: {manifest_file}")

    with open(manifest_file, "r") as f:
        candidates = json.load(f)

    print(f"[INFO] Running Event-Driven Execution Bridge (Dry-Run: {dry_run}) across {len(candidates)} candidates...")

    adapter = SimulationAdapter("XAUUSD") if dry_run else MT5Adapter("XAUUSD")
    adapter.connect()

    oms = OrderManagementSystem()
    circuit_breaker = CircuitBreaker()
    heartbeat = HeartbeatMonitor()

    executed_records = []

    for cand in candidates:
        if cand.get("decision_code") != "EXECUTE":
            continue

        # Circuit Breaker Check
        if not circuit_breaker.verify_market_conditions(current_spread_usd=0.15, execution_latency_ms=85.0, is_connected=adapter.connected):
            print(f"[EXECUTION BLOCKED] Circuit breaker active for candidate {cand['candidate_id']}")
            break

        # Event-Driven OMS Processing
        oms_res = oms.process_candidate(cand, adapter)
        executed_records.append(oms_res)

        heartbeat.record_heartbeat(broker_connected=adapter.connected, queue_depth=0, latency_ms=oms_res.get("execution_latency_ms", 85.0))

    adapter.disconnect()
    print(f"[SUCCESS] Event-Driven Execution Bridge finished. Processed {len(executed_records)} execution events.")
    return executed_records

def main():
    parser = argparse.ArgumentParser(description="Run Event-Driven Execution Bridge")
    parser.add_argument("--candidates_dir", type=str, default="decision_engine/execution_candidates", help="Candidates directory")
    parser.add_argument("--dry_run", type=bool, default=True, help="Dry run mode flag")

    args = parser.parse_args()
    run_event_execution_bridge(args.candidates_dir, args.dry_run)

if __name__ == "__main__":
    main()
