# 🏛️ XAU/USD Institutional Backtesting & Analytics Engine Blueprint

This document specifies the architecture and technical requirements for the **Multi-Timeframe Event-Driven Backtesting, Walk-Forward Analysis, and Analytics Engine** for XAU/USD (Gold) scalping strategies.

---

## 🏗️ Architectural Flow (Decoupled Pipeline)

The engine enforces strict separation between **Market Data**, **Strategy Signal Generation**, and **Execution Simulation**.

```
┌─────────────────────────────────────────────────────────────┐
│ 1. Historical Data (1m Base Bars + MT5 Tick Data)          │
└──────────────────────────────┬──────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────┐
│ 2. Data Validation & UTC Normalization Engine               │
└──────────────────────────────┬──────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────┐
│ 3. Timestamp-Safe 1m Event Loop (Strict HTF Close Guard)   │
└──────────────────────────────┬──────────────────────────────┘
                               │ Emits Pure Signals (Buy/Sell)
┌──────────────────────────────▼──────────────────────────────┐
│ 4. Decoupled Strategy Logic Engine                          │
└──────────────────────────────┬──────────────────────────────┘
                               │ Pure Orders (No Execution Assumptions)
┌──────────────────────────────▼──────────────────────────────┐
│ 5. Execution Simulator (Tick-Level Fills, Spreads, Partials)│
└──────────────────────────────┬──────────────────────────────┘
                               │ Raw Trade Fill Logs
┌──────────────────────────────▼──────────────────────────────┐
│ 6. Trade Ledger & Accounting Core                           │
└──────────────────────────────┬──────────────────────────────┘
                               │ Portfolio Equity Curve
┌──────────────────────────────▼──────────────────────────────┐
│ 7. Analytics Engine (Sharpe, Sortino, Drawdown, Sessions)   │
└──────────────────────────────┬──────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────┐
│ 8. Walk-Forward + Enhanced Monte Carlo + Stress Tests       │
└─────────────────────────────────────────────────────────────┘
```

---

## ⚙️ Core Component Specifications

### 1️⃣ Tick-Level Execution Validation Engine
* **Purpose**: Eliminates 1m OHLC bar ambiguity when both Stop Loss (SL) and Take Profit (TP) fall within a single 1-minute bar's High-Low range.
* **Mechanism**:
  * When a trade's SL and TP are both inside a 1m bar range, the simulator loads **MT5 Tick-Level History** for that specific minute to reconstruct the exact price path sequence.
  * If tick data is unavailable for that timestamp, it defaults to the conservative **Pessimistic SL-First Execution Rule**.

---

### 2️⃣ Timestamp-Safe HTF Structure Guard
* **Purpose**: Guarantees zero lookahead bias when accessing 5m and 15m higher timeframe data.
* **Rule Enforced**:
  $$\text{Strategy Execution Timestamp} \ge \text{HTF Bar Close Timestamp}$$
* **Behavior**: A 15m candle spanning `08:00:00 to 08:15:00` is completely invisible to the strategy engine until the `08:15:00` 1m bar event triggers.

---

### 3️⃣ Decoupled Strategy vs. Execution Simulator Engine
* **Strategy Engine**: Pure signal logic. Takes validated market state and emits immutable order intents:
  $$\text{ORDER}(\text{Type}=\text{BUY}, \text{Price}=2350.00, \text{SL}=2342.00, \text{TP1}=2356.00, \text{TP2}=2365.00)$$
* **Execution Simulator**: Responsible for trade lifecycle, spread application, slippage, latency simulation, and partial profit fills.
* **Advantage**: Allows testing the exact same strategy against **Zero Slippage**, **Standard Slippage**, and **Extreme Slippage** models without modifying strategy code.

---

### 4️⃣ Walk-Forward Analysis (WFA) & Out-of-Sample Engine
* **Purpose**: Prevents parameter over-optimization and curve fitting.
* **Rolling Window Protocol**:
  * **In-Sample Train Window**: 12 Months (Parameter discovery & feature optimization).
  * **Out-of-Sample Test Window**: 3 Months (Forward testing without parameter adjustments).
  * Step forward 3 months and repeat across 5 years of historical data (16 Walk-Forward iterations).
* **Walk-Forward Efficiency (WFE)** Target:
  $$\text{WFE} = \frac{\text{Out-of-Sample Annualized Return}}{\text{In-Sample Annualized Return}} \ge 70\%$$

---

### 5️⃣ Multi-Variable Enhanced Monte Carlo Engine (1,000 Runs)
Rather than simple trade sequence shuffling, each Monte Carlo iteration applies randomized multi-variable stress vectors:

| Stress Vector | Randomization Model | Purpose |
| :--- | :--- | :--- |
| **Trade Sequence** | Bootstrap sampling with replacement | Test drawdown depth & streak probability |
| **Variable Slippage** | Heavy-tailed Gaussian distribution ($0.00 – \$0.15$) | Model execution friction spikes |
| **Spread Expansion** | Dynamic spread multiplier ($15 – 50$ points) | Model session boundary spread widening |
| **Execution Latency** | Fill delay simulation ($50\text{ms} – 500\text{ms}$) | Model order routing delays |
| **Missed Trades** | Random 3% trade drop probability | Model network disconnects or rejected orders |

---

### 6️⃣ Explicit Mathematical Risk of Ruin Model
* **Baseline Parameters**:
  * **Starting Equity**: $10,000
  * **Risk per Trade**: 1.0% Account Equity (Dynamic lot sizing)
  * **Ruin Threshold**: **20.0% Maximum Portfolio Drawdown** (Account Breach Level)
* **Pass Condition**:
  $$\text{Empirical Risk of Ruin (at 20\% Drawdown)} < 1.0\% \quad \text{across 1,000 Monte Carlo runs}$$

---

## 📊 Analytics & Performance Metrics Suite

The engine outputs an institutional performance report across 4 quantitative dimensions:

### A. Return & Profitability
* **Total Net Profit ($ and %)**
* **Annualized Return (CAGR)**
* **Profit Factor**: $\frac{\text{Gross Profit}}{\text{Gross Loss}}$ *(Target: $> 1.75$)*
* **Expectancy ($E$) per Trade**:
  $$E = (\text{Win Rate} \times \text{Avg Win}) - (\text{Loss Rate} \times \text{Avg Loss})$$
* **Realized Risk-to-Reward Ratio (Average R:R)**

### B. Drawdown & Risk Profile
* **Max Peak-to-Trough Drawdown ($ and %)** *(Target: $< 8.0\%$)*
* **Max Drawdown Duration** (Time required to recover to equity peak)
* **Max Consecutive Losses Count**
* **Risk of Ruin Probability (%)**

### C. Microstructure & Session Metrics
* **Session Breakdown**: Independent performance for **London Open (07:00-12:00 UTC)**, **NY Open / Overlap (12:00-16:00 UTC)**, and **NY Afternoon (16:00-21:00 UTC)**.
* **Average Holding Time**: Minutes per trade.
* **Long vs. Short Directional Win Rate**.

### D. Risk-Adjusted Ratios
* **Sharpe Ratio**: Excess return per unit of total risk *(Target: $> 1.5$)*
* **Sortino Ratio**: Excess return per unit of downside risk *(Target: $> 2.0$)*
* **Calmar Ratio**: $\frac{\text{CAGR}}{\text{Max Drawdown}}$ *(Target: $> 2.0$)*
