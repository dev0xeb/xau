import os
import pytest
from scripts.manage_order_recovery import run_order_recovery_reconciliation
from scripts.audit_execution_logs import audit_execution_logs

def test_order_recovery_and_execution_audit(tmp_path):
    audit_dir = str(tmp_path / "audit")
    reports_dir = str(tmp_path / "reports")

    rec_res = run_order_recovery_reconciliation(audit_dir, reports_dir, dry_run=True)
    assert rec_res["disconnection_recovery_status"] == "SUCCESS"
    assert rec_res["reconciliation_accuracy_pct"] == 100.0

    telemetry = audit_execution_logs(audit_dir, reports_dir)
    assert telemetry["acceptance_rate_pct"] >= 95.0
    assert os.path.exists(os.path.join(reports_dir, "execution_bridge_summary.md"))
    assert os.path.exists(os.path.join(reports_dir, "order_recovery_report.md"))
