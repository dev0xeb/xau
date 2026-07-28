#!/usr/bin/env python3
"""
market_data_adapter.py - Live Market Data Subscriber & M1 Aggregator

Provides live tick streams, M1 candle updates, bid/ask spread, session status, and server time UTC.
Supports live MT5 Terminal connection via MetaTrader5 Python API, with fallback simulated tick stream.
Supports automatic symbol resolution for broker variations (e.g. XAUUSDz, XAUUSDm, GOLD, GOLD.m).
"""

import time
import random
from datetime import datetime, timezone
from execution_engine.adapters.mt5_adapter import resolve_broker_symbol

try:
    import MetaTrader5 as mt5
    HAS_MT5 = True
except ImportError:
    HAS_MT5 = False

class MarketDataAdapter:
    """Live Market Data Subscriber for MT5 & Dry-Run Environments."""

    def __init__(self, symbol: str = None):
        self.requested_symbol = symbol or "XAUUSD"
        self.symbol = self.requested_symbol
        self.is_connected = False
        self.last_tick_time = None
        self.tick_counter_minute = 0
        self.last_minute_timestamp = time.time()
        self.current_m1_candle = None

    def connect(self) -> bool:
        """Connects to live MT5 feed or initializes dry-run mode."""
        if HAS_MT5:
            if mt5.initialize():
                self.symbol = resolve_broker_symbol(self.requested_symbol)
                mt5.symbol_select(self.symbol, True)
                self.is_connected = True
                print(f"[MARKET DATA] Connected to MT5 Live Feed for '{self.symbol}'")
                return True
        self.is_connected = True
        print(f"[MARKET DATA] Initialized Mock Live Feed for '{self.symbol}'")
        return True

    def get_latest_tick(self) -> dict:
        """Retrieves latest tick quote (bid, ask, spread, time)."""
        now = time.time()
        if now - self.last_minute_timestamp >= 60.0:
            self.tick_counter_minute = 0
            self.last_minute_timestamp = now

        self.tick_counter_minute += 1
        self.last_tick_time = now

        if HAS_MT5 and self.is_connected:
            tick_info = mt5.symbol_info_tick(self.symbol)
            if tick_info:
                bid = float(tick_info.bid)
                ask = float(tick_info.ask)
                spread = round(ask - bid, 3)
                server_time_utc = datetime.fromtimestamp(tick_info.time, tz=timezone.utc).isoformat()
                return {
                    "symbol": self.symbol,
                    "timestamp_utc": server_time_utc,
                    "bid": bid,
                    "ask": ask,
                    "spread_usd": spread,
                    "ticks_last_minute": self.tick_counter_minute
                }

        # Dry-Run Mock Quote Generation
        mock_bid = round(2350.0 + random.uniform(-0.5, 0.5), 2)
        mock_ask = round(mock_bid + 0.15, 2)
        return {
            "symbol": self.symbol,
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "bid": mock_bid,
            "ask": mock_ask,
            "spread_usd": round(mock_ask - mock_bid, 2),
            "ticks_last_minute": self.tick_counter_minute
        }

    def update_m1_candle(self, current_tick: dict) -> dict:
        """
        Aggregates ticks into completed M1 candles.
        Returns candle dict when M1 completes, else None.
        """
        tick_time = current_tick.get("timestamp_utc")
        minute_key = tick_time[:16] + ":00" if tick_time else datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:00")
        price = current_tick.get("bid", 2350.0)

        if self.current_m1_candle is None:
            self.current_m1_candle = {
                "minute_key": minute_key,
                "open": price, "high": price, "low": price, "close": price,
                "volume": 1, "completed": False
            }
            return None

        if minute_key != self.current_m1_candle["minute_key"]:
            completed_candle = self.current_m1_candle
            completed_candle["completed"] = True
            self.current_m1_candle = {
                "minute_key": minute_key,
                "open": price, "high": price, "low": price, "close": price,
                "volume": 1, "completed": False
            }
            return completed_candle

        self.current_m1_candle["high"] = max(self.current_m1_candle["high"], price)
        self.current_m1_candle["low"] = min(self.current_m1_candle["low"], price)
        self.current_m1_candle["close"] = price
        self.current_m1_candle["volume"] += 1
        return None
