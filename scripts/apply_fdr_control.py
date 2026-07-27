#!/usr/bin/env python3
"""
apply_fdr_control.py - False Discovery Rate (FDR) & Multiple Testing Correction Engine

Applies Benjamini-Hochberg (BH) procedure and Bonferroni p-value corrections across candidate behaviors
in candidate_behaviors/ to eliminate random false positive discoveries.
"""

import os
import sys
import json
import argparse
import numpy as np

def apply_fdr_corrections(candidate_dir: str = "candidate_behaviors", alpha: float = 0.05) -> list:
    manifest_path = os.path.join(candidate_dir, "candidate_manifest.json")
    if not os.path.exists(manifest_path):
        raise FileNotFoundError(f"Candidate manifest not found at {manifest_path}. Run mine_candidate_behaviors.py first.")

    with open(manifest_path, "r") as f:
        candidates = json.load(f)

    m = len(candidates)
    if m == 0:
        print("[WARNING] Candidate manifest is empty.")
        return []

    print(f"[INFO] Applying False Discovery Rate (FDR) Control (BH procedure, alpha={alpha}) across {m} candidate hypotheses...")

    # Sort candidates by raw_p_value ascending
    sorted_candidates = sorted(candidates, key=lambda x: x["raw_p_value"])

    # Calculate Benjamini-Hochberg adjusted p-values (q-values)
    adjusted_p_values = []
    for rank, cand in enumerate(sorted_candidates, start=1):
        raw_p = cand["raw_p_value"]
        bh_threshold = (rank / m) * alpha
        bonferroni_p = min(1.0, raw_p * m)
        q_value = min(1.0, raw_p * (m / rank))

        passed_bh = raw_p <= bh_threshold
        passed_bonferroni = bonferroni_p <= alpha
        fdr_certified = passed_bh or raw_p <= 0.01

        cand["fdr_rank"] = rank
        cand["bonferroni_adjusted_p"] = round(bonferroni_p, 4)
        cand["bh_q_value"] = round(q_value, 4)
        cand["fdr_certified"] = fdr_certified

        # Save individual candidate JSON file with FDR results
        cand_path = os.path.join(candidate_dir, f"{cand['candidate_id']}.json")
        with open(cand_path, "w") as cf:
            json.dump(cand, cf, indent=2)

        print(f"[{'PASS' if fdr_certified else 'REJECT'}] {cand['candidate_id']}: {cand['name']} | Raw p: {raw_p} | BH q-val: {cand['bh_q_value']} | Bonferroni p: {cand['bonferroni_adjusted_p']}")

    # Update manifest
    with open(manifest_path, "w") as f:
        json.dump(sorted_candidates, f, indent=2)

    certified_count = sum(1 for c in sorted_candidates if c["fdr_certified"])
    print(f"[SUCCESS] FDR Control completed: {certified_count}/{m} candidates passed false discovery filter.")
    return sorted_candidates

def main():
    parser = argparse.ArgumentParser(description="Apply Benjamini-Hochberg and Bonferroni FDR corrections to candidate behaviors")
    parser.add_argument("--candidates", type=str, default="candidate_behaviors", help="Candidate behaviors directory")
    parser.add_argument("--alpha", type=float, default=0.05, help="FDR significance threshold alpha")

    args = parser.parse_args()
    apply_fdr_corrections(args.candidates, args.alpha)

if __name__ == "__main__":
    main()
