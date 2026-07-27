import os
import json
import pytest
from scripts.run_stress_testing import run_stress_test_suite

STRATEGY_FILE = "strategy_architecture/STRAT-XAU-001.json"

def test_stress_testing_suite(tmp_path):
    output_dir = str(tmp_path / "stress_tests")
    reports_dir = str(tmp_path / "reports")

    res = run_stress_test_suite(STRATEGY_FILE, output_dir=output_dir, reports_dir=reports_dir)

    assert os.path.exists(output_dir)
    assert os.path.exists(os.path.join(output_dir, "stress_scenarios.json"))
    assert os.path.exists(os.path.join(reports_dir, "stress_test_report.md"))

    assert res["catastrophic_failures"] == 0
    assert res["scenarios_passed"] == len(res["scenarios"])
