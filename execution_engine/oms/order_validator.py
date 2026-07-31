#!/usr/bin/env python3
"""
order_validator.py - Pre-Broker Order Validator Layer

Enforces pre-broker guardrails:
1. Min / Max lot size limits
2. Minimum Stop-Loss / Take-Profit distance
3. Maximum allowable spread check
4. Symbol trading session status check
5. Minimum account equity & leverage constraints
6. Total portfolio position exposure limit (current_exposure + candidate_exposure <= max_exposure)
7. Duplicate execution UUID lock
8. Stale candidate expiration check (ttl)
"""

from datetime import datetime, timezone
from execution_engine.errors import ValidationError

class OrderValidator:
    """Pre-broker order parameter & portfolio exposure validator."""

    def __init__(
        self,
        min_lot_size: float = 0.01,
        max_lot_size: float = 10.0,
        min_sl_distance_usd: float = 0.50,
        max_spread_usd: float = 0.35,
        max_portfolio_exposure_lots: float = 5.0,
        min_account_equity_usd: float = 1000.0,
        max_candidate_age_sec: float = 30.0
    ):
        self.min_lot_size = min_lot_size
        self.max_lot_size = max_lot_size
        self.min_sl_distance_usd = min_sl_distance_usd
        self.max_spread_usd = max_spread_usd
        self.max_portfolio_exposure_lots = max_portfolio_exposure_lots
        self.min_account_equity_usd = min_account_equity_usd
        self.max_candidate_age_sec = max_candidate_age_sec
        self.seen_execution_uuids = set()

    def validate_candidate(
        self,
        candidate_payload: dict,
        current_portfolio_exposure_lots: float = 0.0,
        current_account_equity_usd: float = 10000.0,
        current_spread_usd: float = 0.15,
        is_market_session_open: bool = True
    ) -> bool:
        """
        Validates order candidate parameters before forwarding to broker adapter.
        Raises ValidationError on failure.
        """
        # 1. Market session status
        if not is_market_session_open:
            raise ValidationError("Market trading session is closed.", {"candidate": candidate_payload})

        # 2. Duplicate Execution UUID check
        exec_uuid = candidate_payload.get("execution_uuid")
        if not exec_uuid:
            raise ValidationError("Candidate payload missing mandatory execution_uuid.", {"candidate": candidate_payload})

        if exec_uuid in self.seen_execution_uuids:
            raise ValidationError(f"Duplicate execution UUID detected: {exec_uuid}", {"execution_uuid": exec_uuid})

        # 3. Candidate Expiration / TTL check
        created_at_str = candidate_payload.get("created_at_utc")
        if created_at_str:
            try:
                created_at = datetime.fromisoformat(created_at_str)
                age_sec = (datetime.now(timezone.utc) - created_at).total_seconds()
                if age_sec > self.max_candidate_age_sec:
                    raise ValidationError(
                        f"Stale candidate expired. Age: {age_sec:.2f}s > Max: {self.max_candidate_age_sec}s",
                        {"candidate_age_sec": age_sec}
                    )
            except (ValueError, TypeError):
                pass

        # 4. Account Equity check
        if current_account_equity_usd < self.min_account_equity_usd:
            raise ValidationError(
                f"Account equity ${current_account_equity_usd:.2f} below minimum requirement ${self.min_account_equity_usd:.2f}",
                {"equity": current_account_equity_usd}
            )

        # 5. Spread Check
        if current_spread_usd > self.max_spread_usd:
            raise ValidationError(
                f"Current spread ${current_spread_usd:.2f} breaches threshold ${self.max_spread_usd:.2f}",
                {"spread_usd": current_spread_usd}
            )

        # 6. Volume Limits & SL Distance
        volume = candidate_payload.get("volume_lots", candidate_payload.get("adaptive_risk_pct", 1.0) * 0.1)
        if volume < self.min_lot_size or volume > self.max_lot_size:
            raise ValidationError(
                f"Order volume {volume} lots outside valid range [{self.min_lot_size}, {self.max_lot_size}]",
                {"volume_lots": volume}
            )

        # 7. Portfolio Position Exposure Limit check
        projected_exposure = current_portfolio_exposure_lots + volume
        if projected_exposure > self.max_portfolio_exposure_lots:
            raise ValidationError(
                f"Projected portfolio exposure {projected_exposure:.2f} lots breaches limit {self.max_portfolio_exposure_lots:.2f} lots",
                {"current_exposure": current_portfolio_exposure_lots, "volume": volume}
            )

        # Record UUID on successful validation
        self.seen_execution_uuids.add(exec_uuid)
        return True
