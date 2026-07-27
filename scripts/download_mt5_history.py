#!/usr/bin/env python3
"""
download_mt5_history.py - MT5 Historical Data Downloader

Downloads historical XAUUSD tick and M1/M5 bar data directly from an active MetaTrader 5 terminal,
standardizes timestamps to UTC, and writes raw immutable files to data/raw/MT5/.
"""

import os
import sys
import argparse
import pandas as pd
from datetime import datetime, timezone

def download_mt5_data(symbol: str = "XAUUSD", timeframe: str = "M1", start_date: str = "2021-01-01", end_date: str = None, output_dir: str = "data/raw/MT5"):
    """
    Downloads historical data using the MetaTrader5 Python API.
    If MetaTrader5 package is not available or terminal connection fails, raises RuntimeError with clear instructions.
    """
    try:
        import MetaTrader5 as mt5
    except ImportError:
        raise ImportError("MetaTrader5 python package not installed. Run 'pip install MetaTrader5' when connected to an active MT5 terminal.")

    if not mt5.initialize():
        raise RuntimeError(f"MetaTrader5 initialization failed. Ensure MT5 terminal is open and logged in. Error: {mt5.last_error()}")

    dt_start = datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    dt_end = datetime.strptime(end_date, "%Y-%m-%d").replace(tzinfo=timezone.utc) if end_date else datetime.now(timezone.utc)

    print(f"[INFO] Fetching {symbol} {timeframe} history from MT5 terminal ({start_date} to {end_date or 'NOW'})...")

    if timeframe.upper() == "TICK":
        ticks = mt5.copy_ticks_range(symbol, dt_start, dt_end, mt5.COPY_TICKS_ALL)
        if ticks is None or len(ticks) == 0:
            mt5.shutdown()
            raise RuntimeError(f"No tick data returned from MT5 for {symbol}.")
        df = pd.DataFrame(ticks)
        df["timestamp"] = pd.to_datetime(df["time_msc"], unit="ms", utc=True)
        df = df.rename(columns={"bid": "bid", "ask": "ask", "volume": "volume"})
        cols = ["timestamp", "bid", "ask", "volume"]
        df = df[[c for c in cols if c in df.columns]]
    else:
        tf_map = {
            "M1": mt5.TIMEFRAME_M1,
            "M5": mt5.TIMEFRAME_M5,
            "M15": mt5.TIMEFRAME_M15,
            "H1": mt5.TIMEFRAME_H1
        }
        mt5_tf = tf_map.get(timeframe.upper(), mt5.TIMEFRAME_M1)
        rates = mt5.copy_rates_range(symbol, mt5_tf, dt_start, dt_end)
        if rates is None or len(rates) == 0:
            mt5.shutdown()
            raise RuntimeError(f"No rate data returned from MT5 for {symbol} {timeframe}.")
        df = pd.DataFrame(rates)
        df["timestamp"] = pd.to_datetime(df["time"], unit="s", utc=True)
        cols = ["timestamp", "open", "high", "low", "close", "tick_volume", "spread"]
        df = df[[c for c in cols if c in df.columns]]

    mt5.shutdown()

    os.makedirs(output_dir, exist_ok=True)
    out_file = os.path.join(output_dir, f"{symbol}_{timeframe}_{start_date.replace('-','')}_raw.csv")
    df.to_csv(out_file, index=False)
    print(f"[SUCCESS] Saved MT5 raw dataset to {out_file} (Rows: {len(df)})")
    return out_file

def main():
    parser = argparse.ArgumentParser(description="Download raw historical XAUUSD data from active MT5 terminal")
    parser.add_argument("--symbol", type=str, default="XAUUSD", help="Symbol (default: XAUUSD)")
    parser.add_argument("--timeframe", type=str, default="M1", choices=["TICK", "M1", "M5", "M15", "H1"], help="Granularity")
    parser.add_argument("--start", type=str, default="2021-01-01", help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", type=str, default=None, help="End date (YYYY-MM-DD)")
    parser.add_argument("--output_dir", type=str, default="data/raw/MT5", help="Output directory")

    args = parser.parse_args()
    download_mt5_data(args.symbol, args.timeframe, args.start, args.end, args.output_dir)

if __name__ == "__main__":
    main()
