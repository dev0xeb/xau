"""
MT5 Order Manager for Model 2 Demo Execution on XAU/USD.
Handles dynamic lot sizing, 3-burst split tickets, MT5 order routing, 
and distinct Magic Numbers/Comments for Personal Engine (2001) and Prop Engine (2002).
"""

import sys
import logging
from pathlib import Path
import pandas as pd
import numpy as np

try:
    import MetaTrader5 as mt5
    MT5_AVAILABLE = True
except ImportError:
    MT5_AVAILABLE = False

Path("logs").mkdir(parents=True, exist_ok=True)
file_handler = logging.FileHandler("logs/demo_execution.log", mode="a", encoding="utf-8")
stream_handler = logging.StreamHandler(sys.stdout)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[file_handler, stream_handler]
)
logger = logging.getLogger("OrderManager")

class MT5OrderManager:
    """Manages order routing, lot sizing, and split-ticket placement for both strategy engines."""

    MAGIC_PERSONAL = 2001
    MAGIC_PROP = 2002

    COMMENT_PERSONAL = "[PERS_ENG]"
    COMMENT_PROP = "[PROP_ENG]"

    def __init__(self, symbol: str = "XAUUSD", account_balance: float = 5000.0, risk_pct: float = 1.0):
        self.requested_symbol = symbol
        self.symbol = symbol
        self.account_balance = account_balance
        self.risk_pct = risk_pct
        self.connected = False

    def connect(self) -> bool:
        """Initialize connection to MetaTrader 5 terminal."""
        if not MT5_AVAILABLE:
            logger.error("MetaTrader5 python library is not installed.")
            return False

        if not mt5.initialize():
            logger.error(f"MT5 initialization failed. Error code: {mt5.last_error()}")
            return False

        all_symbols = mt5.symbols_get()
        if all_symbols:
            symbol_names = [s.name for s in all_symbols]
            xauusd_matches = [name for name in symbol_names if "XAUUSD" in name.upper() or "GOLDUSD" in name.upper()]
            gold_matches = [name for name in symbol_names if "XAU" in name.upper() or "GOLD" in name.upper()]

            if self.requested_symbol in symbol_names:
                self.symbol = self.requested_symbol
            elif xauusd_matches:
                self.symbol = xauusd_matches[0]
                logger.info(f"Gold symbol auto-detected: '{self.symbol}'")
            elif gold_matches:
                self.symbol = gold_matches[0]
                logger.info(f"Gold symbol auto-detected: '{self.symbol}'")

        if not mt5.symbol_select(self.symbol, True):
            logger.warning(f"Could not explicitly select symbol '{self.symbol}' in Market Watch. Proceeding...")

        account_info = mt5.account_info()
        if account_info is not None:
            self.account_balance = account_info.balance
            logger.info(f"Connected to MT5 Demo Account #{account_info.login} on {account_info.server}")
            logger.info(f"Active Symbol: '{self.symbol}' | Account Balance: ${self.account_balance:,.2f} USD")
        else:
            logger.info(f"Connected to MT5. Using specified baseline balance: ${self.account_balance:,.2f}")

        self.connected = True
        return True

    def calculate_lot_size(self, ticket_risk_usd: float, sl_distance_dollars: float) -> float:
        """Calculate lot size per ticket given risk dollars and SL distance in dollars."""
        if sl_distance_dollars <= 0:
            return 0.01

        symbol_info = mt5.symbol_info(self.symbol) if self.connected else None
        contract_size = symbol_info.trade_contract_size if symbol_info else 100.0
        min_lot = symbol_info.volume_min if symbol_info else 0.01
        step_lot = symbol_info.volume_step if symbol_info else 0.01
        max_lot = symbol_info.volume_max if symbol_info else 100.0

        raw_lots = ticket_risk_usd / (sl_distance_dollars * contract_size)
        steps = round(raw_lots / step_lot)
        lots = steps * step_lot
        lots = max(min_lot, min(max_lot, lots))
        return round(lots, 2)

    def place_split_tickets(
        self,
        engine_type: str,  # 'PERSONAL' or 'PROP'
        direction: str,    # 'BUY' or 'SELL'
        entry_price: float,
        sl_price: float,
        tp1_price: float,
        tp2_price: float,
        tp3_price: float,
        dry_run: bool = False
    ) -> bool:
        """Place 3 split tickets for TP1 (1.0x), TP2 (2.0x), and TP3 (3.0x) with distinct Magic Number."""
        magic_number = self.MAGIC_PERSONAL if engine_type.upper() == 'PERSONAL' else self.MAGIC_PROP
        comment = self.COMMENT_PERSONAL if engine_type.upper() == 'PERSONAL' else self.COMMENT_PROP

        # Total 1% risk on $5,000 = $50.00 total risk -> $16.67 per ticket
        account_info = mt5.account_info() if self.connected else None
        current_balance = account_info.balance if account_info else self.account_balance
        total_risk_usd = current_balance * (self.risk_pct / 100.0)
        ticket_risk_usd = total_risk_usd / 3.0

        sl_dist = abs(entry_price - sl_price)
        lot_per_ticket = self.calculate_lot_size(ticket_risk_usd, sl_dist)

        logger.info(f"[{engine_type} ENGINE] Signal Triggered: {direction} @ ${entry_price:.2f}")
        logger.info(f"   SL: ${sl_price:.2f} (Dist: ${sl_dist:.2f}) | TP1: ${tp1_price:.2f} | TP2: ${tp2_price:.2f} | TP3: ${tp3_price:.2f}")
        logger.info(f"   Lot Sizing: 3 Tickets x {lot_per_ticket:.2f} Lots (Risk per ticket: ${ticket_risk_usd:.2f}) | Magic: {magic_number}")

        if dry_run:
            logger.info(f"   [DRY-RUN MODE] 3 Tickets logged successfully for {engine_type} engine. No broker order sent.")
            return True

        if not self.connected:
            logger.error("MT5 terminal not connected. Cannot send order.")
            return False

        order_type = mt5.ORDER_TYPE_BUY if direction.upper() == 'BUY' else mt5.ORDER_TYPE_SELL
        tp_levels = [tp1_price, tp2_price, tp3_price]

        symbol_info = mt5.symbol_info(self.symbol)
        point = symbol_info.point if symbol_info else 0.01
        min_stop_dist = (symbol_info.stops_level * point) if (symbol_info and symbol_info.stops_level > 0) else 0.30

        success_count = 0
        for i, tp in enumerate(tp_levels, 1):
            tick = mt5.symbol_info_tick(self.symbol)
            live_price = (tick.ask if direction.upper() == 'BUY' else tick.bid) if tick else entry_price

            # Enforce minimum broker stops distance
            adjusted_sl = sl_price
            adjusted_tp = tp

            if direction.upper() == 'BUY':
                if (live_price - adjusted_sl) < min_stop_dist:
                    adjusted_sl = live_price - min_stop_dist
                if (adjusted_tp - live_price) < min_stop_dist:
                    adjusted_tp = live_price + min_stop_dist
            else:
                if (adjusted_sl - live_price) < min_stop_dist:
                    adjusted_sl = live_price + min_stop_dist
                if (live_price - adjusted_tp) < min_stop_dist:
                    adjusted_tp = live_price - min_stop_dist

            request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": self.symbol,
                "volume": lot_per_ticket,
                "type": order_type,
                "price": live_price,
                "sl": round(adjusted_sl, 2),
                "tp": round(adjusted_tp, 2),
                "deviation": 30,
                "magic": magic_number,
                "comment": f"{comment}_TP{i}",
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_IOC,
            }
            result = mt5.order_send(request)
            if result is not None and result.retcode == mt5.TRADE_RETCODE_DONE:
                logger.info(f"   [SUCCESS] Ticket #{i}/3 Placed! Order Ticket: {result.order} | TP: ${adjusted_tp:.2f}")
                success_count += 1
                self.record_trade_csv(
                    order_ticket=result.order,
                    engine_type=engine_type,
                    magic=magic_number,
                    direction=direction,
                    volume=lot_per_ticket,
                    entry=live_price,
                    sl=adjusted_sl,
                    tp=adjusted_tp,
                    comment=f"{comment}_TP{i}"
                )
            else:
                ret_code = result.retcode if result else mt5.last_error()
                logger.error(f"   [FAILED] Ticket #{i}/3 Error Code: {ret_code}")

        return success_count == 3

    def record_trade_csv(self, order_ticket, engine_type, magic, direction, volume, entry, sl, tp, comment):
        """Append executed trade details to logs/executed_trades.csv."""
        csv_path = Path("logs/executed_trades.csv")
        file_exists = csv_path.exists()
        df_row = pd.DataFrame([{
            "timestamp": pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%d %H:%M:%S UTC"),
            "order_ticket": order_ticket,
            "engine_type": engine_type,
            "magic_number": magic,
            "symbol": self.symbol,
            "direction": direction,
            "volume_lots": volume,
            "entry_price": entry,
            "sl_price": sl,
            "tp_price": tp,
            "comment": comment
        }])
        df_row.to_csv(csv_path, mode="a", header=not file_exists, index=False)

    def manage_live_trailing_stops(self, trailing_mode: int = 3):
        """
        Monitors active positions for Magic 2001 (Personal) and Magic 2002 (Prop).
        When 2 out of 3 tickets have closed (meaning TP1 and TP2 hit),
        trails remaining Ticket 3's SL to TP1 Price (Mode 3)!
        """
        if not self.connected or not MT5_AVAILABLE:
            return

        positions = mt5.positions_get(symbol=self.symbol)
        if not positions:
            return

        for magic in [self.MAGIC_PERSONAL, self.MAGIC_PROP]:
            engine_label = "PERSONAL" if magic == self.MAGIC_PERSONAL else "PROP"
            engine_positions = [p for p in positions if p.magic == magic]

            # Mode 3: Check if exactly 1 ticket remains out of 3 (meaning TP1 and TP2 have filled)
            if len(engine_positions) == 1:
                p3 = engine_positions[0]
                comment = p3.comment

                if "_TP3" in comment or "TP3" in comment or p3.volume > 0:
                    entry_price = p3.price_open
                    direction = "BUY" if p3.type == mt5.ORDER_TYPE_BUY else "SELL"
                    current_sl = p3.sl

                    # Calculate TP1 Price (entry +/- 1.0x SL distance)
                    sl_dist = abs(entry_price - current_sl)
                    if sl_dist > 0.50:  # Valid SL distance
                        tp1_price = (entry_price + sl_dist) if direction == "BUY" else (entry_price - sl_dist)

                        should_modify = False
                        if direction == "BUY" and (current_sl < tp1_price or current_sl == 0):
                            should_modify = True
                        elif direction == "SELL" and (current_sl > tp1_price or current_sl == 0):
                            should_modify = True

                        if should_modify:
                            request = {
                                "action": mt5.TRADE_ACTION_SLTP,
                                "position": p3.ticket,
                                "symbol": self.symbol,
                                "sl": round(tp1_price, 2),
                                "tp": p3.tp
                            }
                            result = mt5.order_send(request)
                            if result is not None and result.retcode == mt5.TRADE_RETCODE_DONE:
                                logger.info(f"[{engine_label} LIVE TRAILING] Ticket 3 #{p3.ticket} SL moved to TP1 Price: ${tp1_price:.2f} (TP2 hit locked in!)")


