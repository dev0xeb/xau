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
from datetime import datetime, timezone
from decision_engine.decision_replay import DecisionReplayEngine
from execution_engine.monitoring.trading_session_manager import TradingSessionManager
from execution_engine.monitoring.market_quality_filter import MarketQualityFilter

class LiveDecisionEngine:
    """Real-Time Decision Intelligence & Shadow Mode Engine."""

    def __init__(
        self,
        session_manager: TradingSessionManager = None,
        market_quality_filter: MarketQualityFilter = None,
        replay_engine: DecisionReplayEngine = None
    ):
        self.session_manager = session_manager or TradingSessionManager()
        self.market_quality_filter = market_quality_filter or MarketQualityFilter()
        self.replay_engine = replay_engine or DecisionReplayEngine()
        self.shadow_candidates = []

    def evaluate_features(self, feature_vector: dict, current_tick: dict = None) -> dict:
        """
        Evaluates real-time feature vector and returns candidate payload or NO_TRADE decision.
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

        # 3. Behavior Scoring Logic (STRAT-XAU-001 Ensemble)
        vol_atr = feature_vector.get("volatility_atr", 1.5)
        mom_vel = feature_vector.get("momentum_velocity", 0.0)
        comp_ratio = feature_vector.get("compression_ratio", 1.0)

        scores = {
            "BEH-001": 0.85 if abs(mom_vel) > 1.2 and comp_ratio > 1.2 else 0.20,
            "BEH-002": 0.90 if abs(mom_vel) > 1.8 else 0.15,
            "BEH-003": 0.88 if comp_ratio < 0.8 and abs(mom_vel) > 0.8 else 0.10,
            "BEH-004": 0.92 if vol_atr > 2.0 and abs(mom_vel) > 1.0 else 0.25
        }

        active_behaviors = [b_id for b_id, score in scores.items() if score >= 0.75]
        mean_conviction = sum(scores.values()) / float(len(scores))

        # 4. Decision Threshold
        if active_behaviors and mean_conviction >= 0.50:
            direction = "BUY" if mom_vel > 0 else "SELL"
            cand_id = f"CAND-LIVE-{uuid.uuid4().hex[:8]}"
            exec_uuid = uuid.uuid4().hex

            # Extract real-time tick prices dynamically (no hardcoded price fallbacks)
            ask_p = float(current_tick["ask"]) if (current_tick and "ask" in current_tick) else float(feature_vector.get("ask", 0.0))
            bid_p = float(current_tick["bid"]) if (current_tick and "bid" in current_tick) else float(feature_vector.get("bid", 0.0))
            entry_p = ask_p if direction == "BUY" else bid_p

            # Certified Research Excursion Targets (STRAT-XAU-001): MAE = $2.00/oz (20 pts SL), MFE = $5.00/oz (50 pts TP)
            sl_dist = 2.00
            tp_dist = 5.00

            sl_price = round(entry_p - sl_dist, 2) if direction == "BUY" else round(entry_p + sl_dist, 2)
            tp_price = round(entry_p + tp_dist, 2) if direction == "BUY" else round(entry_p - tp_dist, 2)

            candidate_payload = {
                "decision": "EXECUTE",
                "candidate_id": cand_id,
                "execution_uuid": exec_uuid,
                "strategy_version": "STRAT-XAU-001",
                "behavior_ids": active_behaviors,
                "direction": direction,
                "volume_lots": 0.1,
                "decision_score": round(mean_conviction, 2),
                "risk_tier": "TIER_1",
                "spread_usd": spread,
                "volatility_atr": vol_atr,
                "entry_target": entry_p,
                "sl": sl_price,
                "tp": tp_price,
                "created_at_utc": datetime.now(timezone.utc).isoformat()
            }

            self.replay_engine.record_snapshot(
                features=feature_vector,
                behavior_scores=scores,
                portfolio_votes={"conviction": mean_conviction, "active_count": len(active_behaviors)},
                decision="EXECUTE",
                candidate_snapshot=candidate_payload,
                market_snapshot=quality_eval
            )
            return candidate_payload

        # Shadow Mode: NO_TRADE counterfactual candidate logging
        shadow_record = {
            "decision": "NO_TRADE",
            "reason": "Conviction threshold not met",
            "mean_conviction": round(mean_conviction, 2),
            "feature_snapshot": feature_vector
        }
        self.shadow_candidates.append(shadow_record)

        self.replay_engine.record_snapshot(
            features=feature_vector,
            behavior_scores=scores,
            portfolio_votes={"conviction": mean_conviction, "active_count": len(active_behaviors)},
            decision="NO_TRADE",
            market_snapshot=quality_eval
        )
        return shadow_record
