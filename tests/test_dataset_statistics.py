import os
import pytest
from scripts.generate_features import generate_research_features
from scripts.dataset_statistics import generate_reports

FIXTURE_M1 = "tests/fixtures/sample_m1_fixture.csv"

def test_dataset_statistics_reports_generation(tmp_path):
    features_parquet = str(tmp_path / "features.parquet")
    generate_research_features(FIXTURE_M1, features_parquet)

    reports_dir = str(tmp_path / "reports")
    generate_reports(features_parquet, reports_dir)

    expected_reports = [
        "dataset_summary.md",
        "spread_analysis.md",
        "session_statistics.md",
        "volatility_report.md",
        "feature_catalog.md",
        "opportunity_density.md"
    ]

    for rep in expected_reports:
        rep_path = os.path.join(reports_dir, rep)
        assert os.path.exists(rep_path), f"Missing report: {rep}"
        assert os.path.getsize(rep_path) > 50, f"Report empty: {rep}"
