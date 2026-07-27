import os
import json
import pytest
from scripts.score_behaviors import score_all_behaviors
from scripts.run_decision_engine import run_portfolio_decision_engine

FIXTURE_M1 = "tests/fixtures/sample_m1_fixture.csv"

def test_portfolio_decision_engine(tmp_path):
    scores_dir = str(tmp_path / "behavior_scores")
    portfolio_dir = str(tmp_path / "portfolio_state")
    candidates_dir = str(tmp_path / "execution_candidates")
    reports_dir = str(tmp_path / "reports")

    score_all_behaviors("behavior_registry", FIXTURE_M1, scores_dir)
    candidates = run_portfolio_decision_engine(scores_dir, portfolio_dir, FIXTURE_M1, candidates_dir, reports_dir)

    assert os.path.exists(candidates_dir)
    assert len(candidates) > 0
    assert os.path.exists(os.path.join(candidates_dir, "candidates_manifest.json"))

    first_cand = candidates[0]
    assert "explainability" in first_cand
    assert "opportunity_quality_score" in first_cand
    assert "ranking_tier" in first_cand
    assert first_cand["opportunity_quality_score"] >= 75.0
