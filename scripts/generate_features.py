#!/usr/bin/env python3
"""
generate_features.py - Neutral Research Feature Engineering Engine

Calculates zero-logic research features for XAUUSD datasets:
- Price features (OHLC, Mid, Returns, Log Returns)
- Tick Microstructure features (if Tick data)
- Volatility features (ATR, Rolling Vol, Body/Wicks, Range)
- Liquidity features (Spread Percentile, Expansion, Contraction)
- Time & Session Event Labels (Asian/London/NY, Opens/Closes, Macro Windows)
- Objective Market Regime Labels (TRENDING, RANGING, EXPANDING, CONTRACTING, HIGH_VOL, LOW_VOL)
- Market Structure features (Swing Highs/Lows, Trend Slope)
- Research features (Consecutive Candles, Compression/Expansion periods)
- Execution Cost Baselines (Spread, Commission, Slippage, Total Round-Trip USD & Pts)
"""

import os
import sys
import argparse
import pandas as pd
import numpy as np

def compute_atr(df: pd.DataFrame, window: int = 14) -> pd.Series:
    high = df["high"]
    low = df["low"]
    close = df["close"]
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.rolling(window, min_periods=1).mean()

def compute_rolling_slope(series: pd.Series, window: int = 20) -> pd.Series:
    x = np.arange(window)
    x_sum = x.sum()
    x2_sum = (x**2).sum()

    def calc_slope(y_arr):
        if len(y_arr) < window or np.isnan(y_arr).any():
            return 0.0
        y_sum = y_arr.sum()
        xy_sum = (x * y_arr).sum()
        n = window
        denom = (n * x2_sum - x_sum**2)
        if denom == 0:
            return 0.0
        return (n * xy_sum - x_sum * y_sum) / denom

    return series.rolling(window, min_periods=window).apply(calc_slope, raw=True).fillna(0.0)

def generate_research_features(input_file: str, output_file: str) -> pd.DataFrame:
    if not os.path.exists(input_file):
        raise FileNotFoundError(f"Input file not found: {input_file}")

    print(f"[INFO] Generating research features for {input_file}...")
    if input_file.endswith(".parquet"):
        df = pd.read_parquet(input_file)
    else:
        df = pd.read_csv(input_file)

    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.sort_values(by="timestamp").reset_index(drop=True)

    is_tick = "bid" in df.columns and "ask" in df.columns and "open" not in df.columns

    # 1. Price Features
    if is_tick:
        df["mid"] = (df["bid"] + df["ask"]) / 2.0
        df["spread"] = (df["ask"] - df["bid"]).round(4)
        df["ret_abs"] = df["mid"].diff().fillna(0.0)
        df["ret_log"] = np.log(df["mid"] / df["mid"].shift(1)).fillna(0.0)

        # Microstructure Features
        df["time_diff"] = df["timestamp"].diff().dt.total_seconds().fillna(0.0)
        df["tick_arrival_rate"] = np.where(df["time_diff"] > 0, 1.0 / df["time_diff"], 0.0)
        df["bid_changed"] = (df["bid"].diff() != 0).astype(int)
        df["ask_changed"] = (df["ask"].diff() != 0).astype(int)
        df["quote_update_freq"] = (df["bid_changed"] | df["ask_changed"]).rolling(20, min_periods=1).mean()
        df["micro_volatility"] = df["ret_abs"].rolling(20, min_periods=1).std().fillna(0.0)
        df["micro_momentum"] = df["ret_abs"].rolling(10, min_periods=1).sum()
        df["direction_changed"] = ((df["ret_abs"] * df["ret_abs"].shift(1)) < 0).astype(int)
        df["price_acceleration"] = df["ret_abs"].diff().fillna(0.0)
    else:
        for col in ["open", "high", "low", "close"]:
            if col in df.columns:
                df[col] = df[col].astype(float)

        df["mid"] = (df["open"] + df["close"]) / 2.0
        if "spread" not in df.columns:
            df["spread"] = 0.20  # Default nominal baseline spread if not present
        df["spread"] = df["spread"].astype(float)
        df["ret_abs"] = df["close"].diff().fillna(0.0)
        df["ret_log"] = np.log(df["close"] / df["close"].shift(1)).fillna(0.0)

        # 2. Volatility Features
        df["high_low_range"] = df["high"] - df["low"]
        df["body_size"] = (df["close"] - df["open"]).abs()
        df["upper_wick"] = df["high"] - df[["open", "close"]].max(axis=1)
        df["lower_wick"] = df[["open", "close"]].min(axis=1) - df["low"]
        df["atr_14"] = compute_atr(df, 14)
        df["vol_rolling_20"] = df["ret_abs"].rolling(20, min_periods=1).std().fillna(0.0)
        df["vol_rolling_60"] = df["ret_abs"].rolling(60, min_periods=1).std().fillna(0.0)

        # 3. Liquidity Features
        df["spread_rolling_mean_100"] = df["spread"].rolling(100, min_periods=1).mean()
        df["spread_percentile_100"] = df["spread"].rolling(100, min_periods=1).apply(
            lambda x: (pd.Series(x).rank(pct=True).iloc[-1]) if len(x) > 0 else 0.5, raw=False
        ).fillna(0.5)
        df["spread_expansion"] = df["spread"] / np.maximum(df["spread_rolling_mean_100"], 0.001)
        df["spread_contraction"] = df["spread_rolling_mean_100"] / np.maximum(df["spread"], 0.001)

        # 4. Market Structure Features
        df["swing_high_5"] = df["high"].rolling(5, min_periods=1).max()
        df["swing_low_5"] = df["low"].rolling(5, min_periods=1).min()
        df["swing_high_15"] = df["high"].rolling(15, min_periods=1).max()
        df["swing_low_15"] = df["low"].rolling(15, min_periods=1).min()
        df["trend_slope_20"] = compute_rolling_slope(df["close"], 20)

        # 5. Research Features
        is_bull = (df["close"] > df["open"]).astype(int)
        is_bear = (df["close"] < df["open"]).astype(int)
        df["consecutive_bullish"] = is_bull.groupby((is_bull != is_bull.shift()).cumsum()).cumsum() * is_bull
        df["consecutive_bearish"] = is_bear.groupby((is_bear != is_bear.shift()).cumsum()).cumsum() * is_bear

        range_p20 = df["high_low_range"].rolling(100, min_periods=1).quantile(0.20)
        range_p80 = df["high_low_range"].rolling(100, min_periods=1).quantile(0.80)
        df["compression_period"] = (df["high_low_range"] <= range_p20).astype(int)
        df["expansion_period"] = (df["high_low_range"] >= range_p80).astype(int)

    # 6. Time & Session Event Features
    df["utc_hour"] = df["timestamp"].dt.hour
    df["utc_minute"] = df["timestamp"].dt.minute
    df["day_of_week"] = df["timestamp"].dt.dayofweek
    df["week_of_year"] = df["timestamp"].dt.isocalendar().week.astype(int)
    df["month"] = df["timestamp"].dt.month

    # Session Labels
    # Asian: 00:00 - 06:59, London: 07:00 - 11:59, Overlap: 12:00 - 15:59, NY: 16:00 - 20:59, Asian_Off: 21:00-23:59
    conditions = [
        (df["utc_hour"] >= 0) & (df["utc_hour"] < 7),
        (df["utc_hour"] >= 7) & (df["utc_hour"] < 12),
        (df["utc_hour"] >= 12) & (df["utc_hour"] < 16),
        (df["utc_hour"] >= 16) & (df["utc_hour"] < 21)
    ]
    choices = ["Asian", "London", "London_NY_Overlap", "NY"]
    df["session_label"] = np.select(conditions, choices, default="Asian_Offscreen")

    # Session Event Labels
    df["event_asian_open"] = ((df["utc_hour"] == 0) & (df["utc_minute"] < 5)).astype(int)
    df["event_london_open"] = ((df["utc_hour"] == 7) & (df["utc_minute"] < 5)).astype(int)
    df["event_ny_open"] = ((df["utc_hour"] == 12) & (df["utc_minute"] < 5)).astype(int)
    df["event_london_close"] = ((df["utc_hour"] == 16) & (df["utc_minute"] < 5)).astype(int)
    df["event_ny_close"] = ((df["utc_hour"] == 21) & (df["utc_minute"] < 5)).astype(int)
    df["event_friday_close"] = ((df["day_of_week"] == 4) & (df["utc_hour"] >= 20)).astype(int)

    # Macro Event Windows (Placeholder flags for NFP first Friday, CPI mid-month, FOMC Wednesdays)
    df["macro_nfp_window"] = ((df["day_of_week"] == 4) & (df["timestamp"].dt.day <= 7) & (df["utc_hour"] == 13) & (df["utc_minute"] >= 15) & (df["utc_minute"] <= 45)).astype(int)
    df["macro_cpi_window"] = ((df["timestamp"].dt.day >= 10) & (df["timestamp"].dt.day <= 15) & (df["utc_hour"] == 13) & (df["utc_minute"] >= 15) & (df["utc_minute"] <= 45)).astype(int)
    df["macro_fomc_window"] = ((df["day_of_week"] == 2) & (df["utc_hour"] >= 18) & (df["utc_hour"] <= 20)).astype(int)

    # 7. Objective Market Regime Labels (Research Metadata - No strategy logic)
    if not is_tick:
        vol_p75 = df["vol_rolling_20"].rolling(100, min_periods=1).quantile(0.75)
        vol_p25 = df["vol_rolling_20"].rolling(100, min_periods=1).quantile(0.25)
        slope_abs = df["trend_slope_20"].abs()
        slope_p66 = slope_abs.rolling(100, min_periods=1).quantile(0.66)

        df["regime_trending"] = (slope_abs >= slope_p66).astype(int)
        df["regime_ranging"] = (slope_abs < slope_p66).astype(int)
        df["regime_expanding"] = df["expansion_period"]
        df["regime_contracting"] = df["compression_period"]
        df["regime_high_vol"] = (df["vol_rolling_20"] >= vol_p75).astype(int)
        df["regime_low_vol"] = (df["vol_rolling_20"] <= vol_p25).astype(int)

    # 8. Execution Cost Baselines
    df["estimated_spread_usd"] = df["spread"]
    df["estimated_commission_usd"] = 0.05  # $0.05/oz nominal baseline commission
    df["estimated_slippage_usd"] = 0.08    # $0.08/oz nominal baseline slippage
    df["estimated_roundtrip_cost_usd"] = df["estimated_spread_usd"] + df["estimated_commission_usd"] + df["estimated_slippage_usd"]
    df["estimated_roundtrip_cost_pts"] = (df["estimated_roundtrip_cost_usd"] * 100.0).round(2)

    os.makedirs(os.path.dirname(os.path.abspath(output_file)), exist_ok=True)
    if output_file.endswith(".parquet"):
        df.to_parquet(output_file, index=False)
    else:
        df.to_csv(output_file, index=False)

    print(f"[SUCCESS] Research features generated and saved to {output_file} (Total Features: {len(df.columns)}, Rows: {len(df)})")
    return df

def main():
    parser = argparse.ArgumentParser(description="Generate zero-logic research features for XAUUSD datasets")
    parser.add_argument("--input", type=str, required=True, help="Input Parquet or CSV path in data/processed/")
    parser.add_argument("--output", type=str, required=True, help="Destination Parquet/CSV path in data/processed/features/")

    args = parser.parse_args()
    generate_research_features(args.input, args.output)

if __name__ == "__main__":
    main()
