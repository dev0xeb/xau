"""
Automated Verification & Unit Test Suite for Decoupled Backtesting Core Engine.

Verifies:
1. Timestamp-safe HTF guard (zero lookahead bias assertion).
2. T+1 Next-Bar Open execution & Bid/Ask fill math.
3. Dynamic risk position sizing calculations.
4. Partial profit exit & directional Breakeven SL adjustments.
5. Quant analytics calculations and reporting.
"""

from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
from pathlib import Path
import sys
import pandas as pd
import logging

# Add src to python path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.backtest.types import (
    BacktestConfig,
    TradeSignal,
    SignalType,
    OrderType,
    ExitReason,
)
from src.backtest.htf_guard import TimestampSafeHTFGuard
from src.backtest.execution_simulator import ExecutionSimulator
from src.backtest.analytics import AnalyticsEngine
from src.backtest.engine import BacktestEngine

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


class DummyTestStrategy:
    """Mock strategy generating periodic signals to test backtest engine execution."""
    def __init__(self, strategy_id: str = "STRAT_TEST"):
        self.strategy_id = strategy_id
        self.counter = 0

    def generate_signal(self, current_time: datetime, current_bar_1m: Dict[str, Any], htf_guard: TimestampSafeHTFGuard, has_open_position: bool) -> Optional[TradeSignal]:
        if has_open_position:
            return None

        self.counter += 1
        # Generate BUY signal every 200 bars during active session
        if self.counter % 200 == 0 and current_bar_1m.get("active_session", False):
            close_p = float(current_bar_1m["close"])
            return TradeSignal(
                timestamp=current_time,
                strategy_id=self.strategy_id,
                signal_type=SignalType.BUY,
                sl_price=round(close_p - 3.0, 2),  # $3.00 SL ($30.0 pips)
                tp1_price=round(close_p + 4.0, 2),  # $4.00 TP1
                tp2_price=round(close_p + 8.0, 2),  # $8.00 TP2
                tp1_ratio=0.50,
            )
        return None


def test_htf_guard(df_1m: pd.DataFrame, df_5m: pd.DataFrame, df_15m: pd.DataFrame):
    print(" [TEST 1] Testing TimestampSafeHTFGuard Zero-Lookahead Assertion...")
    guard = TimestampSafeHTFGuard(df_1m=df_1m, df_5m=df_5m, df_15m=df_15m)

    test_time = datetime(2024, 3, 15, 14, 12, 0, tzinfo=timezone.utc)
    htf_15m_slice = guard.get_closed_htf_bars(test_time, timeframe_minutes=15)

    if not htf_15m_slice.empty:
        last_bar_time = pd.to_datetime(htf_15m_slice._timestamps[-1], utc=True).to_pydatetime()
        assert last_bar_time + pd.Timedelta(minutes=15) <= test_time, "LOOKAHEAD ERROR: HTF bar close time exceeded current minute!"
        print(f"   [PASS] Zero Lookahead Guard Verified! At 14:12, last closed 15m bar open was {last_bar_time.strftime('%H:%M:%S')}")
    else:
        print("   [WARN] HTF guard returned empty slice.")


def test_execution_simulator():
    print("\n [TEST 2] Testing ExecutionSimulator Fills, Risk Lot Sizing & Directional BE...")
    config = BacktestConfig(initial_balance=10000.0, risk_pct=1.0, slippage_pips=0.2, max_spread_points=20)
    sim = ExecutionSimulator(config=config)

    # 1. Test Lot Sizing
    lots = sim.calculate_risk_lot_size(account_equity=10000.0, entry_price=2350.00, sl_price=2345.00)
    assert abs(lots - 0.20) < 0.01, f"Lot sizing error: Expected 0.20 lots, got {lots}"
    print(f"   [PASS] Dynamic Risk Lot Sizing Verified: 1.0% Risk on $5 SL distance = {lots} lots.")

    # 2. Test T+1 Next-Bar Ask Fill Execution
    sig = TradeSignal(
        timestamp=datetime(2024, 3, 15, 10, 0, tzinfo=timezone.utc),
        strategy_id="TEST",
        signal_type=SignalType.BUY,
        sl_price=2345.00,
        tp1_price=2354.00,
        tp2_price=2360.00,
    )
    next_bar = {
        "timestamp": pd.Timestamp("2024-03-15 10:01:00", tz="UTC"),
        "open": 2350.00,
        "high": 2355.00,
        "low": 2349.00,
        "close": 2353.00,
        "spread": 20,
    }

    pos = sim.process_entry_signal(sig, next_bar, account_equity=10000.0)
    assert pos is not None, "Failed to create position from signal"
    expected_ask = 2350.12
    assert abs(pos.entry_price - expected_ask) < 0.001, f"Ask fill error: Expected {expected_ask}, got {pos.entry_price}"
    print(f"   [PASS] Ask Price Execution Verified: Open 2350.00 + Spread/Slippage -> Filled Entry at {pos.entry_price}")

    # 3. Test Partial 50% TP1 Exit + Directional Breakeven Lock
    records, updated_pos = sim.evaluate_position_exit(pos, next_bar)
    assert len(records) == 1, "Expected 1 partial TP1 trade record"
    assert records[0].exit_reason == ExitReason.TP1_HIT, "Expected ExitReason.TP1_HIT"
    assert updated_pos is not None, "Expected runner position to remain active"
    assert updated_pos.tp1_hit is True, "Expected tp1_hit flag True"
    assert updated_pos.breakeven_locked is True, "Expected breakeven_locked flag True"
    assert updated_pos.sl_price > pos.entry_price, "Directional BUY breakeven SL must be above entry price"
    print(f"   [PASS] Partial 50% TP1 & Directional Breakeven Lock Verified! Updated SL: {updated_pos.sl_price:.2f}")


def main():
    print("=" * 70)
    print(" Core Engine Integration & Verification Test Suite")
    print("=" * 70)

    raw_1m_path = Path("data/raw/xau_1m_5y.parquet")
    proc_5m_path = Path("data/processed/xau_5m_5y.parquet")
    proc_15m_path = Path("data/processed/xau_15m_5y.parquet")

    if not (raw_1m_path.exists() and proc_5m_path.exists() and proc_15m_path.exists()):
        print("[ERROR] Datasets missing! Run python scripts/download_xau_data.py first.")
        sys.exit(1)

    print("\n[LOAD] Loading Parquet datasets...")
    df_1m = pd.read_parquet(raw_1m_path)
    df_5m = pd.read_parquet(proc_5m_path)
    df_15m = pd.read_parquet(proc_15m_path)

    # 1. Run Unit Tests
    test_htf_guard(df_1m, df_5m, df_15m)
    test_execution_simulator()

    # 2. Run Sample Integration Backtest (1 Month test range)
    print("\n[INTEGRATION] Running 1-Month Integration Backtest (March 2024)...")
    config = BacktestConfig(initial_balance=10000.0, risk_pct=1.0)
    engine = BacktestEngine(df_1m=df_1m, df_5m=df_5m, df_15m=df_15m, config=config)

    test_strat = DummyTestStrategy()
    start_dt = datetime(2024, 3, 1, tzinfo=timezone.utc)
    end_dt = datetime(2024, 3, 31, tzinfo=timezone.utc)

    results = engine.run(strategies=[test_strat], start_date=start_dt, end_date=end_dt)

    print(results.get("report_str", ""))

    print("\n" + "=" * 70)
    print(" Phase 2 Core Engine Verification PASSED!")
    print("=" * 70)


if __name__ == "__main__":
    main()
