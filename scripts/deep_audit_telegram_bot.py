#!/usr/bin/env python3
"""
deep_audit_telegram_bot.py - Deep Telegram Control Console Command Audit

Deeply audits all 14 slash commands:
1. /start, /help, /menu (Interactive Menu)
2. /health (System Health Console)
3. /today (Daily Performance)
4. /snapshot (Market & Conviction Snapshot)
5. /candidate (Latest Candidate Details)
6. /diagnostics (Subsystem Diagnostics)
7. /status (Engine Running State)
8. /pnl (Account & Session PnL)
9. /positions (Active Position Lifecycle)
10. /open (Open Orders & Deals)
11. /history (Trade Lineage History)
12. /risk (Risk Budget & Exposure)
13. /report (Daily Summary Report)
14. /kill & /resume (Admin Security Authorization)
"""

import sys
import os
import json

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from execution_engine.notifications.telegram_bot import TelegramControlBot

COMMANDS_TO_TEST = [
    ("/start", "Control Console"),
    ("/help", "Control Console"),
    ("/menu", "Control Console"),
    ("/health", "System Health Console"),
    ("/today", "Today's Trading Summary"),
    ("/snapshot", "Market & Strategy Snapshot"),
    ("/candidate", "Latest Execution Candidate"),
    ("/diagnostics", "Subsystem Diagnostics"),
    ("/status", "Engine Operational Status"),
    ("/pnl", "Account & Session PnL Breakdown"),
    ("/positions", "Active Position Lifecycle Audit"),
    ("/open", "Open Market Deals"),
    ("/history", "Recent Executed Trade Lineage"),
    ("/risk", "Institutional Risk Guardrails"),
    ("/report", "Latest Daily Report Summary"),
]

def run_deep_telegram_bot_audit() -> dict:
    audit_results = {
        "commands_tested": 0,
        "commands_passed": 0,
        "security_passed": False,
        "live_api_registered": False,
        "all_passed": False
    }

    print("=" * 70)
    print("  DEEP TELEGRAM BOT CONTROL CONSOLE AUDIT — 14 COMMANDS  ")
    print("=" * 70)

    bot = TelegramControlBot()
    admin_id = bot.admin_user_id
    unauthorized_id = "999999999"

    # Test 1: Command Menu Registration
    menu_reg = bot.register_bot_commands()
    audit_results["live_api_registered"] = menu_reg
    print(f"\n[AUDIT 1] Telegram API Command Menu Registration (setMyCommands): {'[PASS]' if menu_reg else '[FAIL]'}")

    # Test 2: Standard Command Responses
    print("\n[AUDIT 2] Auditing 15 Public Slash Commands...")
    for cmd, expected_keyword in COMMANDS_TO_TEST:
        resp = bot.handle_command(cmd, user_id=admin_id)
        passed = expected_keyword.lower() in resp.lower()
        audit_results["commands_tested"] += 1
        if passed:
            audit_results["commands_passed"] += 1
        print(f"  - Command `{cmd}`: {'[PASS]' if passed else '[FAIL]'} (Response Length: {len(resp)} chars)")

    # Test 3: Admin Authorization Security (/kill & /resume)
    print("\n[AUDIT 3] Auditing Admin Authorization Security Guard...")
    kill_unauth = bot.handle_command("/kill", user_id=unauthorized_id)
    resume_unauth = bot.handle_command("/resume", user_id=unauthorized_id)

    unauth_blocked = ("Access Denied" in kill_unauth) and ("Access Denied" in resume_unauth)

    kill_auth = bot.handle_command("/kill", user_id=admin_id)
    auth_kill_passed = "EMERGENCY STOP ACTIVATED" in kill_auth and bot.is_paused is True

    resume_auth = bot.handle_command("/resume", user_id=admin_id)
    auth_resume_passed = "SYSTEM RESUMED" in resume_auth and bot.is_paused is False

    sec_passed = unauth_blocked and auth_kill_passed and auth_resume_passed
    audit_results["security_passed"] = sec_passed
    print(f"  - Unauthorized User Blocked: {'[PASS]' if unauth_blocked else '[FAIL]'}")
    print(f"  - Authorized Admin Control: {'[PASS]' if (auth_kill_passed and auth_resume_passed) else '[FAIL]'}")

    # Overall Verdict
    all_passed = (
        audit_results["commands_passed"] == audit_results["commands_tested"] and
        audit_results["security_passed"] and
        audit_results["live_api_registered"]
    )
    audit_results["all_passed"] = all_passed

    print("\n" + "=" * 70)
    if all_passed:
        print(f"  DEEP TELEGRAM AUDIT VERDICT: 100% PASS ({audit_results['commands_passed']}/{audit_results['commands_tested']} Commands Verified)  ")
    else:
        print(f"  DEEP TELEGRAM AUDIT VERDICT: FAILED ({audit_results['commands_passed']}/{audit_results['commands_tested']} Commands Passed)  ")
    print("=" * 70)

    return audit_results


if __name__ == "__main__":
    run_deep_telegram_bot_audit()
