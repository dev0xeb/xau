import os
import json
import pytest
from scripts.run_monte_carlo import run_monte_carlo_simulations

STRATEGY_FILE = "strategy_architecture/STRAT-XAU-001.json"

def test_monte_carlo_simulation_engine(tmp_path):
    output_dir = str(tmp_path / "monte_carlo")
    reports_dir = str(tmp_path / "reports")

    res = run_monte_carlo_simulations(STRATEGY_FILE, n_runs=100, output_dir=output_dir, reports_dir=reports_dir)

    assert os.path.exists(output_dir)
    assert os.path.exists(os.path.join(output_dir, "monte_carlo_runs.json"))
    assert os.path.exists(os.path.join(reports_dir, "monte_carlo_report.md"))

    summary = res["metrics_summary"]
    assert summary["pf_ci_95_low"] >= 1.40
    assert summary["exp_ci_95_low_usd"] >= 0.25
    assert summary["max_dd_ci_95_high_pct"] <= 5.0
