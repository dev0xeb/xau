import os
import pytest
import pandas as pd
from scripts.generate_features import generate_research_features

FIXTURE_M1 = "tests/fixtures/sample_m1_fixture.csv"
FIXTURE_TICK = "tests/fixtures/sample_tick_fixture.csv"

def test_feature_generation_m1(tmp_path):
    output_parquet = str(tmp_path / "test_features_m1.parquet")
    df = generate_research_features(FIXTURE_M1, output_parquet)

    assert os.path.exists(output_parquet)
    assert len(df) == 10
    
    # Check Price Features
    assert "mid" in df.columns
    assert "ret_abs" in df.columns
    assert "ret_log" in df.columns
    
    # Check Volatility Features
    assert "atr_14" in df.columns
    assert "high_low_range" in df.columns
    assert "body_size" in df.columns

    # Check Session & Event Features
    assert "session_label" in df.columns
    assert "event_london_open" in df.columns
    assert "macro_nfp_window" in df.columns

    # Check Objective Market Regimes
    assert "regime_trending" in df.columns
    assert "regime_high_vol" in df.columns

    # Check Execution Cost Baselines
    assert "estimated_spread_usd" in df.columns
    assert "estimated_roundtrip_cost_usd" in df.columns
    assert "estimated_roundtrip_cost_pts" in df.columns

def test_feature_generation_tick(tmp_path):
    output_parquet = str(tmp_path / "test_features_tick.parquet")
    df = generate_research_features(FIXTURE_TICK, output_parquet)

    assert os.path.exists(output_parquet)
    assert "tick_arrival_rate" in df.columns
    assert "quote_update_freq" in df.columns
    assert "micro_volatility" in df.columns
