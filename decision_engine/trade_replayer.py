#!/usr/bin/env python3
"""
trade_replayer.py - Interactive Visual Trade Replayer CLI

Loads decision_snapshots.jsonl and allows step-by-step visual replay:
- Inspect features, behavior scores, portfolio votes, market data, and execution outcomes
- Step forward / backward through trade history
"""

import sys
import os
import json
from decision_engine.decision_replay import DecisionReplayEngine

class InteractiveTradeReplayer:
    """Step-by-step visual trade replayer."""

    def __init__(self, replay_dir: str = "decision_engine/decision_logs"):
        self.replay_engine = DecisionReplayEngine(replay_dir=replay_dir)

    def print_snapshot_summary(self, snapshot: dict, index: int, total: int):
        print("\n" + "=" * 60)
        print(f"  TRADE REPLAY STEP [{index+1} / {total}]  ")
        print("=" * 60)
        print(f"Snapshot ID : {snapshot.get('snapshot_id')}")
        print(f"Timestamp   : {snapshot.get('timestamp_utc')}")
        print(f"Decision    : {snapshot.get('decision')}")

        cand = snapshot.get("candidate_snapshot", {})
        if cand:
            print(f"Candidate ID: {cand.get('candidate_id')} ({cand.get('direction', 'N/A')})")
            print(f"Score       : {cand.get('decision_score')}")
            print(f"Behaviors   : {cand.get('behavior_ids')}")

        scores = snapshot.get("behavior_scores", {})
        if scores:
            print(f"Behavior Scores: {json.dumps(scores)}")

        feats = snapshot.get("features", {})
        if feats:
            print(f"Features    : ATR={feats.get('volatility_atr')}, Mom={feats.get('momentum_velocity')}, Spread=${feats.get('spread_usd')}")

        print("=" * 60)

    def run_replay(self):
        snapshots = self.replay_engine.load_snapshots()
        if not snapshots:
            print("[REPLAY] No decision snapshots found to replay.")
            return

        idx = 0
        total = len(snapshots)

        while 0 <= idx < total:
            self.print_snapshot_summary(snapshots[idx], idx, total)
            cmd = input("[REPLAY COMMAND] (n: next, p: prev, q: quit): ").strip().lower()
            if cmd == "n":
                idx += 1
            elif cmd == "p":
                idx = max(0, idx - 1)
            elif cmd == "q":
                break
            else:
                idx += 1

if __name__ == "__main__":
    replayer = InteractiveTradeReplayer()
    replayer.run_replay()
