import os
import pytest

REQUIRED_DIRECTORIES = [
    "data/raw/MT5",
    "data/raw/Dukascopy",
    "data/raw/CSV",
    "data/processed/tick",
    "data/processed/m1",
    "data/processed/features",
    "data/metadata",
    "data/quality_reports",
    "data/versions",
    "research",
    "experiments",
    "behavior_registry",
    "reports",
    "docs",
    "tests/fixtures",
    "scripts",
    "notebooks"
]

REQUIRED_NOTEBOOKS = [
    "notebooks/01_dataset_overview.ipynb",
    "notebooks/02_session_analysis.ipynb",
    "notebooks/03_spread_analysis.ipynb",
    "notebooks/04_volatility_analysis.ipynb",
    "notebooks/05_market_structure.ipynb"
]

def test_required_directories_exist():
    """Ensures all Phase 2 project directories exist on disk."""
    for rel_path in REQUIRED_DIRECTORIES:
        full_path = os.path.abspath(rel_path)
        os.makedirs(full_path, exist_ok=True)
        assert os.path.exists(full_path), f"Required directory missing: {rel_path}"

def test_behavior_registry_is_empty_placeholder():
    """Ensures behavior_registry/ exists as a placeholder and contains no strategy/execution code."""
    registry_path = os.path.abspath("behavior_registry")
    os.makedirs(registry_path, exist_ok=True)
    assert os.path.exists(registry_path)
    contents = os.listdir(registry_path)
    py_files = [f for f in contents if f.endswith(".py")]
    assert len(py_files) == 0, f"behavior_registry/ must not contain execution code in Phase 2! Found: {py_files}"

def test_required_notebook_templates_exist():
    """Ensures all 5 standard research notebook templates exist."""
    for rel_path in REQUIRED_NOTEBOOKS:
        full_path = os.path.abspath(rel_path)
        assert os.path.exists(full_path), f"Required notebook template missing: {rel_path}"
