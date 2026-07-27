#!/usr/bin/env python3
"""
trade_lifecycle_timeline.py - Granular Stage-by-Stage Trade Lifecycle Timeline

Tracks timestamped stage transitions:
Signal Created -> Decision Approved -> Risk Approved -> OMS Queued -> Broker Sent -> Broker Ack -> Filled -> Managed -> Closed -> Archived

Calculates precise stage latencies for each trade candidate.
"""

import os
import json
import time
from datetime import datetime, timezone

class TradeLifecycleTimeline:
    """Trade lifecycle timeline and latency profiler."""

    def __init__(self, timeline_dir: str = "execution_engine/audit"):
        self.timeline_dir = timeline_dir
        os.makedirs(self.timeline_dir, exist_ok=True)
        self.timeline_file = os.path.join(self.timeline_dir, "trade_timelines.jsonl")
        self.active_timelines = {}  # candidate_id -> timeline dict

    def start_timeline(self, candidate_id: str, trigger_event: str = "Signal Created") -> dict:
        """Initializes a new trade lifecycle timeline."""
        now = time.time()
        timeline = {
            "candidate_id": candidate_id,
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "stages": [
                {"stage": trigger_event, "timestamp_utc": datetime.now(timezone.utc).isoformat(), "time_mono": now}
            ],
            "latencies_ms": {}
        }
        self.active_timelines[candidate_id] = timeline
        return timeline

    def record_stage(self, candidate_id: str, stage_name: str, metadata: dict = None) -> dict:
        """Records a new stage transition for an active candidate."""
        now = time.time()
        if candidate_id not in self.active_timelines:
            self.start_timeline(candidate_id, trigger_event="Candidate Initialized")

        timeline = self.active_timelines[candidate_id]
        stage_entry = {
            "stage": stage_name,
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "time_mono": now,
            "metadata": metadata or {}
        }

        # Calculate latency relative to previous stage
        prev_stage = timeline["stages"][-1]
        stage_latency_ms = round((now - prev_stage["time_mono"]) * 1000.0, 2)
        stage_entry["stage_latency_ms"] = stage_latency_ms

        timeline["stages"].append(stage_entry)

        # Compute key accumulated stage benchmarks
        t_start = timeline["stages"][0]["time_mono"]
        timeline["latencies_ms"]["total_lifecycle_ms"] = round((now - t_start) * 1000.0, 2)

        if stage_name in ["Filled", "Closed", "Archived"]:
            self.flush_timeline(candidate_id)

        return timeline

    def flush_timeline(self, candidate_id: str):
        """Flushes completed timeline record to JSONL store."""
        if candidate_id in self.active_timelines:
            timeline = self.active_timelines.pop(candidate_id)
            # Remove raw monotonic floats prior to serialization
            clean_stages = []
            for s in timeline["stages"]:
                s_copy = s.copy()
                s_copy.pop("time_mono", None)
                clean_stages.append(s_copy)
            timeline["stages"] = clean_stages

            with open(self.timeline_file, "a") as f:
                f.write(json.dumps(timeline) + "\n")
