#!/usr/bin/env python3
"""
decision_replay.py - Immutable Decision Replay Snapshot Engine

Captures full state snapshots for every decision:
- features
- behavior_scores
- portfolio_votes
- candidate_snapshot
- market_snapshot
- decision ("EXECUTE" or "NO_TRADE")
- execution payload
- trade result

Enables deterministic offline replay of any historical decision.
"""

import os
import json
import uuid
from datetime import datetime, timezone

class DecisionReplayEngine:
    """Snapshot recorder and deterministic decision replayer."""

    def __init__(self, replay_dir: str = "decision_engine/decision_logs"):
        self.replay_dir = replay_dir
        os.makedirs(self.replay_dir, exist_ok=True)
        self.replay_file = os.path.join(self.replay_dir, "decision_snapshots.jsonl")

    def record_snapshot(
        self,
        features: dict,
        behavior_scores: dict,
        portfolio_votes: dict,
        decision: str,
        candidate_snapshot: dict = None,
        market_snapshot: dict = None,
        execution_result: dict = None
    ) -> dict:
        """Records an immutable snapshot of a decision evaluation."""
        snapshot = {
            "snapshot_id": f"snap-{uuid.uuid4().hex[:10]}",
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "decision": decision,  # "EXECUTE" or "NO_TRADE"
            "features": features,
            "behavior_scores": behavior_scores,
            "portfolio_votes": portfolio_votes,
            "candidate_snapshot": candidate_snapshot or {},
            "market_snapshot": market_snapshot or {},
            "execution_result": execution_result or {}
        }

        with open(self.replay_file, "a") as f:
            f.write(json.dumps(snapshot) + "\n")

        return snapshot

    def load_snapshots(self) -> list:
        """Loads all historical decision snapshots for offline replay."""
        if not os.path.exists(self.replay_file):
            return []

        snapshots = []
        with open(self.replay_file, "r") as f:
            for line in f:
                if line.strip():
                    try:
                        snapshots.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
        return snapshots

    def replay_decision_by_id(self, snapshot_id: str) -> dict:
        """Finds and returns snapshot matching snapshot_id."""
        for snap in self.load_snapshots():
            if snap.get("snapshot_id") == snapshot_id:
                return snap
        return None
