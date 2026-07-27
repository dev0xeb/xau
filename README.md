# XAUUSD Aggressive Scalping Research Laboratory

> **Phase 1: Research Foundation**

A disciplined, reproducible, XAUUSD-only research laboratory designed to discover and validate high-frequency intraday scalping edges.

> **Target Benchmark:** Average **10–15 executed XAUUSD intraday trades per day**, with positive expectancy after spread, slippage, and latency over a statistically meaningful validation window (20–30 day rolling sample).

---

## Core Philosophy

This repository is an **edge discovery laboratory**, not a trading bot factory.

> **Guiding Rule:** Never optimize a strategy until the underlying market behavior has been demonstrated to exist statistically.

"Aggressive" in this laboratory means:
* High frequency (multiple opportunities per day)
* Short holding periods
* Fully systematic execution
* Positive expectancy post-cost across market regimes

It **never** means overtrading, discretionary gambling, looseness in statistical testing, or curve-fitting.

---

## Non-Negotiable Rules

1. **Instrument Scope:** `XAUUSD` (Gold vs USD) only.
2. **Style Scope:** Intraday scalping only.
3. **Execution Mode:** Fully systematic only.
4. **Data Discipline:** Real historical tick and M1 data only for canonical research pipelines (`data/raw/` and `data/processed/`). Synthetic data is strictly prohibited in research datasets and restricted solely to isolated test fixtures in `tests/fixtures/`.
5. **No Strategy Logic in Phase 1:** `behavior_registry/` is a placeholder for validated edges in future phases. No execution logic, entry rules, or strategies are built until statistical proof is documented.
6. **No Lookahead / No Data Drift:** Strict separation of in-sample hypothesis testing and out-of-sample validation.

---

## Directory Structure

```text
xau-scalp-lab/
├── data/
│   ├── raw/          # Immutable raw historical XAUUSD tick & M1 data
│   ├── processed/    # Cleaned, UTC-normalized, audited parquet/csv datasets
│   └── metadata/     # Version tags, SHA256 checksums, and dataset catalog manifests
├── research/         # Exploratory analysis, statistical notebooks, and notes
├── experiments/      # Standardized 9-point research hypotheses & audit records
├── behavior_registry/# Placeholder for statistically validated market behaviors (Phase 3+)
├── reports/          # Audit summaries, distribution reports, performance benchmarks
├── docs/             # Foundational governance, specs, and charter documentation
├── tests/            # Automated verification tests & test fixtures
│   └── fixtures/     # Test sample datasets (isolated unit test fixtures only)
├── scripts/          # CLI data ingestion, cleaning, auditing, and cataloging utilities
└── notebooks/        # Jupyter/Python notebooks for statistical exploration
```

---

## Foundational Documentation

* [`docs/PROJECT_CHARTER.md`](file:///c:/Users/HP/Documents/xau/docs/PROJECT_CHARTER.md) — Scope lock & core research mandates.
* [`docs/AI_ASSISTANT_BRIEF.md`](file:///c:/Users/HP/Documents/xau/docs/AI_ASSISTANT_BRIEF.md) — Instructions for AI agents working in this repository.
* [`docs/DATA_COLLECTION_SPEC.md`](file:///c:/Users/HP/Documents/xau/docs/DATA_COLLECTION_SPEC.md) — Data standards for real tick & M1 data.
* [`docs/DATA_QUALITY_AUDIT_SPEC.md`](file:///c:/Users/HP/Documents/xau/docs/DATA_QUALITY_AUDIT_SPEC.md) — Quantitative quality gates & audit rules.
* [`docs/DATA_CATALOG_SCHEMA.md`](file:///c:/Users/HP/Documents/xau/docs/DATA_CATALOG_SCHEMA.md) — Metadata schema standard.
* [`docs/SUCCESS_METRICS.md`](file:///c:/Users/HP/Documents/xau/docs/SUCCESS_METRICS.md) — Mathematical benchmarks for edge evaluation.
* [`docs/HYPOTHESIS_STANDARD.md`](file:///c:/Users/HP/Documents/xau/docs/HYPOTHESIS_STANDARD.md) — 9-point experiment template.

---

## Getting Started & Verification

### Run Automated Tests
```powershell
python -m pytest tests/ -v
```

### Clean & Audit Data
```powershell
python scripts/clean_normalize_data.py --input tests/fixtures/sample_m1_fixture.csv --output data/processed/sample_clean.parquet
python scripts/audit_data_quality.py --input data/processed/sample_clean.parquet
python scripts/generate_catalog.py --input data/processed/sample_clean.parquet
```

### Create a New Research Experiment
```powershell
python scripts/new_experiment.py --id EXP_001 --title "London_Open_Vol_Spike_Distribution"
```
