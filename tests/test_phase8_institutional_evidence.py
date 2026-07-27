#!/usr/bin/env python3
"""
test_phase8_institutional_evidence.py - Institutional Evidence & Trade Intelligence Test Suite

Validates:
1. Market Regime Database (MarketRegimeDatabase)
2. Decision Quality & EV Variance Analyzer (DecisionQualityAnalyzer)
3. NO_TRADE Missed Opportunity Tracker (MissedOpportunityTracker)
4. Confidence Calibration ECE Drift Monitor (CalibrationDriftMonitor)
5. Micro-Session Attribution Engine (SessionAttributionEngine)
6. Trade Duration Analytics (TradeDurationAnalytics)
7. Infrastructure Reliability Scorer (InfrastructureReliabilityScorer)
8. Version Lineage Reproducibility Manager (VersionLineageManager)
9. Trade Chart Snapshot Generator (TradeChartGenerator)
10. Multi-Condition Behavior Drift Detector (BehaviorDriftDetector)
11. Parallel Shadow Strategy Evaluator (ShadowStrategyEvaluator)
12. Broker Quality Analytics Engine (BrokerQualityAnalytics)
13. Institutional Trade Journal Database (TradeJournalDatabase)
14. Daily & Weekly Report Generators (DailyReportGenerator, WeeklyReviewGenerator)
15. 6 Sequential Promotion Gates & Campaign Completion Evaluator (SequentialPromotionGates, CampaignEvaluator)
"""

import os
import json
import pytest
from datetime import datetime, timezone

from execution_engine.audit.regime_database import MarketRegimeDatabase
from decision_engine.decision_quality_analyzer import DecisionQualityAnalyzer
from decision_engine.missed_opportunity_tracker import MissedOpportunityTracker
from robustness.calibration_drift_monitor import CalibrationDriftMonitor
from research.session_attribution import SessionAttributionEngine
from execution_engine.metrics.trade_duration_analytics import TradeDurationAnalytics
from execution_engine.metrics.infrastructure_reliability_scorer import InfrastructureReliabilityScorer
from execution_engine.audit.version_lineage import VersionLineageManager
from execution_engine.audit.chart_generator import TradeChartGenerator
from robustness.behavior_drift_detector import BehaviorDriftDetector
from decision_engine.shadow_strategy_evaluator import ShadowStrategyEvaluator
from execution_engine.metrics.broker_quality_analytics import BrokerQualityAnalytics
from execution_engine.audit.trade_journal_db import TradeJournalDatabase
from reports.daily_report_generator import DailyReportGenerator
from reports.weekly_review_generator import WeeklyReviewGenerator
from robustness.sequential_promotion_gates import SequentialPromotionGates
from scripts.campaign_evaluator import CampaignEvaluator


def test_market_regime_database(tmp_path):
    r_db = MarketRegimeDatabase(regime_dir=str(tmp_path))
    entry = r_db.record_regime_transition("TREND_UP", {"atr": 2.1})
    assert entry["regime"] == "TREND_UP"
    assert r_db.get_current_regime() == "TREND_UP"


def test_decision_quality_analyzer():
    # Nominal Alignment
    res1 = DecisionQualityAnalyzer.analyze_trade_decision_quality(expected_ev_usd=0.40, actual_pnl_usd=0.42)
    assert res1["attribution"] == "NOMINAL_ALIGNMENT"

    # Execution Slippage
    res2 = DecisionQualityAnalyzer.analyze_trade_decision_quality(expected_ev_usd=0.40, actual_pnl_usd=-0.10, slippage_usd=0.18)
    assert res2["attribution"] == "EXECUTION_SLIPPAGE"


def test_missed_opportunity_tracker():
    tracker = MissedOpportunityTracker()
    tracker.record_no_trade({"candidate_id": "CAND-NO-1", "direction": "BUY"}, entry_price=2350.0, target_tp=2352.0, target_sl=2348.0)

    # Price moves to TP
    outcomes = tracker.update_outcomes(2352.5)
    assert len(outcomes) == 1
    assert outcomes[0]["outcome"] == "WOULD_HAVE_HIT_TP"
    assert outcomes[0]["counterfactual_pnl_usd"] == 2.0


def test_calibration_drift_monitor():
    cdm = CalibrationDriftMonitor(baseline_ece=0.042)
    confs = [0.8, 0.8, 0.8, 0.8, 0.8]
    outcomes = [1, 1, 1, 1, 0]

    res = cdm.evaluate_drift(confs, outcomes)
    assert "current_ece" in res
    assert res["is_valid"] is True


def test_session_attribution_engine():
    sess_london = SessionAttributionEngine.classify_micro_session("2026-07-27T08:30:00+00:00")
    assert sess_london == "London Open"

    sess_ny = SessionAttributionEngine.classify_micro_session("2026-07-27T14:30:00+00:00")
    assert sess_ny == "NY Open"


def test_trade_duration_analytics():
    records = [
        {"pnl_usd": 10.0, "duration_min": 4.0},
        {"pnl_usd": 15.0, "duration_min": 6.0},
        {"pnl_usd": -5.0, "duration_min": 12.0}
    ]
    res = TradeDurationAnalytics.calculate_duration_metrics(records)
    assert res["median_hold_min"] == 6.0
    assert res["winning_hold_min"] == 5.0
    assert res["losing_hold_min"] == 12.0


def test_infrastructure_reliability_scorer():
    res = InfrastructureReliabilityScorer.calculate_reliability_score(
        total_active_seconds=86400.0,
        downtime_seconds=0.0,
        expected_ticks=100000,
        received_ticks=100000,
        reconnect_count=0
    )
    assert res["reliability_score"] == 100.0
    assert res["is_healthy"] is True


def test_version_lineage_manager():
    trade = {"trade_id": "TR-101"}
    versioned = VersionLineageManager.attach_version_lineage(trade)
    assert "version_lineage" in versioned
    assert versioned["version_lineage"]["strategy_version"] == "STRAT-XAU-001"


def test_trade_chart_generator(tmp_path):
    cg = TradeChartGenerator(charts_dir=str(tmp_path))
    chart_file = cg.generate_entry_chart("TR-202", [2350.0, 2351.0, 2352.0], entry_price=2351.0)
    assert os.path.exists(chart_file)


def test_behavior_drift_detector():
    bdd = BehaviorDriftDetector(min_sample_trades=5, baseline_expectancy=0.40)
    # Add 5 winning trades
    for _ in range(5):
        bdd.record_behavior_trade("BEH-001", 10.0)

    eval_res = bdd.evaluate_behavior_health("BEH-001")
    assert eval_res["status"] == "HEALTHY"
    assert eval_res["is_drifted"] is False


def test_shadow_strategy_evaluator():
    sse = ShadowStrategyEvaluator()
    feats = {"momentum_velocity": 2.5, "volatility_atr": 2.0}
    live_dec = {"decision": "EXECUTE"}

    res = sse.evaluate_shadow_candidate(feats, live_dec)
    assert res["shadow_decision"] == "EXECUTE"
    assert res["in_agreement"] is True


def test_broker_quality_analytics():
    records = [{"execution_latency_ms": 75.0, "slippage_usd": 0.02, "retcode": 10009}]
    res = BrokerQualityAnalytics.evaluate_broker_quality(records)
    assert res["broker_quality_grade"] == "EXCELLENT"


def test_trade_journal_database(tmp_path):
    tj_db = TradeJournalDatabase(db_dir=str(tmp_path))
    trade = {"trade_id": "TR-J1", "actual_pnl_usd": 25.0}
    rec = tj_db.record_journal_trade(trade)
    assert rec["trade_id"] == "TR-J1"

    all_trades = tj_db.fetch_all_trades()
    assert len(all_trades) == 1
    assert all_trades[0]["trade_id"] == "TR-J1"


def test_daily_and_weekly_reports(tmp_path):
    drg = DailyReportGenerator(output_dir=str(tmp_path))
    d_file = drg.generate_daily_report("2026-08-01")
    assert os.path.exists(d_file)

    wrg = WeeklyReviewGenerator(output_dir=str(tmp_path))
    w_file = wrg.generate_weekly_report("Week_01")
    assert os.path.exists(w_file)


def test_sequential_promotion_gates_and_campaign_evaluator(tmp_path):
    metrics = {
        "uptime_pct": 99.98,
        "engine_crashes": 0,
        "fill_rate_pct": 100.0,
        "avg_slippage_usd": 0.02,
        "net_expectancy_usd": 0.40,
        "profit_factor": 1.58,
        "max_drawdown_pct": 3.9,
        "risk_breaches": 0,
        "drifted_behaviors_count": 0,
        "requotes_count": 0
    }
    res = SequentialPromotionGates.evaluate_campaign_gates(metrics)
    assert res["all_passed"] is True
    assert "CERTIFIED APPROVED" in res["promotion_status"]

    ce = CampaignEvaluator(reports_dir=str(tmp_path))
    history = [{"actual_pnl_usd": 15.0} for _ in range(300)]
    c_res = ce.evaluate_campaign_progress(history)
    assert c_res["total_trades"] == 300
    assert os.path.exists(os.path.join(tmp_path, "campaign_300_trades_report.md"))
