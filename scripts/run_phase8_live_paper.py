#!/usr/bin/env python3
"""
run_phase8_live_paper.py - Phase 8 Master Paper Trading Orchestration Runner

Initializes & Orchestrates:
- Category Loggers
- Trading Session Manager
- Market Data Adapter (Live Ticks & M1 Aggregator)
- Real-Time Feature Extraction Pipeline
- Live Decision Engine & Shadow Evaluator
- OMS Engine (Optimistic Locking, Pre-Broker Validator, Event Store, DLQ, Audit Journal)
- Active Trade Manager (Trailing Stop / Break-even)
- Position Reconciler
- Heartbeat & Clock Sync Monitor
- Telegram Control Console
"""

import sys
import os
import time
from datetime import datetime, timezone

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from execution_engine.logging_config import setup_category_loggers
from execution_engine.monitoring.trading_session_manager import TradingSessionManager, TradingSessionState
from execution_engine.monitoring.market_quality_filter import MarketQualityFilter
from execution_engine.adapters.market_data_adapter import MarketDataAdapter
from execution_engine.adapters.mt5_adapter import MT5Adapter
from research.realtime_feature_pipeline import RealtimeFeaturePipeline
from decision_engine.live_decision_engine import LiveDecisionEngine
from decision_engine.decision_replay import DecisionReplayEngine
from execution_engine.oms.oms import OrderManagementSystem
from execution_engine.oms.trade_manager import TradeManager
from execution_engine.oms.position_reconciler import PositionReconciler
from execution_engine.monitoring.clock_sync import ClockSyncMonitor
from execution_engine.heartbeat.heartbeat import HeartbeatMonitor
from execution_engine.notifications.telegram_bot import TelegramControlBot
from execution_engine.metrics.telemetry import calculate_execution_telemetry
from execution_engine.filters.news_filter import EconomicNewsFilter
from execution_engine.filters.trend_filter import TrendFilter
from execution_engine.filters.fvg_filter import M5FairValueGapFilter


def run_phase8_paper_trading(num_iterations: int = 5):
    """
    Executes Phase 8 paper trading orchestration run.
    """
    print("=" * 70)
    print("  PHASE 8 — LIVE INFRASTRUCTURE & PAPER TRADING ENGINE INITIALIZING  ")
    print("=" * 70)

    # 1. Setup Category Loggers
    loggers = setup_category_loggers()
    market_log = loggers["market_data"]
    decision_log = loggers["decision"]
    execution_log = loggers["execution"]
    broker_log = loggers["broker"]

    # 2. Initialize Subsystems
    session_mgr = TradingSessionManager(initial_state=TradingSessionState.ACTIVE)
    mq_filter = MarketQualityFilter()
    mkt_data = MarketDataAdapter(symbol="XAUUSD")
    mkt_data.connect()

    broker_adapter = MT5Adapter(symbol="XAUUSD")
    broker_adapter.connect()

    feature_pipeline = RealtimeFeaturePipeline()
    replay_engine = DecisionReplayEngine()
    news_filter = EconomicNewsFilter()
    trend_filter = TrendFilter(symbol=broker_adapter.symbol)
    fvg_filter = M5FairValueGapFilter(symbol=broker_adapter.symbol)

    decision_engine = LiveDecisionEngine(
        session_manager=session_mgr,
        market_quality_filter=mq_filter,
        replay_engine=replay_engine,
        news_filter=news_filter,
        trend_filter=trend_filter,
        fvg_filter=fvg_filter,
        cooldown_seconds=300.0,
        positions_per_signal=3
    )

    oms = OrderManagementSystem()
    trade_manager = TradeManager(enable_trailing_stop=False)
    position_reconciler = PositionReconciler()
    clock_sync = ClockSyncMonitor()
    heartbeat = HeartbeatMonitor()
    telegram_bot = TelegramControlBot()

    telegram_bot.send_notification("System Initialization", "Phase 8 Paper Trading Engine Online. Listening for live market ticks.")
    print(f"[SYSTEM] Engine Online. Session State: {session_mgr.current_state}")

    # 3. Execution Loop
    completed_candidates = []
    try:
        for i in range(num_iterations):
            tick = mkt_data.get_latest_tick()
            market_log.info(f"Tick #{i+1}: Bid ${tick['bid']} | Ask ${tick['ask']} | Spread ${tick['spread_usd']}")

            # Update M1 candle
            m1_candle = mkt_data.update_m1_candle(tick)
            if m1_candle is None:
                m1_candle = {
                    "minute_key": tick["timestamp_utc"],
                    "open": tick["bid"],
                    "high": tick["ask"] + 0.50,
                    "low": tick["bid"] - 0.50,
                    "close": tick["bid"] + 0.20,
                    "volume": 15,
                    "completed": True
                }

            features = feature_pipeline.process_m1_candle(m1_candle, tick)
            decision_log.info(f"Features Computed: Volatility ATR={features['volatility_atr']}, Momentum={features['momentum_velocity']}")

            # Evaluate decision
            decision_res = decision_engine.evaluate_features(features, tick)
            if decision_res.get("decision") == "EXECUTE":
                burst_count = decision_res.get("positions_per_signal", 3)
                decision_log.info(f"Signal Approved: {decision_res['candidate_id']} ({decision_res['direction']}) -> Executing {burst_count} Burst Positions")
                telegram_bot.send_notification("Signal Approved", f"🟢 Candidate {decision_res['candidate_id']} ({decision_res['direction']}) Burst: {burst_count} Positions | Gap: ${decision_res.get('fvg_gap_size', 0.0):.2f}")

                # Model 1 Instant 3-Burst Order Execution
                for b_idx in range(burst_count):
                    pos_payload = dict(decision_res)
                    pos_payload["candidate_id"] = f"{decision_res['candidate_id']}-B{b_idx+1}"
                    pos_payload["execution_uuid"] = f"{decision_res['execution_uuid']}-B{b_idx+1}"
                    oms_record = oms.process_candidate(pos_payload, broker_adapter)
                    execution_log.info(f"OMS Burst #{b_idx+1}: {oms_record.get('oms_state', 'FILLED')} | Ticket #{oms_record.get('broker_ticket', 0)}")

                    if oms_record.get("oms_state") == "FILLED" or oms_record.get("status") == "FILLED":
                        trade_manager.register_position(oms_record)
                        completed_candidates.append(oms_record)

            # Update position management
            updates = trade_manager.update_positions_with_market_tick(tick, broker_adapter)
            for u in updates:
                execution_log.info(f"Trade Management Action: Ticket #{u['ticket']} -> {u['action']} (SL: {u['new_sl']})")

            # Periodic position reconciliation
            if position_reconciler.should_check():
                recon_res = position_reconciler.reconcile(oms, broker_adapter)
                broker_log.info(f"Reconciliation Status: Reconciled={recon_res.get('reconciled', True)} (Matched: {recon_res.get('matched_count', 0)})")

            # Poll Telegram slash commands & respond to user
            bot_context = {
                "broker_connected": broker_adapter.connected,
                "session_state": session_mgr.current_state,
                "spread_usd": tick["spread_usd"],
                "heartbeat_gen": heartbeat.generation,
                "bid": tick["bid"],
                "ask": tick["ask"]
            }
            telegram_bot.poll_updates_and_respond(bot_context)

            # Heartbeat & Clock Sync
            hb_res = heartbeat.record_heartbeat(latency_ms=45.0)
            clock_res = clock_sync.evaluate_clock_drift(datetime.now(timezone.utc))

            time.sleep(0.05)

    except KeyboardInterrupt:
        print("\n[SYSTEM] Paper Trading Engine Shut Down Gracefully by User.")

    # 4. Final Telemetry Summary
    telemetry = calculate_execution_telemetry(completed_candidates, environment="SIMULATION")
    print("\n" + "=" * 70)
    print("  PHASE 8 PAPER TRADING RUN COMPLETE  ")
    print(f"Total Candidate Orders Processed: {len(completed_candidates)}")
    print(f"Fill Rate: {telemetry['fill_rate_pct']}% | Environment: {telemetry['environment']}")
    print("=" * 70)
    return telemetry


if __name__ == "__main__":
    is_continuous = "--continuous" in sys.argv or "-c" in sys.argv
    if is_continuous:
        print("[INFO] Starting Continuous Live Paper Trading Mode (Press Ctrl+C to stop)...")
        run_phase8_paper_trading(num_iterations=999999999)
    else:
        run_phase8_paper_trading(num_iterations=10)
