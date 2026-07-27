#!/usr/bin/env python3
"""
execution_journal.py - Institutional Structured Execution Journal

Captures rich execution context and attribution metrics:
- Trade lineage: Strategy version, Behavior IDs, Candidate ID, Decision score, Risk tier
- Identifiers: Broker ticket, OMS UUID, Execution UUID
- Execution metrics: Fill price, Spread, Slippage, Execution latency bucket
- Regimes & Buckets: Market regime, Volatility bucket, Spread bucket
- Metadata: Git commit, Config version, Timestamp UTC, Reason closed, Exit trigger, PnL
"""

import os
import json
import subprocess
from datetime import datetime, timezone

def get_git_commit_hash() -> str:
    """Helper to fetch current git commit hash."""
    try:
        cmd = ["git", "rev-parse", "--short", "HEAD"]
        output = subprocess.check_output(cmd, stderr=subprocess.DEVNULL).decode().strip()
        return output
    except Exception:
        return "UNKNOWN_GIT_COMMIT"

class ExecutionJournal:
    """Structured execution journal recorder."""

    def __init__(self, journal_path: str = "execution_engine/audit/execution_journal.jsonl"):
        self.journal_path = journal_path
        os.makedirs(os.path.dirname(self.journal_path), exist_ok=True)
        self.git_commit = get_git_commit_hash()

    def record_trade(
        self,
        candidate_payload: dict,
        oms_record: dict,
        market_regime: str = "NORMAL",
        config_version: str = "1.0.0"
    ) -> dict:
        """Constructs and appends a structured trade record to the journal."""
        spread = oms_record.get("spread_usd", candidate_payload.get("spread_usd", 0.15))
        latency = oms_record.get("execution_latency_ms", 85.0)

        # Categorize buckets
        volatility_bucket = "NORMAL_VOL" if candidate_payload.get("volatility_atr", 1.5) < 2.5 else "HIGH_VOL"
        spread_bucket = "LOW_SPREAD" if spread < 0.20 else ("MED_SPREAD" if spread < 0.35 else "HIGH_SPREAD")
        latency_bucket = "FAST" if latency < 100 else ("MEDIUM" if latency < 250 else "SLOW")

        journal_entry = {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "strategy_version": candidate_payload.get("strategy_version", "STRAT-XAU-001"),
            "behavior_ids": candidate_payload.get("behavior_ids", ["BEH-001"]),
            "candidate_id": oms_record.get("candidate_id"),
            "decision_score": candidate_payload.get("decision_score", 0.85),
            "risk_tier": candidate_payload.get("risk_tier", "TIER_1"),
            "broker_ticket": oms_record.get("broker_ticket", 0),
            "oms_uuid": oms_record.get("oms_uuid"),
            "execution_uuid": oms_record.get("execution_uuid"),
            "fill_price": oms_record.get("broker_fill_price", 0.0),
            "spread": spread,
            "slippage": oms_record.get("slippage_usd", 0.02),
            "reason_closed": oms_record.get("reason_closed", "N/A"),
            "pnl_usd": oms_record.get("pnl_usd", 0.0),
            "exit_trigger": oms_record.get("exit_trigger", "N/A"),
            "git_commit": self.git_commit,
            "config_version": config_version,
            "market_regime": market_regime,
            "volatility_bucket": volatility_bucket,
            "spread_bucket": spread_bucket,
            "latency_bucket": latency_bucket
        }

        with open(self.journal_path, "a") as f:
            f.write(json.dumps(journal_entry) + "\n")

        return journal_entry
