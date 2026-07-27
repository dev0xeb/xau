import os
import json
import pytest
from execution_engine.adapters.simulation_adapter import SimulationAdapter
from execution_engine.oms.oms import OrderManagementSystem

def test_oms_idempotency_and_state_machine(tmp_path):
    oms_dir = str(tmp_path / "oms")
    audit_dir = str(tmp_path / "audit")

    oms = OrderManagementSystem(oms_dir, audit_dir)
    adapter = SimulationAdapter("XAUUSD")
    adapter.connect()

    candidate_payload = {
        "candidate_id": "CAND_TEST_001",
        "execution_uuid": "EXEC_UUID_12345",
        "direction": "BUY",
        "adaptive_risk_pct": 1.0
    }

    # First Execution -> Success
    res1 = oms.process_candidate(candidate_payload, adapter)
    assert res1["oms_state"] == "FILLED"
    assert res1["broker_ticket"] > 0

    # Second Execution with SAME UUID -> Rejected (Idempotency Lock)
    res2 = oms.process_candidate(candidate_payload, adapter)
    assert res2["status"] == "REJECTED_DUPLICATE"

    adapter.disconnect()
