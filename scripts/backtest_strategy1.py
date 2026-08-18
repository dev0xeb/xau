"""
End-to-End Backtest, Walk-Forward Analysis, and Monte Carlo Stress Test for Strategy 1.

Evaluates Strategy 1 (SMC Liquidity Sweep, CHoCH & FVG Reversal) across 5 years of XAU/USD data.
"""

from datetime import datetime, timezone
from pathlib import Path
import sys
import pandas as pd
import logging

# Add src to python path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.backtest.types import BacktestConfig
from src.backtest.engine import BacktestEngine
from src.backtest.walk_forward import WalkForwardEngine
from src.backtest.monte_carlo import MonteCarloEngine
from src.strategies.smc_sweep_fvg import SMCSweepFVGStrategy

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def main():
    print("=" * 70)
    print(" STRATEGY 1: SMC LIQUIDITY SWEEP, CHOCH & FVG REVERSAL BACKTEST")
    print("=" * 70)

    raw_1m_path = Path("data/raw/xau_1m_5y.parquet")
    proc_5m_path = Path("data/processed/xau_5m_5y.parquet")
    proc_15m_path = Path("data/processed/xau_15m_5y.parquet")

    if not (raw_1m_path.exists() and proc_5m_path.exists() and proc_15m_path.exists()):
        print("[ERROR] Datasets missing! Run python scripts/download_xau_data.py first.")
        sys.exit(1)

    print("\n[LOAD] Loading 5-Year Parquet Datasets (2021-2026)...")
    df_1m = pd.read_parquet(raw_1m_path)
    df_5m = pd.read_parquet(proc_5m_path)
    df_15m = pd.read_parquet(proc_15m_path)

    config = BacktestConfig(
        initial_balance=10000.0,
        risk_pct=1.0,
        max_spread_points=30,
        slippage_pips=0.2,
        commission_per_lot=7.0,
    )

    strategy = SMCSweepFVGStrategy()
    engine = BacktestEngine(df_1m=df_1m, df_5m=df_5m, df_15m=df_15m, config=config)

    # Step 1: Full 5-Year Backtest
    print("\n[1/3] Executing Full 5-Year Backtest Engine (1.98M Bars)...")
    results = engine.run(strategies=[strategy])

    print(results.get("report_str", ""))

    trades = results.get("trades", [])

    # Step 2: Walk-Forward Analysis (WFA) - 12M Train / 6M Test
    print("\n[2/3] Executing Walk-Forward Analysis (12M Train / 6M Test)...")
    wfa_engine = WalkForwardEngine(train_months=12, test_months=6, config=config)

    def wfa_runner_fn(start_dt, end_dt, cfg):
        sub_engine = BacktestEngine(df_1m=df_1m, df_5m=df_5m, df_15m=df_15m, config=cfg)
        sub_strat = SMCSweepFVGStrategy()
        res = sub_engine.run(strategies=[sub_strat], start_date=start_dt, end_date=end_dt)
        return res.get("metrics", {})

    start_date = df_1m["timestamp"].min().to_pydatetime()
    end_date = df_1m["timestamp"].max().to_pydatetime()

    wfa_summary = wfa_engine.run_walk_forward(wfa_runner_fn, start_date=start_date, end_date=end_date)

    print("\n----------------------------------------------------------------------")
    print(f" Walk-Forward Efficiency (WFE): {wfa_summary.get('walk_forward_efficiency_wfe', 0.0):.1f}%")
    print(f" Mean In-Sample CAGR:          {wfa_summary.get('mean_in_sample_cagr', 0.0):.2f}%")
    print(f" Mean Out-of-Sample CAGR:      {wfa_summary.get('mean_out_of_sample_cagr', 0.0):.2f}%")
    print(f" Passed WFE Target (>= 70%):   {'YES' if wfa_summary.get('passed_wfe_threshold', False) else 'NO'}")
    print("----------------------------------------------------------------------")

    # Step 3: Multi-Variable Monte Carlo Simulation (1,000 Runs)
    print("\n[3/3] Executing 1,000-Run Multi-Variable Monte Carlo Simulation...")
    mc_engine = MonteCarloEngine(n_simulations=1000, ruin_threshold_pct=20.0, config=config)
    mc_summary = mc_engine.run_simulation(trades=trades, initial_balance=config.initial_balance)

    print("\n----------------------------------------------------------------------")
    print(f" Empirical Risk of Ruin (at 20% DD): {mc_summary['empirical_risk_of_ruin_pct']:.2f}%")
    print(f" Median Max Drawdown:                 {mc_summary['median_max_dd_pct']:.2f}%")
    print(f" 95th Percentile Max Drawdown:       {mc_summary['95th_percentile_max_dd_pct']:.2f}%")
    print(f" Worst-Case Drawdown:                 {mc_summary['worst_case_dd_pct']:.2f}%")
    print(f" Passed Risk of Ruin Test (< 1%):     {'YES' if mc_summary['passed_ruin_test'] else 'NO'}")
    print("----------------------------------------------------------------------")

    print("\n" + "=" * 70)
    print(" Strategy 1 Evaluation Completed!")
    print("=" * 70)


if __name__ == "__main__":
    main()
