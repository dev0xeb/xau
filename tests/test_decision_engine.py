import os
import json
import pytest
from scripts.calibrate_confidence import calibrate_behavior_confidence
from scripts.optimize_portfolio import optimize_portfolio_constraints
from scripts.score_behaviors import score_all_behaviors
from scripts.run_decision_engine import run_portfolio_decision_engine

FIXTURE_M1 = "tests/fixtures/sample_m1_fixture.csv"

def test_calibration_and_portfolio_optimizer(tmp_path):
    output_scores = str(tmp_path / "behavior_scores")
    output_portfolio = str(tmp_path / "portfolio_state")
    output_candidates = str(tmp_path / "execution_candidates")
    output_reports = str(tmp_path / "reports")

    cal_res = calibrate_behavior_confidence("behavior_registry", output_scores)
    assert cal_res["behaviors_calibrated"] > 0

    port_state = optimize_portfolio_constraints(output_portfolio)
    assert "current_portfolio_heat_pct" in port_state
    assert port_state["portfolio_heat_limit_pct"] == 5.0

    score_all_behaviors("behavior_registry", FIXTURE_M1, output_scores)
    candidates = run_portfolio_decision_engine(output_scores, output_portfolio, FIXTURE_M1, output_candidates, output_reports)

    first_cand = candidates[0]
    assert "candidate_hash" in first_cand
    assert len(first_cand["candidate_hash"]) == 64
    assert "decision_provenance" in first_cand
    assert os.path.exists(os.path.join(output_reports, "portfolio_heat_report.md"))
    assert os.path.exists(os.path.join(output_reports, "opportunity_quality_distribution.md"))
