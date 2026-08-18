"""
Abstract Base Strategy Interface.

Defines the standard strategy contract for generating signals and enforcing session filters.
"""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional, Dict, Any

from src.backtest.types import TradeSignal
from src.backtest.htf_guard import TimestampSafeHTFGuard


class BaseStrategy(ABC):
    """Abstract base class for all XAU/USD trading strategies."""

    def __init__(self, strategy_id: str):
        self.strategy_id = strategy_id

    @abstractmethod
    def generate_signal(
        self,
        current_time: datetime,
        current_bar_1m: Dict[str, Any],
        htf_guard: TimestampSafeHTFGuard,
        has_open_position: bool,
    ) -> Optional[TradeSignal]:
        """
        Generates a pure TradeSignal given current market state and HTFGuard.
        Must return None if no valid signal condition is met.
        """
        pass

    def check_session_filter(self, current_bar_1m: Dict[str, Any]) -> bool:
        """Default session filter: active during London, NY, or Overlap sessions."""
        return bool(current_bar_1m.get("active_session", True))
