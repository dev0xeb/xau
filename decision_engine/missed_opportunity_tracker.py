#!/usr/bin/env python3
"""
missed_opportunity_tracker.py - NO_TRADE Counterfactual Tracker

Tracks NO_TRADE candidates over subsequent price action to record:
- Would have hit TP ($/oz)
- Would have hit SL ($/oz)
- Counterfactual PnL

Audits decision threshold conservatism to prevent missing profitable edges.
"""

class MissedOpportunityTracker:
    """Tracks counterfactual performance of rejected/filtered candidates."""

    def __init__(self):
        self.tracked_no_trades = []

    def record_no_trade(self, candidate_snapshot: dict, entry_price: float, target_tp: float, target_sl: float):
        """Registers a NO_TRADE decision for counterfactual tracking."""
        record = {
            "candidate_id": candidate_snapshot.get("candidate_id", "NO_TRADE"),
            "direction": candidate_snapshot.get("direction", "BUY"),
            "entry_price": entry_price,
            "target_tp": target_tp,
            "target_sl": target_sl,
            "outcome": "PENDING",
            "counterfactual_pnl_usd": 0.0
        }
        self.tracked_no_trades.append(record)
        return record

    def update_outcomes(self, current_price: float) -> list:
        """Evaluates pending NO_TRADE records against current price."""
        resolved = []
        for r in self.tracked_no_trades:
            if r["outcome"] != "PENDING":
                continue

            direction = r["direction"]
            if direction == "BUY":
                if current_price >= r["target_tp"]:
                    r["outcome"] = "WOULD_HAVE_HIT_TP"
                    r["counterfactual_pnl_usd"] = round(r["target_tp"] - r["entry_price"], 2)
                    resolved.append(r)
                elif current_price <= r["target_sl"]:
                    r["outcome"] = "WOULD_HAVE_HIT_SL"
                    r["counterfactual_pnl_usd"] = round(r["target_sl"] - r["entry_price"], 2)
                    resolved.append(r)
            elif direction == "SELL":
                if current_price <= r["target_tp"]:
                    r["outcome"] = "WOULD_HAVE_HIT_TP"
                    r["counterfactual_pnl_usd"] = round(r["entry_price"] - r["target_tp"], 2)
                    resolved.append(r)
                elif current_price >= r["target_sl"]:
                    r["outcome"] = "WOULD_HAVE_HIT_SL"
                    r["counterfactual_pnl_usd"] = round(r["entry_price"] - r["target_sl"], 2)
                    resolved.append(r)

        return resolved

    def get_summary(self) -> dict:
        """Calculates counterfactual summary for NO_TRADE decisions."""
        total = len(self.tracked_no_trades)
        tps = len([r for r in self.tracked_no_trades if r["outcome"] == "WOULD_HAVE_HIT_TP"])
        sls = len([r for r in self.tracked_no_trades if r["outcome"] == "WOULD_HAVE_HIT_SL"])
        pnl = sum([r["counterfactual_pnl_usd"] for r in self.tracked_no_trades])

        return {
            "total_no_trades_tracked": total,
            "would_have_hit_tp": tps,
            "would_have_hit_sl": sls,
            "net_missed_pnl_usd": round(pnl, 2),
            "conservatism_rating": "OPTIMAL" if tps <= sls else "TOO_CONSERVATIVE"
        }
