import os
import json
import pytest
from scripts.run_sensitivity_analysis import run_sensitivity_sweeps

STRATEGY_FILE = "strategy_architecture/STRAT-XAU-001.json"

def test_sensitivity_analysis(tmp_path):
    output_dir = str(tmp_path / "sensitivity")
    reports_dir = str(tmp_path / "reports")

    res = run_sensitivity_sweeps(STRATEGY_FILE, output_dir=output_dir, reports_dir=reports_dir)

    assert os.path.exists(output_dir)
    assert os.path.exists(os.path.join(output_dir, "sensitivity_sweeps.json"))
    assert os.path.exists(os.path.join(reports_dir, "sensitivity_analysis_report.md"))

    assert res["break_even_spread_limit_usd"] >= 0.35
    assert res["break_even_latency_limit_ms"] >= 180
