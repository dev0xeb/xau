#!/usr/bin/env python3
"""
new_experiment.py - Experiment Template CLI Generator

Instantiates a new standardized research experiment markdown document in experiments/
following the 9-point specification defined in docs/HYPOTHESIS_STANDARD.md.
"""

import os
import argparse
from datetime import datetime, timezone

TEMPLATE = """# Experiment ID: {exp_id} - {title}

* **Author / Agent:** {author}
* **Date Created (UTC):** {date_utc}
* **Target Instrument:** XAUUSD
* **Data Version:** {data_version}

---

## 1. Observation
*Describe the empirical observation or market phenomenon in XAUUSD tick/M1 data that inspired this hypothesis.*

## 2. Research Question
*State the precise quantitative question being evaluated.*

## 3. Null Hypothesis ($H_0$)
*State the null hypothesis ($H_0$: Net return post-cost $\\le 0$).*

## 4. Alternative Hypothesis ($H_1$)
*State the alternative hypothesis ($H_1$: Net return post-cost $> 0$).*

## 5. Required Features & Data Window
*Specify the exact features, bar intervals (Tick/M1), and historical date range required.*

## 6. Statistical Test & Methodology
*Define statistical test method (e.g. bootstrap resampling, Student's t-test) and friction parameters.*

## 7. Acceptance Criteria
*List required mathematical criteria (e.g. p < 0.01, Net Expectancy > +$0.15, N_trades/day >= 10).*

## 8. Empirical Results
*Record test statistics, p-values, sample sizes, distribution plots, and cost-adjusted expectancy.*

## 9. Replication & Verification Status
* **Status:** `PENDING`
* **In-Sample Period:** 
* **Out-of-Sample Period:** 
* **Replication Hash:** 
"""

def create_experiment(exp_id: str, title: str, author: str = "Research Agent", data_version: str = "1.0.0"):
    date_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    filename = f"{exp_id}_{title.lower().replace(' ', '_')}.md"
    target_path = os.path.join("experiments", filename)

    os.makedirs(os.path.dirname(os.path.abspath(target_path)), exist_ok=True)
    content = TEMPLATE.format(
        exp_id=exp_id,
        title=title,
        author=author,
        date_utc=date_utc,
        data_version=data_version
    )

    with open(target_path, "w") as f:
        f.write(content)

    print(f"[SUCCESS] Created new research experiment template: {target_path}")

def main():
    parser = argparse.ArgumentParser(description="Instantiate a new standardized 9-point research experiment template")
    parser.add_argument("--id", type=str, required=True, help="Experiment ID (e.g., EXP_001)")
    parser.add_argument("--title", type=str, required=True, help="Experiment title")
    parser.add_argument("--author", type=str, default="Research Agent", help="Author name")
    parser.add_argument("--version", type=str, default="1.0.0", help="Data version")

    args = parser.parse_args()
    create_experiment(args.id, args.title, args.author, args.version)

if __name__ == "__main__":
    main()
