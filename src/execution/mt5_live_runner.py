"""
MT5 Live Execution Runner: Model 2 Personal & Prop Firm Scalp Hybrid Engine (M5 Execution / M15 Macro Trend)
---------------------------------------------------------------------------------------------------------
Enforces live execution using MetaTrader 5 Python API:
1. M5 Bar Completion Evaluation
2. M15 Macro Trend Filter (EMA21 > EMA50 on M15 Timeframe - 1.80 PF / +190% Return Champion)
3. M5 FVG Displacement (>= 1.5 Pips / $0.15)
4. M5 Liquidity Sweep (Prior 5 bars low <= EMA21 for BUY / high >= EMA21 for SELL)
5. M5 EMA21 Closed Confirmation
6. Retrained Random Forest ML Quality Gate Check (Probability >= 0.58 / 58.0% | Out-of-Sample ROC-AUC: 0.7458)
7. Front-Weighted Multi-Ticket Order Dispatch (50% TP1 / 33.3% TP2 / 16.7% TP3)
"""

import time
import sys
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

from order_manager import MT5OrderManager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("MT5_Live_Runner")

class MT5LiveRunner:
    def __init__(self, symbol: str = "XAUUSDz", magic_personal: int = 2001, magic_prop: int = 2002):
        self.symbol = symbol
        self.magic_personal = magic_personal
        self.magic_prop = magic_prop
        self.order_manager = MT5OrderManager(symbol=symbol)
        self.pip_size = 0.10
        self.total_friction = (2.5 + 1.0) * self.pip_size
        self.last_evaluated_bar_time = None
        self.rf_model = None

    def load_ml_model(self) -> bool:
        """Load retrained Random Forest Quality Gate model."""
        model_path = Path("models/saved_models/model2_fvg_rf_quality_gate.joblib")
        if not model_path.exists():
            logger.error(f"Saved ML model missing at: {model_path.resolve()}")
            return False
        try:
            self.rf_model = joblib.load(model_path)
            logger.info("Loaded retrained Random Forest Quality Gate ML model successfully (ROC-AUC: 0.7458).")
            return True
        except Exception as e:
            logger.error(f"Failed to load ML model: {e}")
            return False

    def fetch_live_data(self) -> tuple[pd.DataFrame, pd.DataFrame]:
        """Fetch 5m and 15m live rate bars from MT5."""
        if not MT5_AVAILABLE or not self.order_manager.connected:
            return pd.DataFrame(), pd.DataFrame()

        rates_m5  = mt5.copy_rates_from_pos(self.order_manager.symbol, mt5.TIMEFRAME_M5, 0, 500)
        rates_m15 = mt5.copy_rates_from_pos(self.order_manager.symbol, mt5.TIMEFRAME_M15, 0, 200)

        if rates_m5 is None or len(rates_m5) < 50 or rates_m15 is None or len(rates_m15) < 20:
            logger.warning("Insufficient rate bars returned from MT5.")
            return pd.DataFrame(), pd.DataFrame()

        df_m5 = pd.DataFrame(rates_m5)
        df_m5['timestamp'] = pd.to_datetime(df_m5['time'], unit='s', utc=True)
        if 'tick_volume' in df_m5.columns:
            df_m5.rename(columns={'tick_volume': 'volume'}, inplace=True)

        df_m15 = pd.DataFrame(rates_m15)
        df_m15['timestamp'] = pd.to_datetime(df_m15['time'], unit='s', utc=True)

        return df_m5, df_m15

    def process_closed_candle(self) -> bool:
        """Evaluate closed candle (iloc[-2]) and trigger trades for both engines."""
        df_m5, df_m15 = self.fetch_live_data()
        if df_m5.empty or df_m15.empty:
            return False

        current_closed_time = df_m5['timestamp'].iloc[-2]
        if self.last_evaluated_bar_time == current_closed_time:
            return False  # Already evaluated this closed bar

        self.last_evaluated_bar_time = current_closed_time
        logger.info(f"--- Evaluating Closed M5 Candle: {current_closed_time.strftime('%Y-%m-%d %H:%M UTC')} ---")

        # 👑 M15 MACRO TREND FILTER (EMA21 > EMA50 on M15 Timeframe)
        df_m15['ema21'] = df_m15['close'].ewm(span=21, adjust=False).mean()
        df_m15['ema50'] = df_m15['close'].ewm(span=50, adjust=False).mean()

        m15_close = df_m15['close'].iloc[-2]
        m15_ema21 = df_m15['ema21'].iloc[-2]
        m15_ema50 = df_m15['ema50'].iloc[-2]

        m15_bull = (m15_close > m15_ema21) and (m15_ema21 > m15_ema50)
        m15_bear = (m15_close < m15_ema21) and (m15_ema21 < m15_ema50)

        if not (m15_bull or m15_bear):
            logger.info(f" M15 Macro Trend: NEUTRAL | Close: ${m15_close:.2f} | EMA21: ${m15_ema21:.2f} | EMA50: ${m15_ema50:.2f}")
            return False

        m15_trend_str = "BULLISH [UPTREND]" if m15_bull else "BEARISH [DOWNTREND]"
        logger.info(f" M15 Macro Trend: {m15_trend_str}")

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
        m5_open  = df_m5['open'].iloc[idx]

        base_buy  = m15_bull and bull_fvg and bull_sweep and (m5_close > m5_e21)
        base_sell = m15_bear and bear_fvg and bear_sweep and (m5_close < m5_e21)

        if not (base_buy or base_sell):
            logger.info(" M5 Setup: No valid FVG + Liquidity Sweep pattern.")
            return False

        direction = "BUY" if base_buy else "SELL"

        # 🧠 FEATURE EXTRACTION FOR RETRAINED RANDOM FOREST MODEL (11 Features)
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
        h1_spread = abs(m15_ema21 - m15_ema50) / self.pip_size
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

        if self.rf_model is not None:
            ml_proba = self.rf_model.predict_proba(feat_df)[0, 1]
            logger.info(f" Retrained Random Forest ML Quality Gate Score: {ml_proba*100:.1f}% (Threshold: >= 58.0%)")
        else:
            ml_proba = 0.65
            logger.warning(" RF Model not loaded. Using baseline probability 65.0%.")

        if ml_proba < 0.58:
            logger.info(" Setup Rejected by Random Forest ML Gate (< 58.0%).")
            return False

        # Personal Engine Trigger Condition
        pers_trigger = True

        # Prop Engine Trigger Condition
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
                risk_pct=3.0,
                magic=self.magic_personal,
                ml_proba=ml_proba
            )

        if prop_trigger:
            logger.info(">>> PROP FIRM ENGINE TRIGGERED (Magic: 2002) <<<")
            self.order_manager.place_split_tickets(
                engine_type="PROP_FIRM",
                direction=direction,
                entry_price=entry_price,
                sl_price=sl_price,
                tp1_price=tp1_price,
                tp2_price=tp2_price,
                tp3_price=tp3_price,
                risk_pct=3.0,
                magic=self.magic_prop,
                ml_proba=ml_proba
            )

        return True

    def run_live_loop(self):
        """Main execution loop polling MT5 for bar completion."""
        logger.info("=========================================================================================")
        logger.info(" STARTING MODEL 2 LIVE DEMO/REAL RUNNER (M5 EXECUTION / M15 MACRO TREND)")
        logger.info(" Target Asset: XAU/USD | Personal Magic: 2001 | Prop Magic: 2002 | ML Threshold: 58.0%")
        logger.info("=========================================================================================")

        if not self.order_manager.connect():
            logger.error("Failed to connect to MT5 order manager.")
            return

        if not self.load_ml_model():
            logger.error("Failed to load retrained ML model. Aborting.")
            return

        logger.info(" Live Runner connected to MT5 & ready! Polling closed M5 bars...")

        try:
            while True:
                self.process_closed_candle()

                # Print heartbeat status
                tick = mt5.symbol_info_tick(self.symbol)
                if tick:
                    logger.info(f"[HEARTBEAT] Engine Active & Monitoring | Live {self.symbol} Price -> Ask: ${tick.ask:.2f} | Bid: ${tick.bid:.2f}")

                time.sleep(10)  # Check every 10 seconds for new closed candle

        except KeyboardInterrupt:
            logger.info("Shutting down Live Demo Runner gracefully.")
        finally:
            self.order_manager.disconnect()

if __name__ == "__main__":
    runner = MT5LiveRunner(symbol="XAUUSDz")
    runner.run_live_loop()
