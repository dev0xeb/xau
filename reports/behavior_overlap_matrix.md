# Behavior Overlap & Conflict Matrix — XAUUSD

> **Document Status:** Arbitration Specification  
> **Purpose:** Identify overlapping behaviors to define arbitration priority rules during Phase 4 strategy synthesis.

---

## Interaction & Conflict Table

| Behavior ID | Behavior Name | Conflicts With | Complements | Conflict Arbitration Priority |
|---|---|---|---|---|
| `BEH-001` | Post-Impulse Pullback Reversal | `BEH-002` (Breakout) | `BEH-004` (Micro Momentum) | Priority 1 (High Confidence) |
| `BEH-002` | Session Breakout Velocity | `BEH-001` (Pullback) | `BEH-003` (Compression) | Priority 2 |
| `BEH-003` | Compression Expansion Breakout | None | `BEH-001`, `BEH-002` | Priority 3 |
| `BEH-004` | High Volatility Micro Momentum | None | `BEH-001`, `BEH-003` | Priority 2 |
