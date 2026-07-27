import os
import json
import pytest
from scripts.synthesize_strategy import synthesize_composite_strategy

def test_synthesize_composite_strategy(tmp_path):
    registry_dir = "behavior_registry"
    output_dir = str(tmp_path / "strategy_architecture")

    strat_spec = synthesize_composite_strategy(registry_dir, output_dir, strategy_id="TEST-STRAT-XAU")

    assert os.path.exists(output_dir)
    assert os.path.exists(os.path.join(output_dir, "TEST-STRAT-XAU.json"))
    assert os.path.exists(os.path.join(output_dir, "strategy_manifest.json"))

    assert strat_spec["strategy_health_score"] >= 90.0
    assert len(strat_spec["composite_behaviors"]) > 0

    with open(os.path.join(output_dir, "strategy_manifest.json"), "r") as f:
        manifest = json.load(f)

    assert manifest["strategy_id"] == "TEST-STRAT-XAU"
    assert len(manifest["sha256_checksum"]) == 64
