import os
import json
import pytest
import pandas as pd
from scripts.clean_normalize_data import clean_and_normalize
from scripts.audit_data_quality import audit_dataset
from scripts.generate_catalog import generate_catalog_entry

FIXTURE_M1 = "tests/fixtures/sample_m1_fixture.csv"
FIXTURE_TICK = "tests/fixtures/sample_tick_fixture.csv"

def test_clean_and_normalize_m1_fixture(tmp_path):
    output_parquet = str(tmp_path / "test_clean_m1.parquet")
    df = clean_and_normalize(FIXTURE_M1, output_parquet)

    assert os.path.exists(output_parquet)
    assert len(df) == 10
    assert "timestamp" in df.columns
    assert "mid" in df.columns
    assert str(df["timestamp"].dtype).startswith("datetime64")

def test_audit_data_quality(tmp_path):
    output_parquet = str(tmp_path / "test_clean_m1.parquet")
    clean_and_normalize(FIXTURE_M1, output_parquet)

    report_path = str(tmp_path / "audit_report.json")
    audit_res = audit_dataset(output_parquet, report_path)

    assert audit_res["passed_audit"] is True
    assert audit_res["quality_score"] == 100.0
    assert os.path.exists(report_path)

def test_generate_catalog(tmp_path):
    output_parquet = str(tmp_path / "test_clean_m1.parquet")
    clean_and_normalize(FIXTURE_M1, output_parquet)

    catalog = generate_catalog_entry(output_parquet, dataset_id="TEST_XAUUSD_M1", version="1.0.0", granularity="M1")

    assert catalog["instrument"] == "XAUUSD"
    assert catalog["dataset_id"] == "TEST_XAUUSD_M1"
    assert len(catalog["sha256_checksum"]) == 64
