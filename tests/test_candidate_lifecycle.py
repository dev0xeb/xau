import os
import json
import pytest
from scripts.score_behaviors import score_all_behaviors
from scripts.run_decision_engine import run_portfolio_decision_engine
from scripts.simulate_virtual_execution import run_virtual_execution

FIXTURE_M1 = "tests/fixtures/sample_m1_fixture.csv"

def test_candidate_lifecycle_and_telemetry(tmp_path):
    scores_dir = str(tmp_path / "behavior_scores")
    portfolio_dir = str(tmp_path / "portfolio_state")
    candidates_dir = str(tmp_path / "execution_candidates")
    reports_dir = str(tmp_path / "reports")
    logs_dir = str(tmp_path / "decision_logs")

    score_all_behaviors("behavior_registry", FIXTURE_M1, scores_dir)
    run_portfolio_decision_engine(scores_dir, portfolio_dir, FIXTURE_M1, candidates_dir, reports_dir)
    telemetry = run_virtual_execution(candidates_dir, FIXTURE_M1, reports_dir, logs_dir)

    assert telemetry["fill_rate_pct"] >= 90.0
    assert telemetry["total_filled_trades"] > 0
    assert os.path.exists(os.path.join(reports_dir, "virtual_execution_report.md"))
    assert os.path.exists(logs_dir)
