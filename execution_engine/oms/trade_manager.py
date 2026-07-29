#!/usr/bin/env python3
"""
trade_manager.py - Active Trade & Position Lifecycle Manager

Manages open positions:
- Stop-Loss / Take-Profit enforcement
- Trailing Stop & Break-Even adjustment triggers
- Partial exits
- Emergency Flatten / manual override
"""

class TradeManager:
    """Active trade lifecycle manager for open positions."""

    def __init__(
        self,
        trailing_stop_dist_usd: float = 1.50,
        break_even_trigger_usd: float = 2.00,
        enable_trailing_stop: bool = True
    ):
        self.trailing_stop_dist_usd = trailing_stop_dist_usd
        self.break_even_trigger_usd = break_even_trigger_usd
        self.enable_trailing_stop = enable_trailing_stop
        self.tracked_positions = {}  # ticket -> position dict

    def register_position(self, oms_record: dict) -> dict:
        """Registers a newly filled order for active management."""
        ticket = oms_record.get("broker_ticket")
        if not ticket:
            return None

        pos = {
            "ticket": ticket,
            "candidate_id": oms_record.get("candidate_id"),
            "oms_uuid": oms_record.get("oms_uuid"),
            "direction": oms_record.get("direction", "BUY"),
            "open_price": oms_record.get("broker_fill_price", 2350.50),
            "volume_lots": oms_record.get("volume_lots", 0.1),
            "sl_price": oms_record.get("sl", 0.0),
            "tp_price": oms_record.get("tp", 0.0),
            "is_break_even": False,
            "status": "OPEN"
        }

        self.tracked_positions[ticket] = pos
        return pos

    def update_positions_with_market_tick(self, current_tick: dict, broker_adapter) -> list:
        """
        Evaluates open positions against current market price.
        Applies Break-Even and Trailing Stop modifications via broker_adapter if enabled.
        """
        if not self.enable_trailing_stop:
            return []

        bid = current_tick["bid"]
        ask = current_tick["ask"]
        updates = []

        for ticket, pos in list(self.tracked_positions.items()):
            if pos["status"] != "OPEN":
                continue

            direction = pos["direction"]
            open_price = pos["open_price"]

            if direction == "BUY":
                current_price = bid
                pnl_dist = current_price - open_price

                # 1. Break-Even Check (+ $2.00/oz -> + $20 profit trigger)
                if pnl_dist >= self.break_even_trigger_usd and not pos["is_break_even"]:
                    new_sl = round(open_price + 0.10, 2)
                    broker_adapter.modify_order(ticket, sl=new_sl, tp=pos["tp_price"])
                    pos["sl_price"] = new_sl
                    pos["is_break_even"] = True
                    updates.append({"ticket": ticket, "action": "MOVED_TO_BREAK_EVEN", "new_sl": new_sl})

                # 2. Trailing Stop Check
                elif pos["is_break_even"] and current_price - pos["sl_price"] > self.trailing_stop_dist_usd:
                    new_sl = round(current_price - self.trailing_stop_dist_usd, 2)
                    if new_sl > pos["sl_price"]:
                        broker_adapter.modify_order(ticket, sl=new_sl, tp=pos["tp_price"])
                        pos["sl_price"] = new_sl
                        updates.append({"ticket": ticket, "action": "TRAILING_STOP_UPDATED", "new_sl": new_sl})

            elif direction == "SELL":
                current_price = ask
                pnl_dist = open_price - current_price

                # 1. Break-Even Check (+ $2.00/oz -> + $20 profit trigger)
                if pnl_dist >= self.break_even_trigger_usd and not pos["is_break_even"]:
                    new_sl = round(open_price - 0.10, 2)
                    broker_adapter.modify_order(ticket, sl=new_sl, tp=pos["tp_price"])
                    pos["sl_price"] = new_sl
                    pos["is_break_even"] = True
                    updates.append({"ticket": ticket, "action": "MOVED_TO_BREAK_EVEN", "new_sl": new_sl})

                # 2. Trailing Stop Check
                elif pos["is_break_even"] and pos["sl_price"] - current_price > self.trailing_stop_dist_usd:
                    new_sl = round(current_price + self.trailing_stop_dist_usd, 2)
                    if new_sl < pos["sl_price"]:
                        broker_adapter.modify_order(ticket, sl=new_sl, tp=pos["tp_price"])
                        pos["sl_price"] = new_sl
                        updates.append({"ticket": ticket, "action": "TRAILING_STOP_UPDATED", "new_sl": new_sl})

        return updates

    def emergency_flatten(self, broker_adapter) -> list:
        """
        Emergency flatten command: Closes all active open positions immediately.
        """
        closed_tickets = []
        for ticket, pos in list(self.tracked_positions.items()):
            if pos["status"] == "OPEN":
                broker_adapter.cancel_order(ticket)
                pos["status"] = "EMERGENCY_CLOSED"
                closed_tickets.append(ticket)

        print(f"[EMERGENCY FLATTEN] Closed {len(closed_tickets)} open positions.")
        return closed_tickets
