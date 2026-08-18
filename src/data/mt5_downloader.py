"""
MT5 Historical Data Downloader Module.

Handles chunked monthly downloads of 1-minute historical rates from MetaTrader 5,
broker server time normalization, spread integrity checks, and disk persistence.
"""

from datetime import datetime, timezone
from pathlib import Path
import logging
import pandas as pd

try:
    import MetaTrader5 as mt5
    MT5_AVAILABLE = True
except ImportError:
    MT5_AVAILABLE = False

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


class MT5DataDownloader:
    """Manages connections to MT5 terminal and downloads historical rate data."""

    def __init__(self, symbol: str = "XAUUSD"):
        self.requested_symbol = symbol
        self.symbol = symbol
        self.connected = False

    def connect(self) -> bool:
        """Initialize connection to MetaTrader 5 terminal and resolve active Gold symbol."""
        if not MT5_AVAILABLE:
            logger.error("MetaTrader5 package is not installed.")
            return False

        if not mt5.initialize():
            logger.error(f"MT5 initialization failed. Error code: {mt5.last_error()}")
            return False

        # Query all available symbols in broker terminal
        all_symbols = mt5.symbols_get()
        if all_symbols is None:
            logger.error(f"Failed to query symbols from MT5 terminal. Error: {mt5.last_error()}")
            mt5.shutdown()
            return False

        symbol_names = [s.name for s in all_symbols]
        logger.info(f"Connected to MT5 terminal. Found {len(symbol_names)} total symbols.")

        # Match exact or partial symbol name (XAUUSD, GOLD, etc.)
        matched_symbol = None

        # Direct match check
        if self.requested_symbol in symbol_names:
            matched_symbol = self.requested_symbol
        else:
            # Prioritize XAUUSD / GOLD USD pairs over cross pairs (e.g. BTCXAU, XAUAUD)
            xauusd_matches = [name for name in symbol_names if "XAUUSD" in name.upper() or "GOLDUSD" in name.upper()]
            gold_matches = [name for name in symbol_names if "XAU" in name.upper() or "GOLD" in name.upper()]
            
            if xauusd_matches:
                matched_symbol = xauusd_matches[0]
                logger.info(f"Gold symbol auto-detected (XAUUSD priority): '{matched_symbol}' out of matches: {xauusd_matches}")
            elif gold_matches:
                matched_symbol = gold_matches[0]
                logger.info(f"Gold symbol auto-detected: '{matched_symbol}' out of matches: {gold_matches}")
            else:
                logger.error(f"No Gold symbol (XAU/GOLD) found among broker symbols. Samples: {symbol_names[:10]}")
                mt5.shutdown()
                return False

        # Select symbol in Market Watch
        if not mt5.symbol_select(matched_symbol, True):
            logger.error(f"Failed to select symbol '{matched_symbol}' in MT5 Market Watch.")
            mt5.shutdown()
            return False

        self.symbol = matched_symbol
        self.connected = True
        logger.info(f"Successfully connected and selected active symbol: '{self.symbol}'")
        return True

    def disconnect(self):
        """Shutdown MT5 terminal connection."""
        if self.connected and MT5_AVAILABLE:
            mt5.shutdown()
            self.connected = False
            logger.info("MT5 connection closed.")

    def verify_spread_integrity(self, df: pd.DataFrame) -> dict:
        """Inspects spread column to determine if real broker spreads are present."""
        if "spread" not in df.columns:
            return {"is_real_spread": False, "mean_spread": 0.0, "min_spread": 0, "max_spread": 0}

        non_zero_spreads = (df["spread"] > 0).sum()
        total_rows = len(df)
        is_real = (non_zero_spreads / total_rows) > 0.8 if total_rows > 0 else False

        return {
            "is_real_spread": is_real,
            "mean_spread": float(df["spread"].mean()) if total_rows > 0 else 0.0,
            "min_spread": int(df["spread"].min()) if total_rows > 0 else 0,
            "max_spread": int(df["spread"].max()) if total_rows > 0 else 0,
            "zero_spread_ratio": float((df["spread"] == 0).sum() / total_rows) if total_rows > 0 else 0.0,
        }

    def download_month_chunk(
        self, year: int, month: int, chunks_dir: Path
    ) -> pd.DataFrame:
        """Downloads a single monthly chunk of 1-minute data and caches it to Parquet."""
        chunks_dir.mkdir(parents=True, exist_ok=True)
        chunk_file = chunks_dir / f"xau_1m_{year}_{month:02d}.parquet"

        # Return cached chunk if available
        if chunk_file.exists():
            logger.info(f"Loading cached chunk: {chunk_file.name}")
            try:
                df = pd.read_parquet(chunk_file)
                return df
            except Exception as e:
                logger.warning(f"Failed to read cache {chunk_file.name}: {e}. Redownloading...")

        if not self.connected:
            raise RuntimeError("MT5 terminal is not connected. Call connect() first.")

        # Determine start and end datetime for month in UTC
        start_utc = datetime(year, month, 1, 0, 0, 0, tzinfo=timezone.utc)
        if month == 12:
            end_utc = datetime(year + 1, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        else:
            end_utc = datetime(year, month + 1, 1, 0, 0, 0, tzinfo=timezone.utc)

        logger.info(f"Downloading {self.symbol} 1m data for {year}-{month:02d}...")

        rates = mt5.copy_rates_range(
            self.symbol, mt5.TIMEFRAME_M1, start_utc, end_utc
        )

        if rates is None or len(rates) == 0:
            logger.warning(f"No rates returned for {year}-{month:02d}. MT5 error: {mt5.last_error()}")
            return pd.DataFrame()

        # Convert numpy array to pandas DataFrame
        df = pd.DataFrame(rates)

        # Rename columns to standardized schema
        df["timestamp"] = pd.to_datetime(df["time"], unit="s", utc=True)
        df.drop(columns=["time"], inplace=True)

        # Standardize volume column names
        if "tick_volume" in df.columns:
            df.rename(columns={"tick_volume": "volume"}, inplace=True)

        # Reorder columns
        cols = ["timestamp", "open", "high", "low", "close", "volume", "spread"]
        if "real_volume" in df.columns:
            cols.append("real_volume")

        df = df[[c for c in cols if c in df.columns]]

        # Clean invalid bars (e.g. high < low or zero prices)
        valid_mask = (df["high"] >= df["low"]) & (df["open"] > 0) & (df["close"] > 0)
        df = df[valid_mask].copy()

        # Sort by timestamp
        df.sort_values("timestamp", inplace=True)
        df.reset_index(drop=True, inplace=True)

        # Save to Parquet cache
        df.to_parquet(chunk_file, index=False)
        logger.info(f"Saved chunk {chunk_file.name} ({len(df):,} rows)")

        return df

    def download_history(
        self, start_year: int = 2021, end_year: int = 2026, chunks_dir: str = "data/raw/chunks"
    ) -> pd.DataFrame:
        """Downloads full multi-year 1m historical dataset in monthly chunks."""
        chunks_path = Path(chunks_dir)
        all_chunks = []

        now = datetime.now(timezone.utc)
        current_year = now.year
        current_month = now.month

        for year in range(start_year, end_year + 1):
            for month in range(1, 13):
                # Don't request future months
                if year > current_year or (year == current_year and month > current_month):
                    continue

                chunk_df = self.download_month_chunk(year, month, chunks_path)
                if not chunk_df.empty:
                    all_chunks.append(chunk_df)

        if not all_chunks:
            logger.error("No data chunks were downloaded.")
            return pd.DataFrame()

        master_df = pd.concat(all_chunks, ignore_index=True)
        master_df.drop_duplicates(subset=["timestamp"], inplace=True)
        master_df.sort_values("timestamp", inplace=True)
        master_df.reset_index(drop=True, inplace=True)

        logger.info(f"Master 1m dataset ready: {len(master_df):,} total rows from {master_df['timestamp'].min()} to {master_df['timestamp'].max()}")
        return master_df
