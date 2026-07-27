import os
import json
import pytest
from scripts.generate_features import generate_research_features
from scripts.mine_candidate_behaviors import mine_candidates
from scripts.apply_fdr_control import apply_fdr_corrections

FIXTURE_M1 = "tests/fixtures/sample_m1_fixture.csv"

def test_apply_fdr_control(tmp_path):
    features_parquet = str(tmp_path / "features.parquet")
    generate_research_features(FIXTURE_M1, features_parquet)

    candidate_dir = str(tmp_path / "candidate_behaviors")
    mine_candidates(features_parquet, candidate_dir)

    adjusted = apply_fdr_corrections(candidate_dir, alpha=0.05)
    assert len(adjusted) > 0

    first_cand = adjusted[0]
    assert "bh_q_value" in first_cand
    assert "bonferroni_adjusted_p" in first_cand
    assert "fdr_certified" in first_cand
