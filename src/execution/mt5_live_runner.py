"""
Real-Time MT5 Live Runner for Model 2 (M5 Scalp Hybrid Strategy Engine).
Runs dual Personal (Magic 2001) & Prop Firm (Magic 2002) engines on M5 closed candles.
"""

import sys
import time
import argparse
import logging
from pathlib import Path
import pandas as pd
import numpy as np
import joblib

try:
    import MetaTrader5 as mt5
    MT5_AVAILABLE = True
except ImportError:
    MT5_AVAILABLE = False

Path("logs").mkdir(parents=True, exist_ok=True)
file_handler = logging.FileHandler("logs/mt5_live_runner.log", mode="a", encoding="utf-8")
stream_handler = logging.StreamHandler(sys.stdout)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[file_handler, stream_handler]
)
logger = logging.getLogger("LiveRunner")

sys.path.insert(0, str(Path(__file__).resolve().parent))
from order_manager import MT5OrderManager

class Model2LiveRunner:
    """Monitors MT5 live candles and executes Model 2 for Personal & Prop Firm Engines."""

    def __init__(self, symbol: str = "XAUUSD", balance: float = 5000.0, dry_run: bool = True):
        self.symbol = symbol
        self.balance = balance
        self.dry_run = dry_run
        self.order_manager = MT5OrderManager(symbol=symbol, account_balance=balance)
        self.rf_model = None
        self.pip_size = 0.10
        self.total_friction = 0.35  # 3.5 pips friction
        self.last_evaluated_bar_time = None

    def load_model(self) -> bool:
        """Load saved Random Forest ML model."""
        model_path = Path("src/models/model2_rf_gate.joblib")
        if not model_path.exists():
            logger.error(f"Saved ML model missing at: {model_path.resolve()}")
            return False
        try:
            self.rf_model = joblib.load(model_path)
            logger.info("Loaded Random Forest Quality Gate ML model successfully.")
            return True
        except Exception as e:
            logger.error(f"Failed to load ML model: {e}")
            return False

    def fetch_live_data(self) -> tuple[pd.DataFrame, pd.DataFrame]:
        """Fetch 5m and 1h live rate bars from MT5."""
        if not MT5_AVAILABLE or not self.order_manager.connected:
            return pd.DataFrame(), pd.DataFrame()

        rates_m5 = mt5.copy_rates_from_pos(self.order_manager.symbol, mt5.TIMEFRAME_M5, 0, 500)
        rates_h1 = mt5.copy_rates_from_pos(self.order_manager.symbol, mt5.TIMEFRAME_H1, 0, 200)

        if rates_m5 is None or len(rates_m5) < 50 or rates_h1 is None or len(rates_h1) < 20:
            logger.warning("Insufficient rate bars returned from MT5.")
            return pd.DataFrame(), pd.DataFrame()

        df_m5 = pd.DataFrame(rates_m5)
        df_m5['timestamp'] = pd.to_datetime(df_m5['time'], unit='s', utc=True)
        if 'tick_volume' in df_m5.columns:
            df_m5.rename(columns={'tick_volume': 'volume'}, inplace=True)

        df_h1 = pd.DataFrame(rates_h1)
        df_h1['timestamp'] = pd.to_datetime(df_h1['time'], unit='s', utc=True)

        return df_m5, df_h1

    def process_closed_candle(self) -> bool:
        """Evaluate closed candle (iloc[-2]) and trigger trades for both engines."""
        df_m5, df_h1 = self.fetch_live_data()
        if df_m5.empty or df_h1.empty:
            return False

        current_closed_time = df_m5['timestamp'].iloc[-2]
        if self.last_evaluated_bar_time == current_closed_time:
            return False  # Already evaluated this closed bar

        self.last_evaluated_bar_time = current_closed_time
        logger.info(f"--- Evaluating Closed M5 Candle: {current_closed_time.strftime('%Y-%m-%d %H:%M UTC')} ---")

        # H1 Trend
        df_h1['ema21'] = df_h1['close'].ewm(span=21, adjust=False).mean()
        df_h1['ema50'] = df_h1['close'].ewm(span=50, adjust=False).mean()

        h1_close = df_h1['close'].iloc[-2]
        h1_ema21 = df_h1['ema21'].iloc[-2]
        h1_ema50 = df_h1['ema50'].iloc[-2]

        h1_bull = (h1_close > h1_ema21) and (h1_ema21 > h1_ema50)
        h1_bear = (h1_close < h1_ema21) and (h1_ema21 < h1_ema50)

        if not (h1_bull or h1_bear):
            logger.info(f" H1 Macro Trend: NEUTRAL | Close: ${h1_close:.2f} | EMA21: ${h1_ema21:.2f} | EMA50: ${h1_ema50:.2f}")
            return False

        h1_trend_str = "BULLISH [UPTREND]" if h1_bull else "BEARISH [DOWNTREND]"
        logger.info(f" H1 Macro Trend: {h1_trend_str}")

        # M5 Indicators
        df_m5['m5_ema21'] = df_m5['close'].ewm(span=21, adjust=False).mean()

        # Daily VWAP
        df_m5['date'] = df_m5['timestamp'].dt.date
        tp_vol = (df_m5['high'] + df_m5['low'] + df_m5['close']) / 3.0 * df_m5['volume']
        df_m5['tp_vol'] = tp_vol
        df_m5['cum_tp_vol'] = df_m5.groupby('date')['tp_vol'].cumsum()
        df_m5['cum_vol'] = df_m5.groupby('date')['volume'].cumsum()
        cum_vol = df_m5['cum_vol'].replace(0, 1.0)
        df_m5['daily_vwap'] = df_m5['cum_tp_vol'] / cum_vol

        # Inspection Candle (iloc[-2])
        idx = len(df_m5) - 2
        low_t = df_m5['low'].iloc[idx]
        high_t = df_m5['high'].iloc[idx]
        low_t2 = df_m5['low'].iloc[idx - 2]
        high_t2 = df_m5['high'].iloc[idx - 2]

        bull_fvg_size = (low_t - high_t2) / self.pip_size
        bear_fvg_size = (low_t2 - high_t) / self.pip_size

        bull_fvg = bull_fvg_size >= 1.5
        bear_fvg = bear_fvg_size >= 1.5

        prior_5_low = df_m5['low'].iloc[idx-5:idx].min()
        prior_5_high = df_m5['high'].iloc[idx-5:idx].max()
        m5_e21 = df_m5['m5_ema21'].iloc[idx]

        bull_sweep = prior_5_low <= m5_e21
        bear_sweep = prior_5_high >= m5_e21

        c_vwap = df_m5['daily_vwap'].iloc[idx]
        m5_close = df_m5['close'].iloc[idx]
        m5_open = df_m5['open'].iloc[idx]

        base_buy = h1_bull and bull_fvg and bull_sweep and (m5_close > m5_e21)
        base_sell = h1_bear and bear_fvg and bear_sweep and (m5_close < m5_e21)

        if not (base_buy or base_sell):
            logger.info(" M5 Setup: No valid FVG + Liquidity Sweep pattern.")
            return False

        direction = "BUY" if base_buy else "SELL"

        # Feature extraction
        highs = df_m5['high'].values
        lows = df_m5['low'].values
        closes = df_m5['close'].values
        volumes = df_m5['volume'].values

        tr = np.maximum(highs - lows, np.maximum(np.abs(highs - np.roll(closes, 1)), np.abs(lows - np.roll(closes, 1))))
        tr[0] = highs[0] - lows[0]
        atr5 = pd.Series(tr).ewm(span=5, adjust=False).mean().values[idx]
        atr20 = pd.Series(tr).ewm(span=20, adjust=False).mean().values[idx]

        delta = pd.Series(closes).diff()
        gain = (delta.where(delta > 0, 0)).ewm(alpha=1/14, adjust=False).mean()
        loss = (-delta.where(delta < 0, 0)).ewm(alpha=1/14, adjust=False).mean()
        rs = gain / (loss + 1e-9)
        rsi14 = (100 - (100 / (1 + rs))).values[idx]
        vol_sma20 = pd.Series(volumes).rolling(20, min_periods=1).mean().values[idx]

        if direction == "BUY":
            entry_price = high_t2 + self.total_friction
            recent_3_low = df_m5['low'].iloc[idx-2:idx+1].min()
            sl_price = recent_3_low - 0.50
            sl_pips = np.clip((entry_price - sl_price) / self.pip_size, 15.0, 80.0)
            sl_price = entry_price - (sl_pips * self.pip_size)

            tp1_price = entry_price + (sl_pips * self.pip_size * 1.0)
            tp2_price = entry_price + (sl_pips * self.pip_size * 2.0)
            tp3_price = entry_price + (sl_pips * self.pip_size * 3.0)
        else:
            entry_price = low_t2 - self.total_friction
            recent_3_high = df_m5['high'].iloc[idx-2:idx+1].max()
            sl_price = recent_3_high + 0.50
            sl_pips = np.clip((sl_price - entry_price) / self.pip_size, 15.0, 80.0)
            sl_price = entry_price + (sl_pips * self.pip_size)

            tp1_price = entry_price - (sl_pips * self.pip_size * 1.0)
            tp2_price = entry_price - (sl_pips * self.pip_size * 2.0)
            tp3_price = entry_price - (sl_pips * self.pip_size * 3.0)

        fvg_size = bull_fvg_size if direction == "BUY" else bear_fvg_size
        sweep_depth = (m5_e21 - prior_5_low) / self.pip_size if direction == "BUY" else (prior_5_high - m5_e21) / self.pip_size
        vwap_dist = abs(entry_price - c_vwap) / self.pip_size
        atr_ratio = atr5 / (atr20 + 1e-9)
        h1_spread = abs(h1_ema21 - h1_ema50) / self.pip_size
        m5_slope = (m5_e21 - df_m5['m5_ema21'].iloc[idx-3]) / self.pip_size
        body_ratio = abs(m5_close - m5_open) / (high_t - low_t + 1e-6)
        vol_ratio = volumes[idx] / (vol_sma20 + 1e-9)
        hour_val = df_m5['timestamp'].dt.hour.iloc[idx]

        swing_20_high = df_m5['high'].iloc[idx-20:idx].max()
        swing_20_low = df_m5['low'].iloc[idx-20:idx].min()
        dist_swing = (entry_price - swing_20_low) / self.pip_size if direction == "BUY" else (swing_20_high - entry_price) / self.pip_size

        feat_df = pd.DataFrame([{
            'f_fvg_size': fvg_size,
            'f_sweep_depth': sweep_depth,
            'f_vwap_dist': vwap_dist,
            'f_atr_ratio': atr_ratio,
            'f_h1_spread': h1_spread,
            'f_m5_slope': m5_slope,
            'f_body_ratio': body_ratio,
            'f_rsi_14': rsi14,
            'f_vol_ratio': vol_ratio,
            'f_dist_swing': dist_swing,
            'f_hour_utc': hour_val
        }])

        ml_proba = self.rf_model.predict_proba(feat_df)[0, 1]
        logger.info(f" Random Forest ML Quality Gate Score: {ml_proba*100:.1f}% (Threshold: >= 50.0%)")

        if ml_proba < 0.50:
            logger.info(" Setup Rejected by Random Forest ML Gate.")
            return False

        # Personal Engine Trigger Condition (H1 + FVG + Sweep + ML >= 50%)
        pers_trigger = True

        # Prop Engine Trigger Condition (Personal + Daily VWAP Alignment)
        vwap_bull = m5_close > c_vwap
        vwap_bear = m5_close < c_vwap
        prop_trigger = vwap_bull if direction == "BUY" else vwap_bear

        if pers_trigger:
            logger.info(">>> PERSONAL ACCOUNT ENGINE TRIGGERED (Magic: 2001) <<<")
            self.order_manager.place_split_tickets(
                engine_type="PERSONAL",
                direction=direction,
                entry_price=entry_price,
                sl_price=sl_price,
                tp1_price=tp1_price,
                tp2_price=tp2_price,
                tp3_price=tp3_price,
                dry_run=self.dry_run
            )

        if prop_trigger:
            logger.info(">>> PROP FIRM ENGINE TRIGGERED (Magic: 2002) <<<")
            self.order_manager.place_split_tickets(
                engine_type="PROP",
                direction=direction,
                entry_price=entry_price,
                sl_price=sl_price,
                tp1_price=tp1_price,
                tp2_price=tp2_price,
                tp3_price=tp3_price,
                dry_run=self.dry_run
            )
        elif pers_trigger:
            logger.info("   [Prop Engine Skipped: Daily VWAP filter not aligned]")

        return True

    def run_live_loop(self):
        """Start live monitoring loop."""
        logger.info("=========================================================================")
        logger.info(f" STARTING MODEL 2 LIVE DEMO ENGINE ({self.symbol})")
        logger.info(f" Baseline Account Equity: ${self.balance:,.2f} USD")
        logger.info(f" Execution Mode: {'DRY-RUN (PAPER TRADING)' if self.dry_run else 'LIVE MT5 DEMO ORDER ROUTING'}")
        logger.info(" Tagging Rules: Magic 2001 [PERS_ENG] | Magic 2002 [PROP_ENG]")
        logger.info("=========================================================================\n")

        if not self.load_model():
            return

        if not self.order_manager.connect():
            logger.warning("MT5 connect returned false. Running offline/test check...")

        try:
            loop_count = 0
            while True:
                self.process_closed_candle()
                self.order_manager.manage_live_trailing_stops(trailing_mode=3)
                loop_count += 1
                if loop_count % 6 == 0:  # Every 60 seconds
                    tick = mt5.symbol_info_tick(self.order_manager.symbol) if MT5_AVAILABLE and self.order_manager.connected else None
                    price_str = f"Ask: ${tick.ask:.2f} | Bid: ${tick.bid:.2f}" if tick else "Polling MT5..."
                    logger.info(f"[HEARTBEAT] Engine Active & Monitoring | Live {self.order_manager.symbol} Price -> {price_str}")
                time.sleep(10)  # Check every 10 seconds for new closed candle
        except KeyboardInterrupt:
            logger.info("Shutting down Live Demo Runner gracefully.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Model 2 MT5 Live Demo Runner")
    parser.add_argument("--symbol", type=str, default="XAUUSD", help="Symbol name")
    parser.add_argument("--balance", type=float, default=5000.0, help="Starting account balance")
    parser.add_argument("--dry-run", action="store_true", default=False, help="Run in dry-run paper trading mode")
    parser.add_argument("--single-pass", action="store_true", help="Evaluate current closed bar once and exit")

    args = parser.parse_args()

    runner = Model2LiveRunner(symbol=args.symbol, balance=args.balance, dry_run=args.dry_run)
    if args.single_pass:
        runner.load_model()
        runner.order_manager.connect()
        runner.process_closed_candle()
    else:
        runner.run_live_loop()
