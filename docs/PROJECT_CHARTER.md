# XAUUSD Scalp Lab — Project Charter

> **Document Status:** Active & Mandated  
> **Phase:** 1 (Research Foundation)  
> **Scope Lock:** Strict & Non-Negotiable  

---

## 1. Executive Mandate

The primary goal of the XAUUSD Aggressive Scalping Research Laboratory is to establish an auditable, reproducible, research-first environment for discovering statistically defensible intraday scalping edges in Gold (`XAUUSD`).

> **Locked Target Benchmark:** Average **10–15 executed XAUUSD intraday trades per day**, with positive expectancy after spread, slippage, and latency over a statistically meaningful validation window (20–30 day rolling sample).

---

## 2. Non-Negotiable Project Scope

### In Scope
* **Instrument:** `XAUUSD` (Spot Gold / USD) exclusively.
* **Style:** Intraday scalping (holding times ranging from seconds to minutes).
* **Execution:** Fully systematic and algorithmic.
* **Workflow:** Hypothesis-driven empirical behavior discovery before any execution logic or strategy optimization is attempted.

### Out of Scope
* Any other asset class or instrument (EURUSD, Forex pairs, US30/NAS100, Crypto, Equities).
* Swing trading, position trading, or overnight holding strategies.
* Discretionary manual trading setups.
* Machine Learning (ML) models unless explicitly introduced in a future phase for a specific, audited statistical task.
* Premature strategy backtesting or optimization before underlying market behavior proof.
* Synthetic data in canonical research pipelines (`data/raw/` or `data/processed/`).

---

## 3. Core Principles

1. **Behavior First, Strategy Second:** A trading strategy is merely an execution wrapper around an underlying statistical anomaly in market behavior. If the anomaly does not exist in real historical data, no strategy optimization can make it profitable.
2. **Real-Data Discipline:** Canonical research pipelines accept real historical tick and M1 data only. Synthetic datasets are strictly prohibited in research datasets and permitted only in isolated test fixtures (`tests/fixtures/`).
3. **Reproducibility & Versioning:** Every experiment, clean dataset, and statistical result must be verifiable via immutable metadata hashes (SHA256) and recorded in the behavior registry.
4. **Friction-Aware Expectations:** All edge evaluation must account for bid-ask spread, slippage, commission, and execution latency. An edge that vanishes under real-world friction is rejected.
5. **Valid Negative Results:** Proving that a hypothesized behavior *does not exist* or *does not survive costs* is a successful research outcome. It prevents capital destruction.

---

## 4. Phase Boundaries

* **Phase 1 (Current):** Research Foundation, Governance, Repository Architecture, Audit Tooling. Zero strategy code built. Broker source selection deferred to Phase 2.
* **Phase 2:** Historical Data Acquisition, Cleaning, UTC Standardization, Quality Auditing, Versioning.
* **Phase 3:** Systematic Behavior Discovery & Statistical Hypothesis Testing.
* **Phase 4:** Edge Validation, Friction Stress Testing, and Out-of-Sample Verification.
* **Phase 5:** Systematic Execution Model & Risk Architecture.

---

## 5. Scope Lock Affirmation

Any expansion of asset scope, change in timeframe horizon, or introduction of non-audited models requires explicit project re-chartering.
