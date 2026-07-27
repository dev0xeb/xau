#!/usr/bin/env python3
"""
calibration_drift_monitor.py - Confidence Calibration (ECE) Drift Monitor

Monitors Expected Calibration Error (ECE) drift over time against research baseline (0.042):
- ECE < 0.050: NOMINAL_CALIBRATION
- 0.050 <= ECE < 0.080: MODERATE_DRIFT
- ECE >= 0.080: OVERCONFIDENCE_BREACH
"""

import numpy as np

class CalibrationDriftMonitor:
    """Monitors expected calibration error drift across trade batches."""

    def __init__(self, baseline_ece: float = 0.042, max_ece_threshold: float = 0.050):
        self.baseline_ece = baseline_ece
        self.max_ece_threshold = max_ece_threshold

    def calculate_ece(self, confidence_scores: list, outcomes: list, num_bins: int = 5) -> float:
        """
        Calculates Expected Calibration Error (ECE) across confidence bins.
        confidence_scores: list of float [0.0, 1.0]
        outcomes: list of int (1 for win, 0 for loss)
        """
        if not confidence_scores or len(confidence_scores) != len(outcomes):
            return self.baseline_ece

        conf = np.array(confidence_scores)
        acc = np.array(outcomes)

        bins = np.linspace(0.0, 1.0, num_bins + 1)
        ece = 0.0
        total_samples = len(conf)

        for i in range(num_bins):
            in_bin = (conf >= bins[i]) & (conf < bins[i+1])
            prop_in_bin = np.mean(in_bin)

            if prop_in_bin > 0:
                accuracy_in_bin = np.mean(acc[in_bin])
                avg_confidence_in_bin = np.mean(conf[in_bin])
                ece += np.abs(accuracy_in_bin - avg_confidence_in_bin) * prop_in_bin

        return round(float(ece), 4)

    def evaluate_drift(self, confidence_scores: list, outcomes: list) -> dict:
        """Evaluates calibration drift against baseline ECE."""
        current_ece = self.calculate_ece(confidence_scores, outcomes)

        if current_ece >= 0.080:
            status = "OVERCONFIDENCE_BREACH"
            is_valid = False
        elif current_ece >= self.max_ece_threshold:
            status = "MODERATE_DRIFT"
            is_valid = True
        else:
            status = "NOMINAL_CALIBRATION"
            is_valid = True

        return {
            "baseline_ece": self.baseline_ece,
            "current_ece": current_ece,
            "ece_delta": round(current_ece - self.baseline_ece, 4),
            "status": status,
            "is_valid": is_valid
        }
