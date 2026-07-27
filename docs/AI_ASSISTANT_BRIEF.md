# AI Assistant Brief — XAUUSD Scalp Lab Guidelines

> **Mandatory Instructions for AI Assistants**  
> **Applies to:** All AI models, agents, and automated pair-programmers operating in this repository.

---

## 1. Primary Rule: Maintain Scope Discipline

You are operating inside a research lab locked exclusively to **XAUUSD intraday scalping**. Your role is to assist in empirical data science, statistical testing, pipeline engineering, and rigorous validation.

You MUST NOT:
- Suggest or generate code for other instruments (e.g., EURUSD, BTCUSD, NAS100).
- Suggest discretionary or subjective trading ideas.
- Jump directly to building trading bots, entry/exit indicators, or strategy code in early phases.
- Introduce synthetic data generation scripts into `data/raw/` or `data/processed/`.
- Introduce machine learning or complex models unless explicitly requested for a documented phase.
- Perform curve-fitting, parameter sweeps, or optimization prior to establishing statistical proof of an underlying market behavior.

---

## 2. Real-Data Integrity Rule

* **Canonical Research Pipeline:** Only real, historical XAUUSD tick and M1 data may be loaded into or generated for `data/raw/`, `data/processed/`, or `data/metadata/`.
* **Test Fixtures:** Synthetic data is permitted **exclusively** within `tests/fixtures/` for testing script logic. Do not write synthetic data to production/research data directories.
* **Broker Choice:** In Phase 1, do not assume or hardcode a specific broker or format choice. Data source selection is explicitly deferred to Phase 2.

---

## 3. Workflow Protocol

When asked to work on research or code in this repository:

1. **Verify Phase Readiness:** Check which Phase the project is in. In Phase 1, only foundation, governance, data tooling, metadata, and testing scripts may be created.
2. **Enforce the 9-Point Hypothesis Standard:** All market behavior research must follow [`docs/HYPOTHESIS_STANDARD.md`](file:///c:/Users/HP/Documents/xau/docs/HYPOTHESIS_STANDARD.md).
3. **Check for Lookahead Bias:** Ensure all feature calculations use past and current data only relative to the observation timestamp.
4. **Enforce Friction Costs:** When calculating expectancy or statistical returns, always incorporate bid-ask spread and slippage.
5. **Keep `behavior_registry/` Clean:** Do not write strategy execution logic to `behavior_registry/`. It is a placeholder reserved for validated statistical edges in Phase 3+.

---

## 4. Response & Formatting Standards

- Provide complete, runnable code files when modifying or creating scripts.
- Include unit tests in `tests/` for all new scripts.
- Use explicit typing, error handling, logging, and metadata generation in data processing scripts.
- Highlight negative statistical findings clearly rather than trying to optimize weak results.
