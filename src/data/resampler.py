"""
Multi-Timeframe Resampler, Data Gap Auditor, and DST-Aware Session Tagger.

Provides data integrity auditing for historical 1m bars, timezone-aware
session boundary flagging (London, NY, Overlap) handling DST transitions,
and multi-spread aggregation for 5m and 15m datasets.
"""

from datetime import datetime, timezone
import json
from pathlib import Path
from zoneinfo import ZoneInfo
import logging
import numpy as np
import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def audit_data_gaps(df_1m: pd.DataFrame, report_path: str = "data/reports/data_health_report.json") -> dict:
    """Analyzes timestamp continuity in 1m bar data and categorizes data gaps."""
    if df_1m.empty or "timestamp" not in df_1m.columns:
        logger.error("Dataframe is empty or missing 'timestamp' column.")
        return {}

    df = df_1m.sort_values("timestamp").reset_index(drop=True)
    timestamps = pd.to_datetime(df["timestamp"])
    time_diffs = timestamps.diff()

    # Find gaps larger than 2 minutes
    gap_indices = np.where(time_diffs > pd.Timedelta(minutes=2))[0]

    weekend_closures = []
    rollover_breaks = []
    unexpected_gaps = []

    for idx in gap_indices:
        prev_time = timestamps.iloc[idx - 1]
        curr_time = timestamps.iloc[idx]
        duration_minutes = round((curr_time - prev_time).total_seconds() / 60.0, 1)

        gap_info = {
            "start": prev_time.isoformat(),
            "end": curr_time.isoformat(),
            "duration_minutes": duration_minutes,
        }

        # Check for weekend closure (Friday night to Sunday evening)
        if prev_time.weekday() == 4 and curr_time.weekday() == 6:
            weekend_closures.append(gap_info)
        elif prev_time.weekday() == 4 and curr_time.weekday() == 0:  # Rare Monday open gap
            weekend_closures.append(gap_info)
        # Check for daily 21:00-22:00 UTC market break / rollover
        elif prev_time.hour == 21 and (curr_time.hour == 22 or curr_time.hour == 21) and duration_minutes <= 75:
            rollover_breaks.append(gap_info)
        else:
            unexpected_gaps.append(gap_info)

    audit_report = {
        "summary": {
            "total_bars": len(df),
            "start_time": timestamps.iloc[0].isoformat(),
            "end_time": timestamps.iloc[-1].isoformat(),
            "weekend_closures_count": len(weekend_closures),
            "daily_rollover_breaks_count": len(rollover_breaks),
            "unexpected_gaps_count": len(unexpected_gaps),
            "has_unexpected_gaps": len(unexpected_gaps) > 0,
        },
        "unexpected_gaps": unexpected_gaps[:100],  # Cap log size
    }

    # Save report JSON
    report_file = Path(report_path)
    report_file.parent.mkdir(parents=True, exist_ok=True)
    with open(report_file, "w") as f:
        json.dump(audit_report, f, indent=2)

    logger.info(
        f"Data Health Audit: {len(df):,} total bars | "
        f"Weekend Closures: {len(weekend_closures)} | "
        f"Rollover Breaks: {len(rollover_breaks)} | "
        f"Unexpected Gaps: {len(unexpected_gaps)}"
    )

    return audit_report


def add_dst_session_flags(df: pd.DataFrame) -> pd.DataFrame:
    """Tags each bar with timezone-aware session flags handling DST shifts for London and NY."""
    df_out = df.copy()

    if "timestamp" not in df_out.columns:
        raise ValueError("DataFrame must contain 'timestamp' column.")

    timestamps_utc = pd.to_datetime(df_out["timestamp"], utc=True)

    london_tz = ZoneInfo("Europe/London")
    ny_tz = ZoneInfo("America/New_York")

    # Convert UTC timestamps to local timezone objects efficiently
    london_dt = timestamps_utc.dt.tz_convert(london_tz)
    ny_dt = timestamps_utc.dt.tz_convert(ny_tz)

    # London Session: 08:00 to 16:30 local London time (handles GMT / BST automatically)
    london_minutes = london_dt.dt.hour * 60 + london_dt.dt.minute
    is_london = (london_minutes >= 8 * 60) & (london_minutes <= 16 * 60 + 30)

    # New York Session: 08:00 to 17:00 local New York time (handles EST / EDT automatically)
    ny_minutes = ny_dt.dt.hour * 60 + ny_dt.dt.minute
    is_ny = (ny_minutes >= 8 * 60) & (ny_minutes <= 17 * 60)

    # Overlap Session: Both London and NY are open simultaneously
    is_overlap = is_london & is_ny

    # Active Session: At least one major session is active
    active_session = is_london | is_ny

    df_out["is_london_session"] = is_london
    df_out["is_ny_session"] = is_ny
    df_out["is_overlap_session"] = is_overlap
    df_out["active_session"] = active_session

    return df_out


def resample_bars(df_1m: pd.DataFrame, timeframe_minutes: int) -> pd.DataFrame:
    """
    Resamples 1m base bars to higher timeframe (5m, 15m) preserving multi-spread stats.
    
    Preserves:
    - Open (first), High (max), Low (min), Close (last)
    - Volume (sum)
    - spread_min (min), spread_max (max), spread_mean (mean), spread_close (last)
    """
    if df_1m.empty:
        return pd.DataFrame()

    df = df_1m.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df.set_index("timestamp", inplace=True)

    rule = f"{timeframe_minutes}min"

    # Aggregation mapping
    agg_dict = {
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum",
    }

    if "spread" in df.columns:
        agg_dict["spread"] = ["min", "max", "mean", "last"]

    if "real_volume" in df.columns:
        agg_dict["real_volume"] = "sum"

    resampled = df.resample(rule, closed="left", label="left").agg(agg_dict)

    # Flatten multi-level columns if spread was aggregated
    if "spread" in df.columns:
        new_cols = []
        for col in resampled.columns:
            if isinstance(col, tuple):
                if col[0] == "spread":
                    if col[1] == "last":
                        new_cols.append("spread_close")
                    else:
                        new_cols.append(f"spread_{col[1]}")
                else:
                    new_cols.append(col[0])
            else:
                new_cols.append(col)
        resampled.columns = new_cols

    # Drop bars with no trading activity (NaN open prices resulting from empty time windows)
    resampled.dropna(subset=["open"], inplace=True)
    resampled.reset_index(inplace=True)

    # Add DST session flags to the resampled dataset
    resampled = add_dst_session_flags(resampled)

    logger.info(f"Resampled 1m -> {timeframe_minutes}m dataset: {len(resampled):,} rows")
    return resampled
