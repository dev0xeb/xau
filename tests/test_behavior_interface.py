import os
import json
import pytest
from scripts.score_behaviors import score_all_behaviors

FIXTURE_M1 = "tests/fixtures/sample_m1_fixture.csv"

def test_behavior_interface_utility_and_cis(tmp_path):
    output_dir = str(tmp_path / "behavior_scores")
    scores = score_all_behaviors("behavior_registry", FIXTURE_M1, output_dir)

    assert os.path.exists(output_dir)
    assert len(scores) > 0
    assert os.path.exists(os.path.join(output_dir, "scores_manifest.json"))

    first_score = scores[0]
    assert "expected_utility_score" in first_score
    assert "ci_95_low_usd" in first_score
    assert "ci_95_high_usd" in first_score
    assert "execution_capacity_score" in first_score
    assert first_score["ci_95_low_usd"] <= first_score["expected_value_usd"] <= first_score["ci_95_high_usd"]
