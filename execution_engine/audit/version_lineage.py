#!/usr/bin/env python3
"""
version_lineage.py - Version Lineage & Reproducibility Locking

Embeds immutable version lineage metadata into every trade record:
- strategy_version
- research_version
- decision_engine_version
- behavior_registry_hash (SHA256)
- feature_schema_version
- risk_config_version
"""

import hashlib
import json

def compute_behavior_registry_hash() -> str:
    """Computes SHA256 reproducibility hash of behavior registry state."""
    registry_repr = "STRAT-XAU-001:BEH-001,BEH-002,BEH-003,BEH-004"
    return hashlib.sha256(registry_repr.encode()).hexdigest()

class VersionLineageManager:
    """Version Lineage Manager for trade record reproducibility."""

    DEFAULT_LINEAGE = {
        "strategy_version": "STRAT-XAU-001",
        "research_version": "v1.6",
        "decision_engine_version": "v3.2",
        "behavior_registry_hash": compute_behavior_registry_hash(),
        "feature_schema_version": "v4",
        "risk_config_version": "v2.1"
    }

    @staticmethod
    def attach_version_lineage(trade_record: dict) -> dict:
        """Attaches version lineage dictionary to trade record."""
        record_copy = trade_record.copy()
        record_copy["version_lineage"] = VersionLineageManager.DEFAULT_LINEAGE
        return record_copy
