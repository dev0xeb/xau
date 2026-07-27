#!/usr/bin/env python3
"""
event_store.py - Immutable Append-Only Event Store & Replay Engine

Maintains an immutable event stream for deterministic execution state replay.
Schema per event:
{
  "event_id": str (uuid),
  "timestamp_utc": str (ISO 8601),
  "aggregate_id": str (candidate_id / OMS order_uuid),
  "version": int,
  "event_type": str (CandidateCreated | RiskValidated | OrderQueued | OrderSent | AckReceived | Filled | Closed),
  "payload": dict
}
"""

import os
import json
import uuid
import logging
from datetime import datetime, timezone

logger = logging.getLogger("EventStore")

class EventStore:
    """Immutable persistent event store for execution state transitions."""

    def __init__(self, store_path: str = "execution_engine/queue/event_log.jsonl"):
        self.store_path = store_path
        os.makedirs(os.path.dirname(self.store_path), exist_ok=True)

    def append_event(self, event_type: str, aggregate_id: str, payload: dict, version: int = 1) -> dict:
        """Appends an immutable event record to the store."""
        event_record = {
            "event_id": f"evt-{uuid.uuid4().hex[:12]}",
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "aggregate_id": aggregate_id,
            "version": version,
            "event_type": event_type,
            "payload": payload
        }

        with open(self.store_path, "a") as f:
            f.write(json.dumps(event_record) + "\n")

        return event_record

    def replay_events(self) -> list:
        """
        Replays all events from the append-only log.
        Resilient to malformed/corrupted event records.
        """
        if not os.path.exists(self.store_path):
            return []

        replayed_events = []
        corrupted_count = 0

        with open(self.store_path, "r") as f:
            for line_idx, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                    # Schema check
                    if "event_type" in event and "aggregate_id" in event:
                        replayed_events.append(event)
                    else:
                        corrupted_count += 1
                        logger.warning(f"Corrupted event schema at line {line_idx}: missing event_type or aggregate_id")
                except json.JSONDecodeError as e:
                    corrupted_count += 1
                    logger.warning(f"Corrupted JSON payload at line {line_idx}: {e}")

        if corrupted_count > 0:
            logger.warning(f"Event replay completed: {len(replayed_events)} valid events, {corrupted_count} corrupted events skipped.")

        return replayed_events

    def reconstruct_oms_state(self) -> dict:
        """
        Reconstructs active orders map from replayed events.
        """
        pass  # Helper method used by OMS or recovery
