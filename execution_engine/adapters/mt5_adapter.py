#!/usr/bin/env python3
"""
mt5_adapter.py - MetaTrader 5 Broker Adapter with Automatic Symbol Resolver

Implements BrokerAdapter interface using MetaTrader5 Python API for XAUUSD order routing,
position queries, and automatic Broker Capability Discovery.
Supports automatic symbol resolution for broker variations (e.g. XAUUSDz, XAUUSDm, GOLD, GOLD.m).
"""

import sys
import os
import json
from execution_engine.adapters.broker_interface import BrokerAdapter

try:
    import MetaTrader5 as mt5
    HAS_MT5 = True
except ImportError:
    HAS_MT5 = False


def resolve_broker_symbol(default_symbol: str = "XAUUSD") -> str:
    """
    Auto-discovers and resolves the exact Gold trading symbol on the connected MT5 broker.
    Supports suffix variations: XAUUSDz, XAUUSDm, XAUUSD.a, XAUUSD_i, GOLD, GOLD.m, etc.
    """
    import configs.env_loader  # Auto-load .env
    env_symbol = os.environ.get("SYMBOL", os.environ.get("MT5_SYMBOL", "")).strip()

    if env_symbol:
        return env_symbol

    if not HAS_MT5 or not mt5.initialize():
        return default_symbol

    # Check default symbol directly first
    info = mt5.symbol_info(default_symbol)
    if info is not None:
        mt5.symbol_select(default_symbol, True)
        return default_symbol

    # Query all available symbols from broker
    all_symbols = mt5.symbols_get()
    if all_symbols:
        symbol_names = [s.name for s in all_symbols]

        # 1. Search for XAUUSD prefix variations (XAUUSDz, XAUUSDm, etc.)
        xau_matches = [s for s in symbol_names if s.upper().startswith("XAUUSD")]
        if xau_matches:
            matched = xau_matches[0]
            mt5.symbol_select(matched, True)
            print(f"[SYMBOL RESOLVER] Auto-discovered broker Gold symbol: '{matched}'")
            return matched

        # 2. Search for GOLD prefix variations (GOLD, GOLD.m, etc.)
        gold_matches = [s for s in symbol_names if s.upper().startswith("GOLD")]
        if gold_matches:
            matched = gold_matches[0]
            mt5.symbol_select(matched, True)
            print(f"[SYMBOL RESOLVER] Auto-discovered broker Gold symbol: '{matched}'")
            return matched

    return default_symbol


class MT5Adapter(BrokerAdapter):

    def __init__(self, symbol: str = None, config_dir: str = "configs"):
        self.requested_symbol = symbol or "XAUUSD"
        self.symbol = self.requested_symbol
        self.config_dir = config_dir
        os.makedirs(self.config_dir, exist_ok=True)
        self.connected = False
        self.broker_profile = {}

    def connect(self) -> bool:
        if not HAS_MT5:
            print("[WARNING] MetaTrader5 package not installed. Operating in API standby mode.")
            self.connected = False
            self.discover_broker_capabilities()
            return False

        import configs.env_loader  # Auto-load .env
        login = os.environ.get("MT5_ACCOUNT_LOGIN", os.environ.get("MT5_LOGIN"))
        password = os.environ.get("MT5_ACCOUNT_PASSWORD", os.environ.get("MT5_PASSWORD"))
        server = os.environ.get("MT5_SERVER")
        path = os.environ.get("MT5_PATH")

        init_kwargs = {}
        if path and os.path.exists(path):
            init_kwargs["path"] = path
        if login and login.isdigit():
            init_kwargs["login"] = int(login)
        if password:
            init_kwargs["password"] = password
        if server:
            init_kwargs["server"] = server

        init_success = mt5.initialize(**init_kwargs) if init_kwargs else mt5.initialize()
        if not init_success:
            print(f"[ERROR] MT5 initialize failed: {mt5.last_error()}")
            self.connected = False
            return False

        # Auto-resolve broker Gold symbol (XAUUSD, XAUUSDz, XAUUSDm, GOLD, etc.)
        self.symbol = resolve_broker_symbol(self.requested_symbol)

        symbol_info = mt5.symbol_info(self.symbol)
        if symbol_info is None or not symbol_info.visible:
            mt5.symbol_select(self.symbol, True)

        self.connected = True
        self.discover_broker_capabilities()
        print(f"[SUCCESS] Connected to MetaTrader 5 Terminal for '{self.symbol}'")
        return True

    def discover_broker_capabilities(self) -> dict:
        """
        Discovers broker specifications and saves broker_profile.json.
        """
        if HAS_MT5 and self.connected:
            info = mt5.symbol_info(self.symbol)
            acc = mt5.account_info()
            profile = {
                "symbol": self.symbol,
                "digits": info.digits if info else 2,
                "spread_usd": round((info.ask - info.bid), 2) if info else 0.15,
                "point_size": info.point if info else 0.01,
                "tick_size": info.trade_tick_size if info else 0.01,
                "tick_value": info.trade_tick_value if info else 1.0,
                "contract_size": info.trade_contract_size if info else 100.0,
                "min_lot": info.volume_min if info else 0.01,
                "max_lot": info.volume_max if info else 100.0,
                "volume_step": info.volume_step if info else 0.01,
                "stops_level": info.trade_stops_level if info else 10,
                "freeze_level": info.trade_freeze_level if info else 0,
                "execution_mode": getattr(info, "execution_mode", getattr(info, "trade_exemode", 1)) if info else 1,
                "filling_mode": getattr(info, "filling_mode", getattr(info, "type_filling", 1)) if info else 1,
                "leverage": acc.leverage if acc else 100,
                "currency": acc.currency if acc else "USD"
            }
        else:
            profile = {
                "symbol": self.symbol,
                "digits": 2,
                "spread_usd": 0.15,
                "point_size": 0.01,
                "tick_size": 0.01,
                "tick_value": 1.0,
                "contract_size": 100.0,
                "min_lot": 0.01,
                "max_lot": 100.0,
                "volume_step": 0.01,
                "stops_level": 10,
                "freeze_level": 0,
                "execution_mode": 1,
                "filling_mode": 1,
                "leverage": 100,
                "currency": "USD"
            }

        self.broker_profile = profile
        profile_path = os.path.join(self.config_dir, "broker_profile.json")
        with open(profile_path, "w") as f:
            json.dump(profile, f, indent=2)

        return profile

    def disconnect(self) -> bool:
        if HAS_MT5 and self.connected:
            mt5.shutdown()
        self.connected = False
        print("[INFO] Disconnected from MetaTrader 5 Terminal.")
        return True

    def place_order(self, order_payload: dict) -> dict:
        if not self.connected or not HAS_MT5:
            return {
                "success": False,
                "retcode": 10001,
                "comment": "MT5 Not Connected",
                "ticket": 0,
                "fill_price": 0.0
            }

        direction = order_payload.get("direction", "BUY")
        volume = order_payload.get("volume_lots", 0.1)
        tick_info = mt5.symbol_info_tick(self.symbol)

        if tick_info is None:
            return {
                "success": False,
                "retcode": 10001,
                "comment": f"MT5 Tick Info Unavailable for {self.symbol}",
                "ticket": 0,
                "fill_price": 0.0
            }

        price = float(tick_info.ask if direction == "BUY" else tick_info.bid)
        sl_val = float(order_payload.get("sl", 0.0))
        tp_val = float(order_payload.get("tp", 0.0))

        # Enforce failsafe non-zero SL/TP if missing
        if sl_val == 0.0:
            sl_val = round(price - 3.0, 2) if direction == "BUY" else round(price + 3.0, 2)
        if tp_val == 0.0:
            tp_val = round(price + 6.0, 2) if direction == "BUY" else round(price - 6.0, 2)

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": self.symbol,
            "volume": float(volume),
            "type": mt5.ORDER_TYPE_BUY if direction == "BUY" else mt5.ORDER_TYPE_SELL,
            "price": price,
            "sl": sl_val,
            "tp": tp_val,
            "deviation": 20,
            "magic": 1001,
            "comment": order_payload.get("candidate_id", "XAU_SCALP"),
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }

        result = mt5.order_send(request)
        if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
            retcode = result.retcode if result else 10001
            comment = result.comment if result else f"Order Send Error: {mt5.last_error()}"
            return {
                "success": False,
                "retcode": retcode,
                "comment": comment,
                "ticket": 0,
                "fill_price": 0.0
            }

        return {
            "success": True,
            "retcode": result.retcode,
            "comment": "FILLED",
            "ticket": result.order,
            "fill_price": result.price
        }

    def modify_order(self, ticket: int, sl: float = 0.0, tp: float = 0.0, **kwargs) -> bool:
        if not HAS_MT5 or not self.connected:
            return False

        sl_val = float(sl if sl != 0.0 else kwargs.get("new_sl", 0.0))
        tp_val = float(tp if tp != 0.0 else kwargs.get("new_tp", 0.0))

        request = {
            "action": mt5.TRADE_ACTION_SLTP,
            "position": ticket,
            "symbol": self.symbol,
            "sl": sl_val,
            "tp": tp_val
        }
        res = mt5.order_send(request)
        if res is None or res.retcode != mt5.TRADE_RETCODE_DONE:
            # Fallback retry without explicit symbol field if broker demands position-only
            alt_req = {
                "action": mt5.TRADE_ACTION_SLTP,
                "position": ticket,
                "sl": sl_val,
                "tp": tp_val
            }
            res = mt5.order_send(alt_req)

        return res is not None and res.retcode == mt5.TRADE_RETCODE_DONE

    def cancel_order(self, ticket: int) -> bool:
        if not HAS_MT5 or not self.connected:
            return False

        request = {
            "action": mt5.TRADE_ACTION_REMOVE,
            "order": ticket
        }
        res = mt5.order_send(request)
        return res is not None and res.retcode == mt5.TRADE_RETCODE_DONE

    def get_positions(self) -> list:
        if not HAS_MT5 or not self.connected:
            return []
        pos = mt5.positions_get(symbol=self.symbol)
        if pos is None:
            return []
        return [p._asdict() for p in pos]

    def get_orders(self) -> list:
        if not HAS_MT5 or not self.connected:
            return []
        orders = mt5.orders_get(symbol=self.symbol)
        if orders is None:
            return []
        return [o._asdict() for o in orders]

    def get_account_info(self) -> dict:
        if not HAS_MT5:
            return {"balance": 10000.0, "equity": 10000.0, "margin": 0.0, "free_margin": 10000.0}
        acc = mt5.account_info()
        if acc is None:
            return {"balance": 10000.0, "equity": 10000.0, "margin": 0.0, "free_margin": 10000.0}
        return {
            "balance": acc.balance,
            "equity": acc.equity,
            "margin": acc.margin,
            "free_margin": acc.margin_free,
            "leverage": acc.leverage
        }
