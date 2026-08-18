"""
Quantitative Analytics and Statistical Performance Metrics Engine.

Computes institutional metrics including Sharpe, Sortino, Calmar, Profit Factor,
Expectancy, Max Drawdown, Session Splits, and Tick-Validation Ratios.
"""

from datetime import datetime
import numpy as np
import pandas as pd
from typing import List, Dict, Any, Tuple
import logging

from src.backtest.types import TradeRecord, SignalType, ExitReason

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


class AnalyticsEngine:
    """Computes comprehensive quantitative performance and statistical risk metrics."""

    @staticmethod
    def calculate_metrics(
        trades: List[TradeRecord],
        equity_curve: List[Tuple[datetime, float]],
        initial_balance: float = 10000.0,
    ) -> Dict[str, Any]:
        """Calculates performance report dictionary from trade records and equity curve."""
        if not trades or not equity_curve:
            return {
                "total_trades": 0,
                "net_profit": 0.0,
                "net_profit_pct": 0.0,
                "profit_factor": 0.0,
                "win_rate": 0.0,
                "max_drawdown_pct": 0.0,
                "sharpe_ratio": 0.0,
                "sortino_ratio": 0.0,
                "calmar_ratio": 0.0,
                "tick_validated_ratio": 0.0,
            }

        # Format equity curve DataFrame
        df_equity = pd.DataFrame(equity_curve, columns=["timestamp", "equity"])
        df_equity["timestamp"] = pd.to_datetime(df_equity["timestamp"])
        df_equity.sort_values("timestamp", inplace=True)

        final_equity = df_equity["equity"].iloc[-1]
        net_profit = final_equity - initial_balance
        net_profit_pct = (net_profit / initial_balance) * 100.0

        # Calculate Drawdown series
        df_equity["peak"] = df_equity["equity"].cummax()
        df_equity["drawdown"] = df_equity["equity"] - df_equity["peak"]
        df_equity["drawdown_pct"] = (df_equity["drawdown"] / df_equity["peak"]) * 100.0

        max_dd_dollars = abs(df_equity["drawdown"].min())
        max_dd_pct = abs(df_equity["drawdown_pct"].min())

        # Trade PnL statistics
        pnls = [t.net_pnl for t in trades]
        winning_trades = [p for p in pnls if p > 0]
        losing_trades = [p for p in pnls if p < 0]

        total_trades = len(trades)
        win_count = len(winning_trades)
        loss_count = len(losing_trades)
        win_rate = (win_count / total_trades) * 100.0 if total_trades > 0 else 0.0

        gross_profit = sum(winning_trades) if winning_trades else 0.0
        gross_loss = abs(sum(losing_trades)) if losing_trades else 0.0
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (99.0 if gross_profit > 0 else 0.0)

        avg_win = (gross_profit / win_count) if win_count > 0 else 0.0
        avg_loss = (gross_loss / loss_count) if loss_count > 0 else 0.0

        # Expectancy per trade: E = (WinRate * AvgWin) - (LossRate * AvgLoss)
        win_prob = win_rate / 100.0
        loss_prob = 1.0 - win_prob
        expectancy = (win_prob * avg_win) - (loss_prob * avg_loss)

        # Realized Average R:R
        realized_rr = (avg_win / avg_loss) if avg_loss > 0 else 0.0

        # Max Consecutive Losses
        max_consecutive_losses = 0
        current_streak = 0
        for p in pnls:
            if p < 0:
                current_streak += 1
                max_consecutive_losses = max(max_consecutive_losses, current_streak)
            else:
                current_streak = 0

        # Tick Validation Ratio
        tick_validated_count = sum(1 for t in trades if t.tick_validated)
        tick_validated_ratio = (tick_validated_count / total_trades) * 100.0 if total_trades > 0 else 100.0

        # Daily Returns for Sharpe / Sortino
        df_daily = df_equity.resample("D", on="timestamp").last().dropna()
        df_daily["daily_return"] = df_daily["equity"].pct_change().fillna(0.0)

        returns = df_daily["daily_return"].values
        mean_ret = np.mean(returns)
        std_ret = np.std(returns, ddof=1) if len(returns) > 1 else 0.0

        # Annualized Sharpe Ratio (assuming 252 trading days)
        sharpe_ratio = (mean_ret / std_ret) * np.sqrt(252) if std_ret > 0 else 0.0

        # Downside Deviation for Sortino
        downside_returns = returns[returns < 0]
        downside_std = np.std(downside_returns, ddof=1) if len(downside_returns) > 1 else 0.0
        sortino_ratio = (mean_ret / downside_std) * np.sqrt(252) if downside_std > 0 else 0.0

        # Annualized Return (CAGR) for Calmar
        total_days = max(1, (df_equity["timestamp"].iloc[-1] - df_equity["timestamp"].iloc[0]).days)
        years = total_days / 365.25
        cagr = (((max(0.01, final_equity) / initial_balance) ** (1.0 / years)) - 1.0) * 100.0 if (years > 0 and final_equity > 0) else -100.0
        calmar_ratio = (cagr / max_dd_pct) if max_dd_pct > 0 else 0.0

        # Session Breakdown
        sessions = {}
        for session in ["LONDON", "NY", "OVERLAP", "OFF_HOURS"]:
            s_trades = [t for t in trades if t.session_name == session]
            s_pnl = sum(t.net_pnl for t in s_trades)
            s_wins = sum(1 for t in s_trades if t.net_pnl > 0)
            sessions[session] = {
                "trades": len(s_trades),
                "net_pnl": s_pnl,
                "win_rate": (s_wins / len(s_trades) * 100.0) if s_trades else 0.0,
            }

        return {
            "initial_balance": initial_balance,
            "final_equity": final_equity,
            "net_profit": net_profit,
            "net_profit_pct": net_profit_pct,
            "cagr_pct": cagr,
            "total_trades": total_trades,
            "winning_trades": win_count,
            "losing_trades": loss_count,
            "win_rate": win_rate,
            "profit_factor": profit_factor,
            "expectancy": expectancy,
            "realized_rr": realized_rr,
            "gross_profit": gross_profit,
            "gross_loss": gross_loss,
            "max_drawdown_dollars": max_dd_dollars,
            "max_drawdown_pct": max_dd_pct,
            "max_consecutive_losses": max_consecutive_losses,
            "sharpe_ratio": sharpe_ratio,
            "sortino_ratio": sortino_ratio,
            "calmar_ratio": calmar_ratio,
            "tick_validated_ratio": tick_validated_ratio,
            "session_breakdown": sessions,
        }

    @staticmethod
    def format_report_string(metrics: Dict[str, Any]) -> str:
        """Formats quantitative metrics dictionary into clean markdown report."""
        if not metrics or "initial_balance" not in metrics:
            return "No trades executed in this period."
        s = metrics.get("session_breakdown", {})
        return f"""
======================================================================
 INSTITUTIONAL QUANTITATIVE PERFORMANCE REPORT
======================================================================
  Initial Balance:          ${metrics['initial_balance']:,.2f}
  Final Equity:             ${metrics['final_equity']:,.2f}
  Net Profit:               ${metrics['net_profit']:,.2f} ({metrics['net_profit_pct']:.2f}%)
  Annualized Return (CAGR): {metrics['cagr_pct']:.2f}%
----------------------------------------------------------------------
  Total Executed Trades:    {metrics['total_trades']:,}
  Win Rate:                 {metrics['win_rate']:.2f}% ({metrics['winning_trades']} W / {metrics['losing_trades']} L)
  Profit Factor:            {metrics['profit_factor']:.2f}
  Expectancy per Trade:     ${metrics['expectancy']:.2f}
  Realized Risk-to-Reward:  1:{metrics['realized_rr']:.2f}
----------------------------------------------------------------------
  Max Drawdown:             -${metrics['max_drawdown_dollars']:,.2f} (-{metrics['max_drawdown_pct']:.2f}%)
  Max Consecutive Losses:   {metrics['max_consecutive_losses']}
  Sharpe Ratio:             {metrics['sharpe_ratio']:.2f}
  Sortino Ratio:            {metrics['sortino_ratio']:.2f}
  Calmar Ratio:             {metrics['calmar_ratio']:.2f}
  Tick Validation Ratio:    {metrics['tick_validated_ratio']:.1f}%
----------------------------------------------------------------------
 Session Breakdown:
  - London Session:   {s.get('LONDON', {}).get('trades', 0)} trades | Win: {s.get('LONDON', {}).get('win_rate', 0):.1f}% | PnL: ${s.get('LONDON', {}).get('net_pnl', 0):,.2f}
  - NY Session:       {s.get('NY', {}).get('trades', 0)} trades | Win: {s.get('NY', {}).get('win_rate', 0):.1f}% | PnL: ${s.get('NY', {}).get('net_pnl', 0):,.2f}
  - London/NY Overlap: {s.get('OVERLAP', {}).get('trades', 0)} trades | Win: {s.get('OVERLAP', {}).get('win_rate', 0):.1f}% | PnL: ${s.get('OVERLAP', {}).get('net_pnl', 0):,.2f}
======================================================================
"""
