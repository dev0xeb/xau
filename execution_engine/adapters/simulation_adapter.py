#!/usr/bin/env python3
"""
simulation_adapter.py - Simulation Broker Adapter for Dry-Run Testing

Implements BrokerAdapter interface for isolated dry-run unit tests and offline strategy simulation.
"""

from execution_engine.adapters.broker_interface import BrokerAdapter

class SimulationAdapter(BrokerAdapter):

    def __init__(self, symbol: str = "XAUUSD"):
        self.symbol = symbol
        self.connected = False
        self.mock_ticket_counter = 1000

    def connect(self) -> bool:
        self.connected = True
        print(f"[SIMULATION] Connected to Mock Simulation Broker for {self.symbol}")
        return True

    def disconnect(self) -> bool:
        self.connected = False
        print("[SIMULATION] Disconnected from Mock Simulation Broker.")
        return True

    def place_order(self, order_payload: dict) -> dict:
        if not self.connected:
            return {"success": False, "retcode": 10001, "comment": "Not Connected"}

        self.mock_ticket_counter += 1
        return {
            "success": True,
            "retcode": 10009,  # TRADE_RETCODE_DONE
            "comment": "SIMULATED_FILL",
            "ticket": self.mock_ticket_counter,
            "fill_price": 2350.50
        }

    def modify_order(self, ticket: int, sl: float, tp: float) -> dict:
        return {"success": True, "ticket": ticket, "sl": sl, "tp": tp}

    def cancel_order(self, ticket: int) -> dict:
        return {"success": True, "ticket": ticket, "comment": "CANCELLED"}

    def get_positions(self) -> list:
        return [{"ticket": 1001, "symbol": self.symbol, "volume": 0.1, "price_open": 2350.50, "profit": 15.0}]

    def get_orders(self) -> list:
        return []

    def get_account_info(self) -> dict:
        return {"balance": 100000.0, "equity": 100015.0, "margin_free": 99500.0}
