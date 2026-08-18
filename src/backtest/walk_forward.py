"""
Walk-Forward Analysis (WFA) Engine Module.

Implements rolling In-Sample (Train) vs. Out-of-Sample (Test) validation
across 5 years of historical data to eliminate parameter overfitting and curve-fitting.
"""

from datetime import datetime, timedelta
import pandas as pd
from typing import List, Dict, Any, Callable
import logging

from src.backtest.types import BacktestConfig
from src.backtest.analytics import AnalyticsEngine

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


class WalkForwardEngine:
    """Orchestrates rolling Walk-Forward Optimization & Validation iterations."""

    def __init__(
        self,
        train_months: int = 12,
        test_months: int = 3,
        config: BacktestConfig = None,
    ):
        self.train_months = train_months
        self.test_months = test_months
        self.config = config or BacktestConfig()

    def generate_windows(
        self, start_date: datetime, end_date: datetime
    ) -> List[Dict[str, datetime]]:
        """Generates rolling train (In-Sample) and test (Out-of-Sample) date windows."""
        windows = []
        current_train_start = pd.to_datetime(start_date)

        while True:
            # Train window end
            train_end = current_train_start + pd.DateOffset(months=self.train_months)
            # Test window end
            test_end = train_end + pd.DateOffset(months=self.test_months)

            if test_end > end_date:
                break

            windows.append({
                "train_start": current_train_start.to_pydatetime(),
                "train_end": train_end.to_pydatetime(),
                "test_start": train_end.to_pydatetime(),
                "test_end": test_end.to_pydatetime(),
            })

            # Step forward by test_months (Rolling window)
            current_train_start = current_train_start + pd.DateOffset(months=self.test_months)

        logger.info(f"Generated {len(windows)} Walk-Forward rolling windows.")
        return windows

    def run_walk_forward(
        self,
        backtest_runner_fn: Callable[[datetime, datetime, BacktestConfig], Dict[str, Any]],
        start_date: datetime,
        end_date: datetime,
    ) -> Dict[str, Any]:
        """Runs walk-forward evaluation across generated windows."""
        windows = self.generate_windows(start_date, end_date)
        if not windows:
            return {"status": "FAILED", "reason": "Date range too small for WFA windows"}

        results = []
        oos_trades_all = []
        is_cagr_list = []
        oos_cagr_list = []

        for idx, w in enumerate(windows, 1):
            logger.info(f"--- WFA Window {idx}/{len(windows)} ---")
            logger.info(f"  Train: {w['train_start'].strftime('%Y-%m-%d')} -> {w['train_end'].strftime('%Y-%m-%d')}")
            logger.info(f"  Test:  {w['test_start'].strftime('%Y-%m-%d')} -> {w['test_end'].strftime('%Y-%m-%d')}")

            # Run In-Sample
            is_result = backtest_runner_fn(w["train_start"], w["train_end"], self.config)
            # Run Out-of-Sample
            oos_result = backtest_runner_fn(w["test_start"], w["test_end"], self.config)

            is_cagr = is_result.get("cagr_pct", 0.0)
            oos_cagr = oos_result.get("cagr_pct", 0.0)

            is_cagr_list.append(is_cagr)
            oos_cagr_list.append(oos_cagr)

            wfe_window = (oos_cagr / is_cagr * 100.0) if is_cagr > 0 else 0.0

            results.append({
                "window": idx,
                "train_range": f"{w['train_start'].strftime('%Y-%m')} to {w['train_end'].strftime('%Y-%m')}",
                "test_range": f"{w['test_start'].strftime('%Y-%m')} to {w['test_end'].strftime('%Y-%m')}",
                "is_profit_factor": is_result.get("profit_factor", 0.0),
                "oos_profit_factor": oos_result.get("profit_factor", 0.0),
                "is_cagr": is_cagr,
                "oos_cagr": oos_cagr,
                "wfe_pct": wfe_window,
            })

        mean_is_cagr = float(pd.Series(is_cagr_list).mean())
        mean_oos_cagr = float(pd.Series(oos_cagr_list).mean())
        overall_wfe = (mean_oos_cagr / mean_is_cagr * 100.0) if mean_is_cagr > 0 else 0.0

        wfa_summary = {
            "total_windows": len(windows),
            "mean_in_sample_cagr": mean_is_cagr,
            "mean_out_of_sample_cagr": mean_oos_cagr,
            "walk_forward_efficiency_wfe": overall_wfe,
            "passed_wfe_threshold": overall_wfe >= 70.0,
            "windows_detail": results,
        }

        logger.info(f"Walk-Forward Analysis Complete. Overall WFE: {overall_wfe:.1f}% (Passed >= 70%: {overall_wfe >= 70.0})")
        return wfa_summary
