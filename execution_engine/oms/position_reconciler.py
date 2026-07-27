#!/usr/bin/env python3
"""
position_reconciler.py - Periodic Position Reconciliation & Discrepancy Repair

Runs periodic reconciliation (default: 5-second interval) comparing broker positions
against OMS active filled orders to detect and repair orphan positions or missing trades.
"""

import time
from datetime import datetime, timezone

class PositionReconciler:
    """Periodic broker vs OMS position reconciler."""

    def __init__(self, check_interval_sec: float = 5.0, notifier = None):
        self.check_interval_sec = check_interval_sec
        self.notifier = notifier
        self.last_check_timestamp = 0.0

    def should_check(self) -> bool:
        """Returns True if check_interval_sec has elapsed since last check."""
        return time.time() - self.last_check_timestamp >= self.check_interval_sec

    def reconcile(self, oms, broker_adapter) -> dict:
        """
        Executes reconciliation pass comparing broker positions vs OMS state.
        Repairs discrepancies where necessary.
        """
        self.last_check_timestamp = time.time()
        broker_positions = broker_adapter.get_positions()
        recon_result = oms.reconcile_positions(broker_positions)

        repaired_actions = []

        # 1. Orphan broker position (position exists on broker but not in OMS)
        for orphan_ticket in recon_result.get("unmatched_broker_tickets", []):
            msg = f"Orphan broker position detected: ticket {orphan_ticket}."
            if self.notifier:
                self.notifier.notify("WARNING", "Position Reconciliation Orphan", msg)
            repaired_actions.append({"ticket": orphan_ticket, "action": "FLAGGED_ORPHAN_BROKER"})

        # 2. Missing broker position (order filled in OMS but missing on broker)
        for missing_oms_uuid in recon_result.get("unmatched_oms_uuids", []):
            msg = f"OMS position missing on broker: OMS UUID {missing_oms_uuid}."
            if self.notifier:
                self.notifier.notify("ERROR", "Position Reconciliation Missing", msg)
            # Update OMS state to CLOSED_EXTERNAL
            if missing_oms_uuid in oms.active_orders:
                oms.active_orders[missing_oms_uuid]["oms_state"] = "CLOSED_EXTERNAL"
            repaired_actions.append({"oms_uuid": missing_oms_uuid, "action": "CLOSED_MISSING_OMS"})

        return {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "reconciled": recon_result.get("reconciled", True),
            "matched_count": recon_result.get("matched_count", 0),
            "repaired_actions": repaired_actions
        }
