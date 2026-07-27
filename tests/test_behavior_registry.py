import os
import json
import pytest
from scripts.generate_features import generate_research_features
from scripts.mine_candidate_behaviors import mine_candidates
from scripts.apply_fdr_control import apply_fdr_corrections
from scripts.validate_walkforward_holdout import validate_walkforward
from scripts.promote_to_registry import promote_candidates
from scripts.generate_opportunity_map import generate_opportunity_map

FIXTURE_M1 = "tests/fixtures/sample_m1_fixture.csv"

def test_behavior_registry_promotion_and_opportunity_map(tmp_path):
    features_parquet = str(tmp_path / "features.parquet")
    generate_research_features(FIXTURE_M1, features_parquet)

    candidate_dir = str(tmp_path / "candidate_behaviors")
    registry_dir = str(tmp_path / "behavior_registry")
    opp_map_md = str(tmp_path / "behavior_opportunity_map.md")

    mine_candidates(features_parquet, candidate_dir)
    apply_fdr_corrections(candidate_dir)
    validate_walkforward(candidate_dir, features_parquet)

    promoted = promote_candidates(candidate_dir, registry_dir)
    assert len(promoted) > 0
    assert os.path.exists(os.path.join(registry_dir, "index.json"))

    first_beh = promoted[0]
    assert first_beh["behavior_id"].startswith("BEH-")
    assert "confidence_score" in first_beh
    assert "regime_dependency_matrix" in first_beh
    assert "failure_patterns" in first_beh
    assert "replication_hash" in first_beh

    # Test opportunity map generation
    total_daily = generate_opportunity_map(registry_dir, opp_map_md)
    assert total_daily > 0
    assert os.path.exists(opp_map_md)
