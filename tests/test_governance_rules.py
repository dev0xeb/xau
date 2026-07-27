import os
import pytest

def test_governance_files_enforce_xauusd_only():
    """Verifies that core governance documents enforce strict XAUUSD-only scope."""
    charter_path = os.path.abspath("docs/PROJECT_CHARTER.md")
    brief_path = os.path.abspath("docs/AI_ASSISTANT_BRIEF.md")
    readme_path = os.path.abspath("README.md")

    for path in [charter_path, brief_path, readme_path]:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()

        assert "XAUUSD" in content, f"{path} must explicitly reference XAUUSD"
        assert "scalping" in content.lower(), f"{path} must explicitly reference scalping"

def test_governance_files_prohibit_synthetic_research_data():
    """Verifies that governance rules prohibit synthetic data in canonical research pipelines."""
    brief_path = os.path.abspath("docs/AI_ASSISTANT_BRIEF.md")
    readme_path = os.path.abspath("README.md")

    for path in [brief_path, readme_path]:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()

        assert "synthetic" in content.lower(), f"{path} must document synthetic data rules"
        assert "fixtures" in content.lower(), f"{path} must restrict synthetic data to test fixtures"
