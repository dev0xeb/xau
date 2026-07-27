import pytest
from execution_engine.monitoring.circuit_breaker import CircuitBreaker
from execution_engine.monitoring.kill_switch import EmergencyKillSwitch
from execution_engine.adapters.simulation_adapter import SimulationAdapter

def test_circuit_breaker_and_kill_switch(tmp_path):
    cb = CircuitBreaker(max_rejects=3, reject_window_sec=60.0, max_spread_usd=0.35, max_latency_ms=400.0)

    # Verify initial active status
    assert cb.verify_market_conditions(current_spread_usd=0.15, execution_latency_ms=85.0, is_connected=True) is True

    # Record 3 rejects -> Trip Circuit Breaker
    cb.record_reject()
    cb.record_reject()
    cb.record_reject()

    assert cb.is_tripped is True
    assert cb.verify_market_conditions(current_spread_usd=0.15, execution_latency_ms=85.0, is_connected=True) is False

    # Emergency Kill Switch Test
    ks = EmergencyKillSwitch(str(tmp_path / "audit"))
    adapter = SimulationAdapter("XAUUSD")
    adapter.connect()

    res = ks.trigger_emergency_stop(adapter, "TEST_EMERGENCY_STOP")
    assert res["status"] == "SYSTEM_LOCKED_SAFETY_SHUTDOWN"
    assert ks.is_active is True
