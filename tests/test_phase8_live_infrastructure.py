#!/usr/bin/env python3
"""
test_phase8_live_infrastructure.py - Phase 8 Infrastructure & Operational Resilience Test Suite

Validates:
1. Trading Session State Machine (TradingSessionManager)
2. Real-Time Market Quality Classifier (MarketQualityFilter)
3. Live Market Data Ingestion & M1 Aggregator (MarketDataAdapter)
4. Real-Time Rolling Feature Extraction (RealtimeFeaturePipeline)
5. Live Decision Engine & Shadow Evaluation (LiveDecisionEngine)
6. Decision Replay Snapshot Engine (DecisionReplayEngine)
7. Active Trade Lifecycle & Trailing Stop Manager (TradeManager)
8. Broker Capability Discovery (MT5Adapter)
9. Granular Trade Lifecycle Timeline (TradeLifecycleTimeline)
10. Periodic Position Reconciliation (PositionReconciler)
11. Telegram Operational Control Bot & Admin Authorization Guard (TelegramControlBot)
12. Pre-Campaign Readiness Gate Audit (run_preflight_readiness_audit)
"""

import os
import json
import pytest
from datetime import datetime, timezone, timedelta

from execution_engine.monitoring.trading_session_manager import TradingSessionManager, TradingSessionState
from execution_engine.monitoring.market_quality_filter import MarketQualityFilter, MarketQualityGrade
from execution_engine.adapters.market_data_adapter import MarketDataAdapter
from execution_engine.adapters.mt5_adapter import MT5Adapter
from research.realtime_feature_pipeline import RealtimeFeaturePipeline
from decision_engine.live_decision_engine import LiveDecisionEngine
from decision_engine.decision_replay import DecisionReplayEngine
from execution_engine.oms.trade_manager import TradeManager
from execution_engine.audit.trade_lifecycle_timeline import TradeLifecycleTimeline
from execution_engine.oms.position_reconciler import PositionReconciler
from execution_engine.notifications.telegram_bot import TelegramControlBot
from scripts.readiness_gate import run_preflight_readiness_audit


def test_trading_session_manager():
    sm = TradingSessionManager(initial_state=TradingSessionState.ACTIVE)
    assert sm.is_trading_allowed() is True

    sm.set_state(TradingSessionState.NEWS_LOCK, reason="CPI Announcement")
    assert sm.is_trading_allowed() is False
    assert sm.current_state == TradingSessionState.NEWS_LOCK

    sm.set_state(TradingSessionState.PAUSED, reason="Operator Manual Pause")
    assert sm.is_trading_allowed() is False

    with pytest.raises(ValueError):
        sm.set_state("INVALID_STATE")


def test_market_quality_filter():
    mq = MarketQualityFilter()

    # Good Quality
    res_good = mq.evaluate_market_quality(current_spread_usd=0.15, ticks_last_minute=40, seconds_since_last_tick=0.2, latency_ms=40.0)
    assert res_good["grade"] == MarketQualityGrade.GOOD
    assert res_good["is_tradable"] is True

    # Fair Quality
    res_fair = mq.evaluate_market_quality(current_spread_usd=0.30, ticks_last_minute=40, seconds_since_last_tick=0.2, latency_ms=40.0)
    assert res_fair["grade"] == MarketQualityGrade.FAIR
    assert res_fair["is_tradable"] is True

    # Untradeable due to stale quote gap
    res_stale = mq.evaluate_market_quality(current_spread_usd=0.15, ticks_last_minute=40, seconds_since_last_tick=10.0, latency_ms=40.0)
    assert res_stale["grade"] == MarketQualityGrade.UNTRADEABLE
    assert res_stale["is_tradable"] is False


def test_market_data_adapter_and_m1_aggregation():
    mda = MarketDataAdapter(symbol="XAUUSD")
    mda.connect()
    tick = mda.get_latest_tick()
    assert "XAUUSD" in tick["symbol"] or "GOLD" in tick["symbol"]
    assert tick["bid"] > 0
    assert tick["ask"] >= tick["bid"]

    candle = mda.update_m1_candle(tick)
    assert mda.current_m1_candle is not None
    assert mda.current_m1_candle["open"] > 0


def test_realtime_feature_pipeline():
    rfp = RealtimeFeaturePipeline()
    m1_candle = {
        "minute_key": "2026-07-27 21:00:00",
        "open": 2350.0,
        "high": 2352.5,
        "low": 2349.0,
        "close": 2351.5,
        "volume": 25
    }
    features = rfp.process_m1_candle(m1_candle, {"spread_usd": 0.18})
    assert "volatility_atr" in features
    assert "momentum_velocity" in features
    assert "compression_ratio" in features
    assert features["spread_usd"] == 0.18


def test_live_decision_engine_and_shadow_mode(tmp_path):
    replay_dir = str(tmp_path / "replay")
    replay = DecisionReplayEngine(replay_dir=replay_dir)

    session_mgr = TradingSessionManager(initial_state=TradingSessionState.ACTIVE)
    mq_filter = MarketQualityFilter()

    lde = LiveDecisionEngine(session_manager=session_mgr, market_quality_filter=mq_filter, replay_engine=replay)

    features = {
        "volatility_atr": 2.2,
        "momentum_velocity": 2.1,
        "compression_ratio": 1.5,
        "spread_usd": 0.15
    }
    tick = {"spread_usd": 0.15, "ticks_last_minute": 50, "seconds_since_last_tick": 0.1}

    res = lde.evaluate_features(features, tick)
    assert res["decision"] == "EXECUTE"
    assert "STRAT-XAU-001" in res["strategy_version"]

    snapshots = replay.load_snapshots()
    assert len(snapshots) == 1
    assert snapshots[0]["decision"] == "EXECUTE"


def test_decision_replay_load_and_replay(tmp_path):
    replay = DecisionReplayEngine(replay_dir=str(tmp_path))
    snap = replay.record_snapshot(
        features={"atr": 1.5},
        behavior_scores={"BEH-001": 0.90},
        portfolio_votes={"conviction": 0.90},
        decision="EXECUTE"
    )
    loaded = replay.load_snapshots()
    assert len(loaded) == 1
    assert loaded[0]["snapshot_id"] == snap["snapshot_id"]


def test_trade_manager_trailing_stop():
    tm = TradeManager(trailing_stop_dist_usd=1.0, break_even_trigger_usd=0.5, enable_trailing_stop=True)

    oms_record = {
        "broker_ticket": 5001,
        "candidate_id": "CAND-TM-1",
        "oms_uuid": "oms-tm-1",
        "direction": "BUY",
        "broker_fill_price": 2350.00,
        "sl": 2345.00,
        "tp": 2360.00
    }
    pos = tm.register_position(oms_record)
    assert pos["status"] == "OPEN"

    # Price moves up +0.60 -> Break-even triggered
    tick1 = {"bid": 2350.60, "ask": 2350.75}

    class DummyAdapter:
        def modify_order(self, ticket, sl, tp):
            return {"success": True}

    updates1 = tm.update_positions_with_market_tick(tick1, DummyAdapter())
    assert len(updates1) == 1
    assert updates1[0]["action"] == "MOVED_TO_BREAK_EVEN"
    assert pos["is_break_even"] is True


def test_broker_capability_discovery(tmp_path):
    adapter = MT5Adapter(config_dir=str(tmp_path))
    profile = adapter.discover_broker_capabilities()
    assert profile["symbol"] == "XAUUSD"
    assert profile["digits"] >= 2
    assert os.path.exists(os.path.join(tmp_path, "broker_profile.json"))


def test_trade_lifecycle_timeline(tmp_path):
    timeline_recorder = TradeLifecycleTimeline(timeline_dir=str(tmp_path))
    timeline_recorder.start_timeline("CAND-TIME-1")
    timeline_recorder.record_stage("CAND-TIME-1", "Decision Approved")
    timeline_recorder.record_stage("CAND-TIME-1", "Filled")

    lines = []
    with open(os.path.join(tmp_path, "trade_timelines.jsonl"), "r") as f:
        for line in f:
            lines.append(json.loads(line))
    assert len(lines) == 1
    assert lines[0]["candidate_id"] == "CAND-TIME-1"
    assert len(lines[0]["stages"]) == 3


def test_position_reconciler_periodic():
    pr = PositionReconciler(check_interval_sec=0.01)
    assert pr.should_check() is True

    class DummyOMS:
        def reconcile_positions(self, pos):
            return {"reconciled": True, "matched_count": 1, "unmatched_broker_tickets": [], "unmatched_oms_uuids": []}

    class DummyBroker:
        def get_positions(self):
            return [{"ticket": 1001}]

    res = pr.reconcile(DummyOMS(), DummyBroker())
    assert res["reconciled"] is True


def test_telegram_control_bot_commands():
    bot = TelegramControlBot(admin_user_id="999")

    # Unauthorized admin command
    res_denied = bot.handle_command("/kill", user_id="123")
    assert "Access Denied" in res_denied

    # Authorized admin command
    res_admin = bot.handle_command("/kill", user_id="999")
    assert "EMERGENCY STOP ACTIVATED" in res_admin
    assert bot.is_paused is True

    # Health command
    res_health = bot.handle_command("/health", user_id="123", context_data={"broker_connected": True})
    assert "System Health Console" in res_health


def test_preflight_readiness_gate():
    report = run_preflight_readiness_audit()
    assert report["all_passed"] is True
    assert report["passed_checks"] == report["total_checks"]
