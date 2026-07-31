#!/usr/bin/env python3
"""
live_decision_engine.py - Live Decision Intelligence Engine & Shadow Evaluator

Evaluates real-time feature vectors against certified STRAT-XAU-001 behavior ensemble:
- BEH-001: Post-Impulse Pullback Reversal
- BEH-002: Session Breakout Velocity
- BEH-003: Compression Expansion Breakout
- BEH-004: High Volatility Micro Momentum

Evaluates Market Quality & Trading Session state.
Shadow Decision Mode: Tracks both EXECUTE and NO_TRADE candidate counterfactuals.
"""

import uuid
import time
from datetime import datetime, timezone
from decision_engine.decision_replay import DecisionReplayEngine
from execution_engine.monitoring.trading_session_manager import TradingSessionManager
from execution_engine.monitoring.market_quality_filter import MarketQualityFilter
from execution_engine.filters.news_filter import EconomicNewsFilter
from execution_engine.filters.trend_filter import TrendFilter
from execution_engine.filters.fvg_filter import M5FairValueGapFilter
from execution_engine.filters.bos_filter import M5StructureBreakoutFilter

class LiveDecisionEngine:
    """Real-Time Decision Intelligence & Multi-Strategy Ensemble Engine."""

    def __init__(
        self,
        session_manager: TradingSessionManager = None,
        market_quality_filter: MarketQualityFilter = None,
        replay_engine: DecisionReplayEngine = None,
        news_filter: EconomicNewsFilter = None,
        trend_filter: TrendFilter = None,
        fvg_filter: M5FairValueGapFilter = None,
        bos_filter: M5StructureBreakoutFilter = None,
        cooldown_seconds: float = 180.0,
        positions_per_signal: int = 3,
        strategy_mode: str = "STRAT-002"  # "STRAT-001", "STRAT-002", "HYBRID", or "ENSEMBLE"
    ):
        self.session_manager = session_manager or TradingSessionManager()
        self.market_quality_filter = market_quality_filter or MarketQualityFilter()
        self.replay_engine = replay_engine or DecisionReplayEngine()
        self.news_filter = news_filter or EconomicNewsFilter()
        self.trend_filter = trend_filter or TrendFilter()
        self.fvg_filter = fvg_filter or M5FairValueGapFilter()
        self.bos_filter = bos_filter or M5StructureBreakoutFilter()
        self.cooldown_seconds = cooldown_seconds
        self.positions_per_signal = positions_per_signal
        self.strategy_mode = strategy_mode.upper()
        self.last_execution_strat001 = 0.0
        self.last_execution_strat002 = 0.0
        self.last_bar_time_strat001 = 0
        self.last_bar_time_strat002 = 0
        self.shadow_candidates = []

    def evaluate_features(self, feature_vector: dict, current_tick: dict = None) -> dict:
        """
        Evaluates real-time features and returns candidate payload or NO_TRADE decision.
        """
        # 1. Trading Session Check
        if not self.session_manager.is_trading_allowed():
            self.replay_engine.record_snapshot(
                features=feature_vector,
                behavior_scores={},
                portfolio_votes={},
                decision="NO_TRADE",
                market_snapshot={"reason": f"Trading Session State: {self.session_manager.current_state}"}
            )
            return {"decision": "NO_TRADE", "reason": f"Session State {self.session_manager.current_state}"}

        # 2. Market Quality Check
        spread = current_tick.get("spread_usd", feature_vector.get("spread_usd", 0.15)) if current_tick else feature_vector.get("spread_usd", 0.15)
        ticks_min = current_tick.get("ticks_last_minute", 30) if current_tick else 30
        sec_gap = current_tick.get("seconds_since_last_tick", 0.1) if current_tick else 0.1

        quality_eval = self.market_quality_filter.evaluate_market_quality(
            current_spread_usd=spread,
            ticks_last_minute=ticks_min,
            seconds_since_last_tick=sec_gap
        )

        if not quality_eval["is_tradable"]:
            self.replay_engine.record_snapshot(
                features=feature_vector,
                behavior_scores={},
                portfolio_votes={},
                decision="NO_TRADE",
                market_snapshot=quality_eval
            )
            return {"decision": "NO_TRADE", "reason": f"Market Quality Grade: {quality_eval['grade']}"}

        news_blocked, news_reason = self.news_filter.is_news_blocked()
        if news_blocked:
            self.replay_engine.record_snapshot(
                features=feature_vector,
                behavior_scores={"BEH-NEWS": 0.0},
                portfolio_votes={"veto": True},
                decision="NO_TRADE",
                market_snapshot={"reason": news_reason}
            )
            return {"decision": "NO_TRADE", "reason": news_reason}

        now_ts = time.time()
        ask_p = float(current_tick["ask"]) if (current_tick and "ask" in current_tick) else float(feature_vector.get("ask", 0.0))
        bid_p = float(current_tick["bid"]) if (current_tick and "bid" in current_tick) else float(feature_vector.get("bid", 0.0))

        # Check STRAT-002 (M5 CHOCH / BOS Breakout)
        if self.strategy_mode in ["STRAT-002", "ENSEMBLE"]:
            bos_status = self.bos_filter.check_structure_breakout()
            bar_t = bos_status.get("bar_time", 0)
            if bos_status["active"] and (bar_t == 0 or bar_t > self.last_bar_time_strat002):
                if self.cooldown_seconds == 0 or (now_ts - self.last_execution_strat002) >= self.cooldown_seconds:
                    direction = bos_status["bos_type"]
                    entry_p = ask_p if direction == "BUY" else bid_p
                    sl_price = round(entry_p - 1.50, 2) if direction == "BUY" else round(entry_p + 1.50, 2)
                    tp_price = round(entry_p + 2.25, 2) if direction == "BUY" else round(entry_p - 2.25, 2)

                    cand_id = f"CAND-LIVE-{uuid.uuid4().hex[:8]}"
                    exec_uuid = uuid.uuid4().hex
                    self.last_execution_strat002 = now_ts
                    if bar_t > 0:
                        self.last_bar_time_strat002 = bar_t

                    candidate_payload = {
                        "decision": "EXECUTE",
                        "candidate_id": cand_id,
                        "execution_uuid": exec_uuid,
                        "strategy_version": "STRAT-XAU-BOS-BURST",
                        "direction": direction,
                        "volume_lots": 0.1,
                        "positions_per_signal": self.positions_per_signal,
                        "breakout_price": bos_status["breakout_price"],
                        "risk_tier": "TIER_1",
                        "spread_usd": spread,
                        "entry_target": entry_p,
                        "sl": sl_price,
                        "tp": tp_price,
                        "created_at_utc": datetime.now(timezone.utc).isoformat()
                    }

                    self.replay_engine.record_snapshot(
                        features=feature_vector,
                        behavior_scores={"CHOCH_BOS": 0.98},
                        portfolio_votes={"bos_type": direction},
                        decision="EXECUTE",
                        candidate_snapshot=candidate_payload,
                        market_snapshot={"spread": spread}
                    )
                    return candidate_payload

        # Check STRAT-001 (M5 Fair Value Gap Imbalance)
        if self.strategy_mode in ["STRAT-001", "ENSEMBLE"]:
            fvg_status = self.fvg_filter.check_fvg_status()
            bar_t = fvg_status.get("bar_time", 0)
            if fvg_status["is_fvg_active"] and (bar_t == 0 or bar_t > self.last_bar_time_strat001):
                if self.cooldown_seconds == 0 or (now_ts - self.last_execution_strat001) >= self.cooldown_seconds:
                    direction = fvg_status["fvg_type"]
                    entry_p = ask_p if direction == "BUY" else bid_p
                    sl_price = round(entry_p - 1.50, 2) if direction == "BUY" else round(entry_p + 1.50, 2)
                    tp_price = round(entry_p + 2.25, 2) if direction == "BUY" else round(entry_p - 2.25, 2)

                    cand_id = f"CAND-LIVE-{uuid.uuid4().hex[:8]}"
                    exec_uuid = uuid.uuid4().hex
                    self.last_execution_strat001 = now_ts
                    if bar_t > 0:
                        self.last_bar_time_strat001 = bar_t

                    candidate_payload = {
                        "decision": "EXECUTE",
                        "candidate_id": cand_id,
                        "execution_uuid": exec_uuid,
                        "strategy_version": "STRAT-XAU-FVG-BURST",
                        "direction": direction,
                        "volume_lots": 0.1,
                        "positions_per_signal": self.positions_per_signal,
                        "fvg_gap_size": fvg_status["fvg_gap_size"],
                        "risk_tier": "TIER_1",
                        "spread_usd": spread,
                        "entry_target": entry_p,
                        "sl": sl_price,
                        "tp": tp_price,
                        "created_at_utc": datetime.now(timezone.utc).isoformat()
                    }

                    self.replay_engine.record_snapshot(
                        features=feature_vector,
                        behavior_scores={"FVG_IMBALANCE": 0.95},
                        portfolio_votes={"fvg_gap": fvg_status["fvg_gap_size"]},
                        decision="EXECUTE",
                        candidate_snapshot=candidate_payload,
                        market_snapshot=quality_eval
                    )
                    return candidate_payload

        return {"decision": "NO_TRADE", "reason": "No active strategy signal at this tick"}
