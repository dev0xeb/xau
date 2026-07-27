#!/usr/bin/env python3
"""
broker_interface.py - Abstract Broker Adapter Interface

Defines the generic base class BrokerAdapter for all broker connections (MT5, Simulation, FIX, etc.).
"""

from abc import ABC, abstractmethod

class BrokerAdapter(ABC):

    @abstractmethod
    def connect(self) -> bool:
        pass

    @abstractmethod
    def disconnect(self) -> bool:
        pass

    @abstractmethod
    def place_order(self, order_payload: dict) -> dict:
        pass

    @abstractmethod
    def modify_order(self, ticket: int, sl: float, tp: float) -> dict:
        pass

    @abstractmethod
    def cancel_order(self, ticket: int) -> dict:
        pass

    @abstractmethod
    def get_positions(self) -> list:
        pass

    @abstractmethod
    def get_orders(self) -> list:
        pass

    @abstractmethod
    def get_account_info(self) -> dict:
        pass
