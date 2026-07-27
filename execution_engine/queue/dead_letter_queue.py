#!/usr/bin/env python3
"""
dead_letter_queue.py - Persistent Dead-Letter Queue (DLQ)

Stores execution candidates that failed repeatedly or suffered fatal pre-broker validation errors.
Preserves rich diagnostic context for post-mortem debugging and manual operator inspection.
"""

import os
import json
import uuid
from datetime import datetime, timezone

class DeadLetterQueue:
    """Persistent storage for unexecutable or failed trade candidates."""

    def __init__(self, dlq_path: str = "execution_engine/queue/dlq_candidates.jsonl"):
        self.dlq_path = dlq_path
        os.makedirs(os.path.dirname(self.dlq_path), exist_ok=True)

    def route_to_dlq(
        self,
        candidate_payload: dict,
        retry_reason: str,
        retry_count: int,
        final_failure: str,
        root_cause: str,
        broker_response: dict = None
    ) -> dict:
        """Enqueues a candidate into the Dead-Letter Queue with full context."""
        dlq_entry = {
            "dlq_id": f"dlq-{uuid.uuid4().hex[:8]}",
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "candidate_id": candidate_payload.get("candidate_id", "UNKNOWN_CANDIDATE"),
            "candidate_snapshot": candidate_payload,
            "retry_reason": retry_reason,
            "retry_count": retry_count,
            "final_failure": final_failure,
            "root_cause": root_cause,
            "broker_response": broker_response or {}
        }

        with open(self.dlq_path, "a") as f:
            f.write(json.dumps(dlq_entry) + "\n")

        print(f"[DLQ ROUTED] Candidate {dlq_entry['candidate_id']} routed to DLQ. Cause: {root_cause}")
        return dlq_entry

    def list_dlq_candidates(self) -> list:
        """Retrieves all candidates currently in the DLQ."""
        if not os.path.exists(self.dlq_path):
            return []

        entries = []
        with open(self.dlq_path, "r") as f:
            for line in f:
                if line.strip():
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
        return entries
