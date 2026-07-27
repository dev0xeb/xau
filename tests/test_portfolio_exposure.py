import os
import json
import pytest
from scripts.synthesize_strategy import synthesize_composite_strategy
from scripts.audit_strategy_risk import audit_strategy_risk

def test_portfolio_exposure_rules(tmp_path):
    output_dir = str(tmp_path / "strategy_architecture")
    synthesize_composite_strategy("behavior_registry", output_dir, strategy_id="TEST-STRAT-XAU")

    strat_path = os.path.join(output_dir, "TEST-STRAT-XAU.json")
    reports_dir = str(tmp_path / "reports")
    audit_res = audit_strategy_risk(strat_path, reports_dir)

    assert audit_res["is_healthy"] is True
    assert os.path.exists(os.path.join(reports_dir, "strategy_health_card.md"))
    assert os.path.exists(os.path.join(reports_dir, "risk_and_arbitration_spec.md"))
