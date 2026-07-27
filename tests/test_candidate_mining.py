import os
import json
import pytest
from scripts.generate_features import generate_research_features
from scripts.mine_candidate_behaviors import mine_candidates

FIXTURE_M1 = "tests/fixtures/sample_m1_fixture.csv"

def test_candidate_mining_pipeline(tmp_path):
    features_parquet = str(tmp_path / "features.parquet")
    generate_research_features(FIXTURE_M1, features_parquet)

    candidate_dir = str(tmp_path / "candidate_behaviors")
    candidates = mine_candidates(features_parquet, candidate_dir)

    assert os.path.exists(candidate_dir)
    assert len(candidates) > 0
    assert os.path.exists(os.path.join(candidate_dir, "candidate_manifest.json"))

    first_cand = candidates[0]
    assert "candidate_id" in first_cand
    assert "raw_profit_factor" in first_cand
    assert "raw_p_value" in first_cand
    assert first_cand["status"] == "CANDIDATE"
