import os
import json
import pytest
from scripts.generate_features import generate_research_features
from scripts.validate_dataset import validate_dataset

FIXTURE_M1 = "tests/fixtures/sample_m1_fixture.csv"

def test_validate_dataset_certification(tmp_path):
    features_parquet = str(tmp_path / "features.parquet")
    generate_research_features(FIXTURE_M1, features_parquet)

    report_json = str(tmp_path / "quality_report.json")
    cert_md = str(tmp_path / "dataset_certification.md")

    val_res = validate_dataset(features_parquet, report_json, cert_md)

    assert val_res["is_certified"] is True
    assert val_res["quality_score"] == 100.0
    assert os.path.exists(report_json)
    assert os.path.exists(cert_md)

    with open(cert_md, "r", encoding="utf-8") as f:
        cert_text = f.read()

    assert "DATASET CERTIFICATION SEAL" in cert_text
    assert "100.00%" in cert_text
