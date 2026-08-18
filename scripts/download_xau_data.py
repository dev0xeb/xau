"""
XAU/USD 5-Year Data Download & Preprocessing Script.

Executes end-to-end historical data acquisition from MetaTrader 5,
runs data gap auditing, DST-aware session tagging, multi-spread aggregation,
and persists datasets in Parquet format.
"""

import sys
from pathlib import Path
import logging
import pandas as pd

# Add src to python path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.data.mt5_downloader import MT5DataDownloader
from src.data.resampler import audit_data_gaps, add_dst_session_flags, resample_bars

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def main():
    print("=" * 70)
    print(" XAU/USD (Gold) 5-Year Data Extraction & Preprocessing Pipeline")
    print("=" * 70)

    raw_dir = Path("data/raw")
    processed_dir = Path("data/processed")
    reports_dir = Path("data/reports")
    chunks_dir = raw_dir / "chunks"

    raw_dir.mkdir(parents=True, exist_ok=True)
    processed_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)

    downloader = MT5DataDownloader(symbol="XAUUSDz")

    # Step 1: Connect to MT5
    connected = downloader.connect()
    if not connected:
        logger.warning(
            "Could not connect to live MT5 terminal. Checking for existing raw data chunks..."
        )
        # Attempt to assemble existing chunks if available on disk
        chunk_files = list(chunks_dir.glob("*.parquet"))
        if not chunk_files:
            logger.error("No MT5 connection and no offline cached data chunks found!")
            print("\n[ERROR] MetaTrader 5 terminal is not connected and no cached chunks exist.")
            print("        Please start MT5 terminal, log into your account, and rerun this script.")
            sys.exit(1)
        else:
            logger.info(f"Found {len(chunk_files)} offline data chunks on disk. Assembling...")
            chunks_dfs = [pd.read_parquet(f) for f in sorted(chunk_files)]
            master_1m = pd.concat(chunks_dfs, ignore_index=True)
            master_1m.drop_duplicates(subset=["timestamp"], inplace=True)
            master_1m.sort_values("timestamp", inplace=True)
            master_1m.reset_index(drop=True, inplace=True)
    else:
        try:
            # Step 2: Download 5 years of 1m data (2021 to 2026)
            master_1m = downloader.download_history(
                start_year=2021, end_year=2026, chunks_dir=str(chunks_dir)
            )
        finally:
            downloader.disconnect()

    if master_1m.empty:
        logger.error("Failed to acquire 1m historical dataset.")
        sys.exit(1)

    print(f"\n[OK] Acquired {len(master_1m):,} raw 1-minute bars.")
    print(f"     Date Range: {master_1m['timestamp'].min()} to {master_1m['timestamp'].max()}")

    # Step 3: Run Data Gap Audit
    print("\n[AUDIT] Running Data Gap Audit...")
    audit_report = audit_data_gaps(
        master_1m, report_path=str(reports_dir / "data_health_report.json")
    )

    # Step 4: Verify Spread Integrity
    spread_stats = downloader.verify_spread_integrity(master_1m)
    print(f"        Spread Realness: {'Real Broker Spread' if spread_stats['is_real_spread'] else 'Simulated / Constant Spread'}")
    print(f"        Mean Spread: {spread_stats['mean_spread']:.1f} points")

    # Step 5: Add DST-aware Session Flags to 1m data
    print("\n[SESSION] Adding DST-Aware Session Flags (London, NY, Overlap)...")
    master_1m = add_dst_session_flags(master_1m)

    # Save Master 1m dataset
    raw_1m_path = raw_dir / "xau_1m_5y.parquet"
    master_1m.to_parquet(raw_1m_path, index=False)
    file_size_mb = raw_1m_path.stat().st_size / (1024 * 1024)
    print(f"[OK] Saved Master 1m dataset: {raw_1m_path} ({file_size_mb:.2f} MB)")

    # Step 6: Resample to 5m and 15m datasets
    print("\n[RESAMPLE] Resampling 1m -> 5m dataset...")
    df_5m = resample_bars(master_1m, timeframe_minutes=5)
    processed_5m_path = processed_dir / "xau_5m_5y.parquet"
    df_5m.to_parquet(processed_5m_path, index=False)
    print(f"[OK] Saved 5m dataset: {processed_5m_path} ({len(df_5m):,} rows, {processed_5m_path.stat().st_size / (1024 * 1024):.2f} MB)")

    print("\n[RESAMPLE] Resampling 1m -> 15m dataset...")
    df_15m = resample_bars(master_1m, timeframe_minutes=15)
    processed_15m_path = processed_dir / "xau_15m_5y.parquet"
    df_15m.to_parquet(processed_15m_path, index=False)
    print(f"[OK] Saved 15m dataset: {processed_15m_path} ({len(df_15m):,} rows, {processed_15m_path.stat().st_size / (1024 * 1024):.2f} MB)")

    print("\n" + "=" * 70)
    print(" Phase 1 Pipeline Completed Successfully!")
    print("=" * 70)


if __name__ == "__main__":
    main()
