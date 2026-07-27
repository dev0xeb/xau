import os
import pytest
from execution_engine.adapters.simulation_adapter import SimulationAdapter
from execution_engine.adapters.mt5_adapter import MT5Adapter

def test_broker_adapter_interface():
    sim_adapter = SimulationAdapter("XAUUSD")
    assert sim_adapter.connect() is True

    account = sim_adapter.get_account_info()
    assert account["balance"] == 100000.0

    order_res = sim_adapter.place_order({"direction": "BUY", "volume_lots": 0.1, "candidate_id": "TEST_CAND_01"})
    assert order_res["success"] is True
    assert order_res["ticket"] > 0

    assert sim_adapter.disconnect() is True
