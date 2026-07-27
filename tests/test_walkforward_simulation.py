import os
import json
import pytest
from scripts.synthesize_strategy import synthesize_composite_strategy
from scripts.simulate_walkforward_portfolio import run_walkforward_simulation

def test_walkforward_portfolio_simulation(tmp_path):
    output_dir = str(tmp_path / "strategy_architecture")
    synthesize_composite_strategy("behavior_registry", output_dir, strategy_id="TEST-STRAT-XAU")

    strat_path = os.path.join(output_dir, "TEST-STRAT-XAU.json")
    reports_dir = str(tmp_path / "reports")

    sim_res = run_walkforward_simulation(strat_path, "data/processed/features/XAUUSD_M1_features.parquet", reports_dir)

    assert sim_res["summary"]["meets_target_benchmark"] is True
    assert sim_res["summary"]["average_executable_daily_trades"] >= 10.0
    assert sim_res["summary"]["average_net_expectancy_usd"] >= 0.30
    assert sim_res["summary"]["peak_max_drawdown_pct"] <= 5.0

    assert os.path.exists(os.path.join(reports_dir, "composite_simulation_report.md"))
