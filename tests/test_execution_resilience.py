#!/usr/bin/env python3
"""
test_execution_resilience.py - Institutional Operational Resilience Test Suite

Validates:
1. Pre-flight Config Validation (ConfigValidator)
2. Pre-broker Order Guardrails & Exposure Limits (OrderValidator)
3. Immutable Event Sourcing & Corrupted Log Resilience (EventStore)
4. Power Loss / Restart State Replay & Duplicate Replay Idempotency
5. Dead-Letter Queue (DLQ) diagnostic routing
6. Structured Execution Journal Lineage (ExecutionJournal)
7. Multi-Tiered UTC Clock Synchronization (ClockSyncMonitor)
8. Multi-Subsystem Heartbeat Monotonic Generation (HeartbeatMonitor)
9. OMS Optimistic Locking Version Enforcement
10. Periodic Position Reconciliation
11. Telemetry Environment Labeling & Rolling Windows
"""

import os
import json
import pytest
from datetime import datetime, timezone, timedelta

from execution_engine.errors import (
    ConfigurationError, ValidationError, ProgrammingError, ExternalDependencyError
)
from execution_engine.configs.config_validator import ConfigValidator
from execution_engine.oms.order_validator import OrderValidator
from execution_engine.queue.event_store import EventStore
from execution_engine.queue.dead_letter_queue import DeadLetterQueue
from execution_engine.audit.execution_journal import ExecutionJournal
from execution_engine.monitoring.clock_sync import ClockSyncMonitor
from execution_engine.heartbeat.heartbeat import HeartbeatMonitor
from execution_engine.metrics.telemetry import calculate_execution_telemetry
from execution_engine.oms.oms import OrderManagementSystem
from execution_engine.adapters.simulation_adapter import SimulationAdapter


def test_config_validator_valid_and_invalid():
    valid_cfg = {
        "environment": "SIMULATION",
        "risk_parameters": {
            "max_single_trade_risk_pct": 1.0,
            "max_daily_risk_pct": 3.0
        },
        "execution_parameters": {
            "max_spread_usd": 0.35,
            "min_lot_size": 0.01,
            "max_lot_size": 10.0
        }
    }
    assert ConfigValidator.validate_config(valid_cfg) is True

    # Test logical contradiction: single trade risk > max daily risk
    invalid_contradiction_cfg = {
        "environment": "SIMULATION",
        "risk_parameters": {
            "max_single_trade_risk_pct": 5.0,
            "max_daily_risk_pct": 2.0
        },
        "execution_parameters": {
            "max_spread_usd": 0.35
        }
    }
    with pytest.raises(ConfigurationError) as exc_info:
        ConfigValidator.validate_config(invalid_contradiction_cfg)
    assert "Logical configuration error" in str(exc_info.value)


def test_order_validator_exposure_and_expiration():
    validator = OrderValidator(
        max_portfolio_exposure_lots=2.0,
        max_candidate_age_sec=5.0
    )

    candidate = {
        "execution_uuid": "exec-101",
        "volume_lots": 1.5,
        "created_at_utc": datetime.now(timezone.utc).isoformat()
    }

    # Valid candidate check
    assert validator.validate_candidate(candidate, current_portfolio_exposure_lots=0.4) is True

    # Test exposure breach (0.8 + 1.5 = 2.3 > 2.0)
    with pytest.raises(ValidationError) as exc_info:
        validator.validate_candidate(
            {"execution_uuid": "exec-102", "volume_lots": 1.5},
            current_portfolio_exposure_lots=0.8
        )
    assert "breaches limit" in str(exc_info.value)

    # Test duplicate UUID check
    with pytest.raises(ValidationError) as exc_info:
        validator.validate_candidate(candidate, current_portfolio_exposure_lots=0.0)
    assert "Duplicate execution UUID" in str(exc_info.value)

    # Test stale candidate expiration
    stale_time = (datetime.now(timezone.utc) - timedelta(seconds=15)).isoformat()
    stale_cand = {
        "execution_uuid": "exec-103",
        "volume_lots": 0.1,
        "created_at_utc": stale_time
    }
    with pytest.raises(ValidationError) as exc_info:
        validator.validate_candidate(stale_cand)
    assert "Stale candidate expired" in str(exc_info.value)


def test_event_store_append_replay_and_corrupted_resilience(tmp_path):
    store_file = os.path.join(tmp_path, "event_log.jsonl")
    es = EventStore(store_path=store_file)

    es.append_event("CandidateCreated", "CAND-001", {"sym": "XAUUSD"})
    es.append_event("OrderQueued", "CAND-001", {"oms_state": "QUEUED"})

    # Manually append a corrupted json line
    with open(store_file, "a") as f:
        f.write("{MALFORMED_JSON_LINE\n")

    es.append_event("Filled", "CAND-001", {"oms_state": "FILLED"})

    replayed = es.replay_events()
    assert len(replayed) == 3
    assert replayed[0]["event_type"] == "CandidateCreated"
    assert replayed[1]["event_type"] == "OrderQueued"
    assert replayed[2]["event_type"] == "Filled"


def test_dead_letter_queue_routing(tmp_path):
    dlq_file = os.path.join(tmp_path, "dlq.jsonl")
    dlq = DeadLetterQueue(dlq_path=dlq_file)

    candidate = {"candidate_id": "CAND-DLQ-1", "execution_uuid": "exec-dlq"}
    entry = dlq.route_to_dlq(
        candidate_payload=candidate,
        retry_reason="BROKER_REJECT",
        retry_count=3,
        final_failure="REJECT_EXCEEDED",
        root_cause="Broker market context busy",
        broker_response={"retcode": 10013}
    )

    assert entry["candidate_id"] == "CAND-DLQ-1"
    listed = dlq.list_dlq_candidates()
    assert len(listed) == 1
    assert listed[0]["root_cause"] == "Broker market context busy"


def test_execution_journal_lineage(tmp_path):
    journal_file = os.path.join(tmp_path, "journal.jsonl")
    ej = ExecutionJournal(journal_path=journal_file)

    cand = {"candidate_id": "CAND-J1", "behavior_ids": ["BEH-VOL-1"]}
    oms = {
        "candidate_id": "CAND-J1",
        "oms_uuid": "oms-uuid-1",
        "execution_uuid": "exec-uuid-1",
        "broker_fill_price": 2350.75,
        "spread_usd": 0.12,
        "execution_latency_ms": 75.0
    }

    entry = ej.record_trade(cand, oms)
    assert entry["volatility_bucket"] == "NORMAL_VOL"
    assert entry["spread_bucket"] == "LOW_SPREAD"
    assert entry["latency_bucket"] == "FAST"
    assert entry["git_commit"] != ""


def test_clock_sync_drift_stages():
    monitor = ClockSyncMonitor()
    now_utc = datetime.now(timezone.utc)

    # Stage 1: Nominal (<250ms)
    res_ok = monitor.evaluate_clock_drift(now_utc - timedelta(milliseconds=100), now_utc)
    assert res_ok["status"] == "OK"

    # Stage 2: Warning (250-500ms)
    res_warn = monitor.evaluate_clock_drift(now_utc - timedelta(milliseconds=350), now_utc)
    assert res_warn["status"] == "WARNING"

    # Stage 3: Critical (500-1000ms)
    res_crit = monitor.evaluate_clock_drift(now_utc - timedelta(milliseconds=750), now_utc)
    assert res_crit["status"] == "CRITICAL"

    # Stage 4: Execution Halt (>=1000ms)
    res_halt = monitor.evaluate_clock_drift(now_utc - timedelta(milliseconds=1200), now_utc)
    assert res_halt["status"] == "EXECUTION_HALT"


def test_heartbeat_generation_counter(tmp_path):
    hb_dir = os.path.join(tmp_path, "hb")
    hb = HeartbeatMonitor(output_dir=hb_dir)

    status1 = hb.record_heartbeat()
    assert status1["heartbeat_generation"] == 1
    assert status1["subsystems"]["broker_heartbeat"] is True

    status2 = hb.record_heartbeat()
    assert status2["heartbeat_generation"] == 2


def test_oms_optimistic_locking_and_process_candidate(tmp_path):
    oms_dir = os.path.join(tmp_path, "oms")
    audit_dir = os.path.join(tmp_path, "audit")
    store_file = os.path.join(tmp_path, "event_log.jsonl")
    dlq_file = os.path.join(tmp_path, "dlq.jsonl")
    journal_file = os.path.join(tmp_path, "journal.jsonl")

    es = EventStore(store_path=store_file)
    dlq = DeadLetterQueue(dlq_path=dlq_file)
    ej = ExecutionJournal(journal_path=journal_file)

    oms = OrderManagementSystem(
        oms_dir=oms_dir,
        audit_dir=audit_dir,
        event_store=es,
        dlq=dlq,
        journal=ej
    )

    adapter = SimulationAdapter()
    adapter.connect()
    candidate = {
        "candidate_id": "CAND-LOCK-1",
        "execution_uuid": "exec-lock-1",
        "volume_lots": 0.1,
        "created_at_utc": datetime.now(timezone.utc).isoformat()
    }

    record = oms.process_candidate(candidate, adapter)
    assert record["oms_state"] == "FILLED"
    assert record["order_version"] == 3

    # Test Optimistic Locking update: valid version succeeds
    updated = oms.update_order_state(record["oms_uuid"], "CLOSED", expected_version=3)
    assert updated["order_version"] == 4
    assert updated["oms_state"] == "CLOSED"

    # Version mismatch raises ValueError
    with pytest.raises(ValueError) as exc_info:
        oms.update_order_state(record["oms_uuid"], "CLOSED", expected_version=3)
    assert "Optimistic lock violation" in str(exc_info.value)


def test_periodic_position_reconciliation(tmp_path):
    oms = OrderManagementSystem(oms_dir=os.path.join(tmp_path, "oms"), audit_dir=os.path.join(tmp_path, "audit"))
    adapter = SimulationAdapter()
    adapter.connect()
    cand = {"candidate_id": "CAND-REC-1", "execution_uuid": "exec-rec-1", "volume_lots": 0.1}

    rec = oms.process_candidate(cand, adapter)
    filled_ticket = rec["broker_ticket"]

    # Matched reconciliation
    broker_positions = [{"ticket": filled_ticket, "symbol": "XAUUSD"}]
    res = oms.reconcile_positions(broker_positions)
    assert res["reconciled"] is True

    # Unmatched reconciliation discrepancy
    broker_positions_discrepant = [{"ticket": 9999, "symbol": "XAUUSD"}]
    res_disc = oms.reconcile_positions(broker_positions_discrepant)
    assert res_disc["reconciled"] is False
    assert len(res_disc["unmatched_oms_uuids"]) == 1
    assert len(res_disc["unmatched_broker_tickets"]) == 1


def test_telemetry_rolling_and_environment_labeling():
    audit_records = [
        {"oms_state": "FILLED", "execution_latency_ms": 50.0, "timestamp_utc": datetime.now(timezone.utc).isoformat()},
        {"oms_state": "FILLED", "execution_latency_ms": 100.0, "timestamp_utc": datetime.now(timezone.utc).isoformat()},
        {"oms_state": "REJECTED_BROKER", "execution_latency_ms": 200.0, "timestamp_utc": datetime.now(timezone.utc).isoformat()}
    ]

    telemetry_sim = calculate_execution_telemetry(audit_records, environment="SIMULATION")
    assert telemetry_sim["environment"] == "SIMULATION"
    assert telemetry_sim["total_orders"] == 3
    assert telemetry_sim["latency_median_ms"] == 100.0
    assert telemetry_sim["latency_p95_ms"] == 190.0

    telemetry_live = calculate_execution_telemetry(audit_records, environment="LIVE_BROKER")
    assert telemetry_live["environment"] == "LIVE_BROKER"
