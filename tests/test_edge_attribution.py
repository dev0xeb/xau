import os
import json
import pytest
from scripts.attribute_edge_contributions import attribute_edge_contributions

def test_edge_attribution_engine(tmp_path):
    output_dir = str(tmp_path / "attribution")
    reports_dir = str(tmp_path / "reports")

    attributions = attribute_edge_contributions("behavior_registry", output_dir, reports_dir)

    assert os.path.exists(output_dir)
    assert len(attributions) > 0
    assert os.path.exists(os.path.join(reports_dir, "edge_attribution_report.md"))

    first_attr = attributions[0]
    assert "profit_contribution_pct" in first_attr
    assert first_attr["profit_contribution_pct"] > 0
    assert first_attr["behavior_decay_status"] == "STABLE"
