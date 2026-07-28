#!/usr/bin/env python3
"""
oms.py - Decoupled Order Management System (OMS) with Optimistic Locking & Event Sourcing

Enforces:
1. Optimistic Locking (order_version) to safely prevent concurrent update race conditions.
2. Pre-Broker Validation Guardrails (OrderValidator).
3. Immutable Event Sourcing (EventStore) & Audit Journaling.
4. Error-Specific Smart Retry Policies & Dead-Letter Queue (DLQ) routing.
5. Periodic Background Position Reconciliation.
"""

import os
import sys
import json
import uuid
import time
from datetime import datetime, timezone

from execution_engine.errors import ValidationError, BrokerRejectError
from execution_engine.oms.order_validator import OrderValidator
from execution_engine.queue.event_store import EventStore
from execution_engine.queue.dead_letter_queue import DeadLetterQueue
from execution_engine.audit.execution_journal import ExecutionJournal
from execution_engine.notifications.notifier import ConsoleNotifier

class OrderManagementSystem:

    def __init__(
        self,
        oms_dir: str = "execution_engine/oms",
        audit_dir: str = "execution_engine/audit",
        validator: OrderValidator = None,
        event_store: EventStore = None,
        dlq: DeadLetterQueue = None,
        journal: ExecutionJournal = None,
        notifier = None
    ):
        self.oms_dir = oms_dir
        self.audit_dir = audit_dir
        os.makedirs(self.oms_dir, exist_ok=True)
        os.makedirs(self.audit_dir, exist_ok=True)

        self.validator = validator or OrderValidator()
        self.event_store = event_store or EventStore()
        self.dlq = dlq or DeadLetterQueue()
        self.journal = journal or ExecutionJournal()
        self.notifier = notifier or ConsoleNotifier()

        self.seen_uuids = set()
        self.active_orders = {}  # oms_uuid -> order_record dict

    def process_candidate(
        self,
        candidate_payload: dict,
        broker_adapter,
        current_portfolio_exposure_lots: float = 0.0,
        current_account_equity_usd: float = 10000.0,
        current_spread_usd: float = 0.15,
        is_market_session_open: bool = True
    ) -> dict:
        cand_id = candidate_payload.get("candidate_id", f"CAND-{uuid.uuid4().hex[:8]}")
        exec_uuid = candidate_payload.get("execution_uuid", uuid.uuid4().hex)
        candidate_payload["execution_uuid"] = exec_uuid

        # 1. Event Log: CandidateCreated
        self.event_store.append_event("CandidateCreated", cand_id, candidate_payload)

        # 2. Pre-Broker Validation Check
        try:
            self.validator.validate_candidate(
                candidate_payload=candidate_payload,
                current_portfolio_exposure_lots=current_portfolio_exposure_lots,
                current_account_equity_usd=current_account_equity_usd,
                current_spread_usd=current_spread_usd,
                is_market_session_open=is_market_session_open
            )
            self.event_store.append_event("RiskValidated", cand_id, {"status": "PASSED"})
        except ValidationError as val_err:
            self.notifier.notify("WARNING", "Order Validation Failure", str(val_err), val_err.context)
            # Route directly to DLQ
            self.dlq.route_to_dlq(
                candidate_payload=candidate_payload,
                retry_reason="VALIDATION_FAILURE",
                retry_count=0,
                final_failure="PRE_BROKER_VALIDATION_FAILED",
                root_cause=str(val_err)
            )
            return {
                "candidate_id": cand_id,
                "execution_uuid": exec_uuid,
                "status": "REJECTED_DUPLICATE" if "Duplicate" in str(val_err) else "REJECTED_VALIDATION",
                "oms_state": "REJECTED_VALIDATION",
                "reason": str(val_err)
            }

        # 3. Create OMS Record with Optimistic Locking (order_version = 1)
        order_uuid = str(uuid.uuid4())
        oms_uuid = str(uuid.uuid4())

        oms_record = {
            "candidate_id": cand_id,
            "execution_uuid": exec_uuid,
            "order_uuid": order_uuid,
            "oms_uuid": oms_uuid,
            "order_version": 1,
            "oms_state": "QUEUED",
            "direction": candidate_payload.get("direction", "BUY"),
            "volume_lots": candidate_payload.get("volume_lots", candidate_payload.get("adaptive_risk_pct", 1.0) * 0.1),
            "sl": candidate_payload.get("sl", 0.0),
            "tp": candidate_payload.get("tp", 0.0),
            "created_at_utc": datetime.now(timezone.utc).isoformat()
        }

        self.active_orders[oms_uuid] = oms_record
        self.event_store.append_event("OrderQueued", cand_id, oms_record, version=1)

        # 4. State Update -> SENT (optimistic lock increment to version 2)
        oms_record["oms_state"] = "SENT"
        oms_record["order_version"] += 1
        self.event_store.append_event("OrderSent", cand_id, oms_record, version=oms_record["order_version"])

        start_time = time.time()
        max_retries = 3
        retry_count = 0
        fill_res = None
        last_error_reason = ""

        # 5. Broker Execution Loop with Error-Specific Smart Retries
        while retry_count < max_retries:
            fill_res = broker_adapter.place_order(oms_record)
            retcode = fill_res.get("retcode", 0)

            if fill_res.get("success"):
                break
            elif retcode in [10004, 10013]:  # REQUOTE / TRADE_CONTEXT_BUSY
                retry_count += 1
                last_error_reason = f"Broker retcode {retcode}: Requote/Busy"
                time.sleep(0.05 * (2 ** retry_count))
            elif retcode in [10018, 10019]:  # MARKET_CLOSED / NO_MONEY
                last_error_reason = f"Fatal broker retcode {retcode}: {fill_res.get('comment')}"
                break
            else:
                retry_count += 1
                last_error_reason = f"Broker retcode {retcode}: {fill_res.get('comment')}"
                time.sleep(0.05)

        execution_latency_ms = round((time.time() - start_time) * 1000.0, 1)
        oms_record["execution_latency_ms"] = execution_latency_ms

        # 6. Final State Evaluation & Optimistic Version Increment
        if fill_res and fill_res.get("success"):
            oms_record["order_version"] += 1
            oms_record["oms_state"] = "FILLED"
            oms_record["broker_ticket"] = fill_res.get("ticket", 1001)
            oms_record["broker_fill_price"] = fill_res.get("fill_price", 2350.50)

            self.event_store.append_event("AckReceived", cand_id, {"ticket": oms_record["broker_ticket"]}, version=oms_record["order_version"])
            self.event_store.append_event("Filled", cand_id, oms_record, version=oms_record["order_version"])

            # Journal execution
            self.journal.record_trade(candidate_payload, oms_record)

            # Record in TradeJournalDatabase for 100% isolated local trade tracking
            try:
                from execution_engine.audit.trade_journal_db import TradeJournalDatabase
                tj_db = TradeJournalDatabase()
                trade_record = {
                    "trade_id": f"TR-{cand_id}",
                    "candidate_id": cand_id,
                    "symbol": oms_record.get("symbol", "XAUUSDz"),
                    "direction": oms_record.get("direction", "BUY"),
                    "volume_lots": oms_record.get("volume_lots", 0.1),
                    "entry_price": oms_record.get("broker_fill_price", 2350.50),
                    "sl": candidate_payload.get("sl", 0.0),
                    "tp": candidate_payload.get("tp", 0.0),
                    "decision_score": candidate_payload.get("decision_score", 0.85),
                    "spread_usd": candidate_payload.get("spread_usd", 0.04),
                    "atr": candidate_payload.get("volatility_atr", 1.2),
                    "timestamp_utc": oms_record.get("created_at_utc")
                }
                tj_db.record_journal_trade(trade_record)
            except Exception as tj_err:
                print(f"[OMS JOURNAL ERROR] {tj_err}")
        else:
            oms_record["order_version"] += 1
            oms_record["oms_state"] = "REJECTED_BROKER"
            oms_record["broker_ticket"] = 0
            self.event_store.append_event("Closed", cand_id, {"reason": last_error_reason}, version=oms_record["order_version"])

            # Route failed candidate to DLQ
            self.dlq.route_to_dlq(
                candidate_payload=candidate_payload,
                retry_reason="BROKER_REJECT",
                retry_count=retry_count,
                final_failure="MAX_RETRIES_EXCEEDED_OR_FATAL_REJECT",
                root_cause=last_error_reason,
                broker_response=fill_res
            )

        # Write immutable audit log
        audit_file = os.path.join(self.audit_dir, f"audit_{cand_id}.json")
        with open(audit_file, "w") as f:
            json.dump(oms_record, f, indent=2)

        return oms_record

    def update_order_state(self, oms_uuid: str, target_state: str, expected_version: int) -> dict:
        """
        Updates order state enforcing optimistic locking (order_version).
        Raises ValueError if version mismatch occurs.
        """
        if oms_uuid not in self.active_orders:
            raise KeyError(f"Order {oms_uuid} not found in active OMS state.")

        order = self.active_orders[oms_uuid]
        if order["order_version"] != expected_version:
            raise ValueError(
                f"Optimistic lock violation: Order {oms_uuid} is at version {order['order_version']}, "
                f"expected version {expected_version}."
            )

        order["order_version"] += 1
        order["oms_state"] = target_state
        return order

    def reconcile_positions(self, broker_positions: list) -> dict:
        """
        Periodic position reconciliation comparing MT5 broker position list vs active OMS filled positions.
        """
        broker_tickets = {p.get("ticket") for p in broker_positions if "ticket" in p}
        oms_filled = {
            oms_uuid: order
            for oms_uuid, order in self.active_orders.items()
            if order.get("oms_state") == "FILLED"
        }

        matched = []
        unmatched_oms = []
        unmatched_broker = []

        for oms_uuid, order in oms_filled.items():
            ticket = order.get("broker_ticket")
            if ticket in broker_tickets:
                matched.append(ticket)
            else:
                unmatched_oms.append(oms_uuid)

        for ticket in broker_tickets:
            if not any(o.get("broker_ticket") == ticket for o in oms_filled.values()):
                unmatched_broker.append(ticket)

        is_reconciled = len(unmatched_oms) == 0 and len(unmatched_broker) == 0

        if not is_reconciled:
            self.notifier.notify(
                "WARNING",
                "Periodic Position Reconciliation Discrepancy",
                f"Unmatched OMS: {len(unmatched_oms)}, Unmatched Broker: {len(unmatched_broker)}"
            )

        return {
            "reconciled": is_reconciled,
            "matched_count": len(matched),
            "unmatched_oms_uuids": unmatched_oms,
            "unmatched_broker_tickets": unmatched_broker
        }
