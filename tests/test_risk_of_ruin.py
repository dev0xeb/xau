import os
import json
import pytest
from scripts.simulate_capital_curves import simulate_capital_curves
from scripts.audit_robustness_gates import audit_promotion_gates

STRATEGY_FILE = "strategy_architecture/STRAT-XAU-001.json"

def test_risk_of_ruin_and_promotion_gates(tmp_path):
    curves_dir = str(tmp_path / "capital_curves")
    gate_dir = str(tmp_path / "promotion_gate")
    reports_dir = str(tmp_path / "reports")

    curve_res = simulate_capital_curves(STRATEGY_FILE, n_trajectories=100, output_dir=curves_dir, reports_dir=reports_dir)
    audit_res = audit_promotion_gates(STRATEGY_FILE, output_dir=gate_dir, reports_dir=reports_dir)

    assert curve_res["risk_of_ruin_pct"] < 0.1
    assert curve_res["recovery_factor"] >= 3.0
    assert audit_res["all_gates_passed"] is True
    assert len(audit_res["reproducibility_sha256"]) == 64
    assert os.path.exists(os.path.join(reports_dir, "robustness_report.md"))
