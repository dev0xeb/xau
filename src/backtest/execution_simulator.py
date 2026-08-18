"""
Decoupled Order Execution Simulator Engine.

Handles T+1 Next-Bar Open entries, Bid/Ask price fills, dynamic risk position sizing,
direction-specific Breakeven locks, partial profit exits, and tick-level conflict resolution.
Dict record fast access.
"""

from datetime import datetime
import math
import uuid
from typing import List, Tuple, Optional, Dict, Any
import pandas as pd

from src.backtest.types import (
    TradeSignal,
    Position,
    TradeRecord,
    BacktestConfig,
    SignalType,
    OrderType,
    ExitReason,
)


class ExecutionSimulator:
    """Independent execution fill simulator completely decoupled from strategy logic."""

    def __init__(self, config: Optional[BacktestConfig] = None):
        self.config = config or BacktestConfig()

    def calculate_risk_lot_size(
        self, account_equity: float, entry_price: float, sl_price: float
    ) -> float:
        """Calculates dynamic lot size based on Equity Risk % and structural SL distance."""
        sl_distance = abs(entry_price - sl_price)
        if sl_distance <= 0:
            return self.config.min_lot

        risk_amount = account_equity * (self.config.risk_pct / 100.0)
        loss_per_lot = sl_distance * self.config.contract_size

        if loss_per_lot <= 0:
            return self.config.min_lot

        raw_lots = risk_amount / loss_per_lot
        stepped_lots = math.floor(raw_lots / self.config.lot_step) * self.config.lot_step
        clamped_lots = max(self.config.min_lot, min(self.config.max_lot, stepped_lots))
        return round(clamped_lots, 2)

    def process_entry_signal(
        self, signal: TradeSignal, next_bar_1m: Dict[str, Any], account_equity: float
    ) -> Optional[Position]:
        """
        Executes a TradeSignal at T+1 Next Bar Open using Bid/Ask spread pricing.
        
        Buy Fills at Ask Price = Open + Spread + Slippage
        Sell Fills at Bid Price = Open - Slippage
        """
        bar_open = float(next_bar_1m["open"])
        bar_spread_points = float(next_bar_1m.get("spread", self.config.max_spread_points))
        spread_price_offset = (bar_spread_points * self.config.point_value) / 2.0
        slippage_offset = self.config.slippage_pips * 0.10

        if bar_spread_points > self.config.max_spread_points:
            return None

        bar_time = pd.to_datetime(next_bar_1m["timestamp"]).to_pydatetime()

        if signal.signal_type == SignalType.BUY:
            filled_entry_price = bar_open + spread_price_offset + slippage_offset
            if signal.sl_price >= filled_entry_price:
                return None
        else:
            filled_entry_price = bar_open - spread_price_offset - slippage_offset
            if signal.sl_price <= filled_entry_price:
                return None

        lots = self.calculate_risk_lot_size(
            account_equity=account_equity,
            entry_price=filled_entry_price,
            sl_price=signal.sl_price,
        )

        pos_id = f"pos_{uuid.uuid4().hex[:8]}"

        return Position(
            position_id=pos_id,
            strategy_id=signal.strategy_id,
            signal_type=signal.signal_type,
            entry_time=bar_time,
            entry_price=filled_entry_price,
            original_lots=lots,
            current_lots=lots,
            sl_price=signal.sl_price,
            tp1_price=signal.tp1_price,
            tp2_price=signal.tp2_price,
            tp1_ratio=signal.tp1_ratio,
            tp1_hit=False,
            breakeven_locked=False,
            initial_risk_amount=account_equity * (self.config.risk_pct / 100.0),
            metadata=signal.metadata.copy(),
        )

    def evaluate_position_exit(
        self,
        position: Position,
        bar_1m: Dict[str, Any],
        tick_data: Optional[pd.DataFrame] = None,
    ) -> Tuple[List[TradeRecord], Optional[Position]]:
        """
        Evaluates active position against current 1m bar for SL, TP1, Breakeven, and TP2.
        """
        records: List[TradeRecord] = []
        bar_high = float(bar_1m["high"])
        bar_low = float(bar_1m["low"])
        bar_spread_points = float(bar_1m.get("spread", 15))
        spread_price_offset = (bar_spread_points * self.config.point_value) / 2.0
        slippage_offset = self.config.slippage_pips * 0.10
        bar_time = pd.to_datetime(bar_1m["timestamp"]).to_pydatetime()

        session_name = "OVERLAP" if bar_1m.get("is_overlap_session", False) else (
            "LONDON" if bar_1m.get("is_london_session", False) else (
                "NY" if bar_1m.get("is_ny_session", False) else "OFF_HOURS"
            )
        )

        if position.signal_type == SignalType.BUY:
            sl_condition = bar_low <= position.sl_price
            tp1_condition = (not position.tp1_hit) and (bar_high >= position.tp1_price)
            tp2_condition = position.tp1_hit and (bar_high >= position.tp2_price)

            tick_validated = True
            if sl_condition and (tp1_condition or tp2_condition):
                if tick_data is not None and not tick_data.empty:
                    first_hit = self._resolve_tick_sequence(position, tick_data)
                    if first_hit == "SL":
                        tp1_condition = tp2_condition = False
                    else:
                        sl_condition = False
                else:
                    sl_condition = True
                    tp1_condition = tp2_condition = False
                    tick_validated = False

            if sl_condition:
                exit_price = min(position.sl_price, bar_low) - slippage_offset
                exit_reason = ExitReason.BREAKEVEN_HIT if position.breakeven_locked else ExitReason.SL_HIT
                trade_rec = self._create_trade_record(
                    position=position,
                    exit_time=bar_time,
                    exit_price=exit_price,
                    closed_lots=position.current_lots,
                    exit_reason=exit_reason,
                    spread_points=bar_spread_points,
                    session_name=session_name,
                    tick_validated=tick_validated,
                )
                records.append(trade_rec)
                return records, None

            if tp1_condition:
                partial_lots = round(position.original_lots * position.tp1_ratio, 2)
                partial_lots = max(self.config.min_lot, min(position.current_lots, partial_lots))

                trade_rec = self._create_trade_record(
                    position=position,
                    exit_time=bar_time,
                    exit_price=position.tp1_price,
                    closed_lots=partial_lots,
                    exit_reason=ExitReason.TP1_HIT,
                    spread_points=bar_spread_points,
                    session_name=session_name,
                    tick_validated=tick_validated,
                )
                records.append(trade_rec)

                position.current_lots = round(position.current_lots - partial_lots, 2)
                position.tp1_hit = True
                position.breakeven_locked = True
                position.sl_price = position.entry_price + (spread_price_offset * 2.0) + slippage_offset

                if position.current_lots <= 0:
                    return records, None

            if tp2_condition:
                trade_rec = self._create_trade_record(
                    position=position,
                    exit_time=bar_time,
                    exit_price=position.tp2_price,
                    closed_lots=position.current_lots,
                    exit_reason=ExitReason.TP2_HIT,
                    spread_points=bar_spread_points,
                    session_name=session_name,
                    tick_validated=tick_validated,
                )
                records.append(trade_rec)
                return records, None

        else:  # SignalType.SELL
            sl_condition = (bar_high + (spread_price_offset * 2.0)) >= position.sl_price
            tp1_condition = (not position.tp1_hit) and (bar_low <= position.tp1_price)
            tp2_condition = position.tp1_hit and (bar_low <= position.tp2_price)

            tick_validated = True
            if sl_condition and (tp1_condition or tp2_condition):
                if tick_data is not None and not tick_data.empty:
                    first_hit = self._resolve_tick_sequence(position, tick_data)
                    if first_hit == "SL":
                        tp1_condition = tp2_condition = False
                    else:
                        sl_condition = False
                else:
                    sl_condition = True
                    tp1_condition = tp2_condition = False
                    tick_validated = False

            if sl_condition:
                exit_price = max(position.sl_price, bar_high + (spread_price_offset * 2.0)) + slippage_offset
                exit_reason = ExitReason.BREAKEVEN_HIT if position.breakeven_locked else ExitReason.SL_HIT
                trade_rec = self._create_trade_record(
                    position=position,
                    exit_time=bar_time,
                    exit_price=exit_price,
                    closed_lots=position.current_lots,
                    exit_reason=exit_reason,
                    spread_points=bar_spread_points,
                    session_name=session_name,
                    tick_validated=tick_validated,
                )
                records.append(trade_rec)
                return records, None

            if tp1_condition:
                partial_lots = round(position.original_lots * position.tp1_ratio, 2)
                partial_lots = max(self.config.min_lot, min(position.current_lots, partial_lots))

                trade_rec = self._create_trade_record(
                    position=position,
                    exit_time=bar_time,
                    exit_price=position.tp1_price,
                    closed_lots=partial_lots,
                    exit_reason=ExitReason.TP1_HIT,
                    spread_points=bar_spread_points,
                    session_name=session_name,
                    tick_validated=tick_validated,
                )
                records.append(trade_rec)

                position.current_lots = round(position.current_lots - partial_lots, 2)
                position.tp1_hit = True
                position.breakeven_locked = True
                position.sl_price = position.entry_price - (spread_price_offset * 2.0) - slippage_offset

                if position.current_lots <= 0:
                    return records, None

            if tp2_condition:
                trade_rec = self._create_trade_record(
                    position=position,
                    exit_time=bar_time,
                    exit_price=position.tp2_price,
                    closed_lots=position.current_lots,
                    exit_reason=ExitReason.TP2_HIT,
                    spread_points=bar_spread_points,
                    session_name=session_name,
                    tick_validated=tick_validated,
                )
                records.append(trade_rec)
                return records, None

        return records, position

    def _create_trade_record(
        self,
        position: Position,
        exit_time: datetime,
        exit_price: float,
        closed_lots: float,
        exit_reason: ExitReason,
        spread_points: float,
        session_name: str,
        tick_validated: bool,
    ) -> TradeRecord:
        """Helper to compute PnL, costs, and format a TradeRecord."""
        if position.signal_type == SignalType.BUY:
            price_diff = exit_price - position.entry_price
        else:
            price_diff = position.entry_price - exit_price

        gross_pnl = price_diff * closed_lots * self.config.contract_size
        commission = self.config.commission_per_lot * closed_lots
        spread_cost = (spread_points * self.config.point_value) * closed_lots * self.config.contract_size
        slippage_cost = (self.config.slippage_pips * 0.10) * closed_lots * self.config.contract_size
        net_pnl = gross_pnl - commission

        return TradeRecord(
            position_id=position.position_id,
            strategy_id=position.strategy_id,
            signal_type=position.signal_type,
            entry_time=position.entry_time,
            exit_time=exit_time,
            entry_price=position.entry_price,
            exit_price=exit_price,
            lots=closed_lots,
            gross_pnl=gross_pnl,
            net_pnl=net_pnl,
            spread_cost=spread_cost,
            slippage_cost=slippage_cost,
            commission=commission,
            exit_reason=exit_reason,
            session_name=session_name,
            tick_validated=tick_validated,
        )

    def _resolve_tick_sequence(self, position: Position, tick_df: pd.DataFrame) -> str:
        """Walks tick dataframe to determine whether SL or TP was hit first."""
        target_tp = position.tp2_price if position.tp1_hit else position.tp1_price

        for _, row in tick_df.iterrows():
            bid = float(row["bid"])
            ask = float(row.get("ask", bid))

            if position.signal_type == SignalType.BUY:
                if bid <= position.sl_price:
                    return "SL"
                if bid >= target_tp:
                    return "TP"
            else:
                if ask >= position.sl_price:
                    return "SL"
                if ask <= target_tp:
                    return "TP"

        return "SL"
