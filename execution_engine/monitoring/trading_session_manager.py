#!/usr/bin/env python3
"""
trading_session_manager.py - System Trading Session State Machine

Manages execution subsystem state transitions:
PRE_MARKET -> MARKET_OPEN -> ACTIVE -> NEWS_LOCK -> END_OF_DAY -> MAINTENANCE -> PAUSED

All components read the active session state before initiating or accepting trades.
"""

from datetime import datetime, timezone

class TradingSessionState:
    PRE_MARKET = "PRE_MARKET"
    MARKET_OPEN = "MARKET_OPEN"
    ACTIVE = "ACTIVE"
    NEWS_LOCK = "NEWS_LOCK"
    END_OF_DAY = "END_OF_DAY"
    MAINTENANCE = "MAINTENANCE"
    PAUSED = "PAUSED"

class TradingSessionManager:
    """Trading Session Controller managing system execution states."""

    def __init__(self, initial_state: str = TradingSessionState.ACTIVE):
        self.current_state = initial_state
        self.state_history = []
        self.record_transition(initial_state, "Initialization")

    def set_state(self, new_state: str, reason: str = "") -> str:
        """Sets the system session state and records transition."""
        valid_states = [
            TradingSessionState.PRE_MARKET,
            TradingSessionState.MARKET_OPEN,
            TradingSessionState.ACTIVE,
            TradingSessionState.NEWS_LOCK,
            TradingSessionState.END_OF_DAY,
            TradingSessionState.MAINTENANCE,
            TradingSessionState.PAUSED
        ]
        if new_state not in valid_states:
            raise ValueError(f"Invalid trading session state '{new_state}'. Must be one of {valid_states}")

        prev_state = self.current_state
        self.current_state = new_state
        self.record_transition(new_state, f"Transition from {prev_state}: {reason}")
        return self.current_state

    def record_transition(self, state: str, note: str):
        self.state_history.append({
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "state": state,
            "note": note
        })

    def is_trading_allowed(self) -> bool:
        """Returns True only when system session is ACTIVE or MARKET_OPEN."""
        return self.current_state in [TradingSessionState.ACTIVE, TradingSessionState.MARKET_OPEN]

    def get_status(self) -> dict:
        return {
            "current_state": self.current_state,
            "is_trading_allowed": self.is_trading_allowed(),
            "history_length": len(self.state_history)
        }
