# 📚 XAU/USD (Gold) Scalping Strategies Blueprint

This document contains the detailed technical specifications for the **5-Strategy Scalping Engine**, algorithmic definitions for **Smart Money Concepts (FVG, BOS, CHoCH/MSS)**, pure **Market Structure & Price Action SL/TP positioning rules** (no trailing stops), and **Risk & Execution Management filters**.

---

## 🔬 Core Smart Money Concepts (SMC) Definitions

```
                  BULLISH CHoCH (Reversal)                      BULLISH FVG (Imbalance)
                  
                      [Break Above]                              Candle 3 ── Low
                 ────── Swing High ──────                                  ░░░ [GAP]
                 /                      \                                  ░░░
         Swing Low                       \                       Candle 2 ── Large Body
                                      New Low                    
                                    (Liquidity Sweep)            Candle 1 ── High
```

### 1. Fair Value Gap (FVG / Imbalance)
* **What it is**: A 3-candle sequence where Candle 1 and Candle 3 do not overlap, leaving an inefficient price gap created by aggressive market orders in Candle 2.
* **Bullish FVG Condition**: $\text{Low}(\text{Candle}_3) > \text{High}(\text{Candle}_1)$
  * **Gap Zone**: $[\text{High}(\text{Candle}_1), \text{Low}(\text{Candle}_3)]$
  * **Consequent Encroachment (CE)**: The 50% midpoint of the FVG zone.
* **Bearish FVG Condition**: $\text{High}(\text{Candle}_3) < \text{Low}(\text{Candle}_1)$
  * **Gap Zone**: $[\text{Low}(\text{Candle}_1), \text{High}(\text{Candle}_3)]$
* **Scalping Entry Rule**: Enter when price retraces into the FVG gap zone on 1m/5m after market structure confirms direction.

---

### 2. Break of Structure (BOS)
* **What it is**: A candle close beyond the most recent major swing point in the **direction of the current trend** (Trend Continuation).
* **Bullish BOS**: Price candle **closes above** the previous valid Swing High during an uptrend.
* **Bearish BOS**: Price candle **closes below** the previous valid Swing Low during a downtrend.
* **Scalping Significance**: Confirms trend continuation. Pullbacks into 1m/5m FVGs following a BOS have a high win rate.

---

### 3. Change of Character (CHoCH) / Market Structure Shift (MSS)
* **What it is**: The **first structural signal of a trend reversal**. It occurs when price breaks the key swing point that was responsible for the last liquidity run.
* **Bullish CHoCH**:
  1. Market is making Lower Highs and Lower Lows (Downtrend).
  2. Price sweeps below a major Swing Low (Liquidity Sweep).
  3. Price aggressively rallies and **closes above the most recent Lower High**.
* **Bearish CHoCH**:
  1. Market is making Higher Highs and Higher Lows (Uptrend).
  2. Price sweeps above a major Swing High (Liquidity Sweep).
  3. Price aggressively drops and **closes below the most recent Higher Low**.
* **Scalping Significance**: Indicates institutional order flow has flipped from sell to buy (or buy to sell).

---

## 🎯 Structural SL & TP Positioning Rules (No Trailing Stops)

Stop Losses (SL) are strictly anchored to **15m/5m Invalidation Swing Structure**, and Take Profits (TP) are anchored to **Liquidity Draw Points, Session Levels, and VWAP Equilibrium**. Trailing SLs are omitted; positions use Breakeven $+ \text{Spread}$ locks upon TP1.

---

### 🔹 Strategy 1: SMC Liquidity Sweep, CHoCH & FVG Reversal
* **Entry Trigger**: 15m Liquidity Sweep $\rightarrow$ 5m CHoCH $\rightarrow$ Retrace into 1m/5m FVG zone.
* **Stop Loss (SL)**: Anchored to the **Major 15m Structural Swing High / Swing Low** $+ \text{Spread}$.
  * *Rationale*: Ignores 1m/5m micro wicks and double-sweeps. Stopped out only if macro 15m market structure breaks.
* **Take Profit 1 (TP1 - Partial 50%)**: Positioned at the **nearest 5m Break of Structure (BOS) level** or **nearest 5m FVG gap fill zone**.
  * *Management*: Move SL to **Breakeven $+ \text{Spread}$** once TP1 is secured.
* **Take Profit 2 (TP2 - Runner 50%)**: Positioned at the **Major Opposing Liquidity Target**: Unswept **Equal Highs/Lows (EQH/EQL)**, **Asian Session High/Low**, or **Opposing 15m Order Block**.

---

### 🔹 Strategy 2: Session Opening Range Breakout (ORB)
* **Entry Trigger**: 15m Opening Range (London 07:00 UTC / NY 12:00 UTC) $\rightarrow$ 1m Breakout with 5m Volatility Expansion.
* **Stop Loss (SL)**: Anchored to the **Opposite 15m Range Boundary** or **Opposite 15m Swing Point** $+ \text{Spread}$.
  * *Rationale*: True expansion retests range edge, but should never collapse through the opposite side of the 15m consolidation.
* **Take Profit 1 (TP1 - Partial 60%)**: Positioned at the **nearest Pre-Market / Session Liquidity Level** (Previous Day High/Low or Pre-Market High/Low).
  * *Management*: Move SL to **Breakeven $+ \text{Spread}$** once TP1 is secured.
* **Take Profit 2 (TP2 - Runner 40%)**: Positioned at the **15m Macro Swing Target** (1.5x–2.0x 15m Opening Range Height extension).

---

### 🔹 Strategy 3: Dynamic Trend-Pullback & Volume Flow
* **Entry Trigger**: 15m Trend (200 EMA + ADX > 25) $\rightarrow$ 5m Pullback into VWAP / 21 EMA zone $\rightarrow$ 1m Engulfing Reversal trigger.
* **Stop Loss (SL)**: Anchored **1.0 pip past the Major 5m/15m Trend Swing Low (for Longs) or Swing High (for Shorts)** $+ \text{Spread}$.
  * *Rationale*: Healthy trends preserve Higher Lows and Higher Highs. Breaking the pullback swing origin invalidates trend structure.
* **Take Profit 1 (TP1 - Partial 50%)**: Positioned at the **Recent 5m/15m Trend Swing High/Low** (retesting the trend extreme).
  * *Management*: Move SL to **Breakeven $+ \text{Spread}$** once TP1 is secured.
* **Take Profit 2 (TP2 - Runner 50%)**: Positioned at the **15m Unmitigated FVG** or **15m Major Liquidity Target** further in the trend direction.

---

### 🔹 Strategy 4: Statistical Mean-Reversion (Bollinger & RSI Divergence)
* **Entry Trigger**: 15m Ranging Filter (ADX < 20) $\rightarrow$ 5m Touch of $2.5\sigma$ Bollinger Band + RSI Divergence $\rightarrow$ 1m Pinbar Rejection.
* **Stop Loss (SL)**: Anchored **beyond the Major 15m Swing High/Low extreme** or outer $3.5\sigma$ volatility boundary $+ \text{Spread}$.
  * *Rationale*: If price pierces major 15m swing levels during mean reversion, the range has broken into a trend expansion.
* **Take Profit (Full Exit 100%)**: Positioned directly at the **Session VWAP (Volume Weighted Average Price)** line.
  * *Rationale*: VWAP represents institutional average price equilibrium.

---

### 🔹 Strategy 5: Microstructure Tick Volume Imbalance (Spike Scalp)
* **Entry Trigger**: 1m Tick Volume $> 2.5\times$ 20-period average + Candle Body Closure $> 85\%$ aligned with 15m bias.
* **Stop Loss (SL)**: Anchored at the **Origin Base of the 1m/5m Imbalance Wave** $+ \text{Spread} + (0.5 \times \text{ATR}_{1\text{m}})$.
  * *Rationale*: Imbalance waves must hold as immediate support/resistance.
* **Take Profit (Full Exit 100%)**: Positioned at the **nearest 5m FVG or 5m Micro Swing Level**.

---

## 🛡️ Risk, Execution & Filter Modules

---

### 1. Dynamic Position Sizing Formula
$$\text{Risk Amount (\$)} = \text{Account Equity} \times \text{Risk \% (e.g., 1.0\%)}$$

$$\text{Lot Size} = \frac{\text{Risk Amount (\$)}}{\text{SL Distance in Points} \times \text{Point Value per Lot}}$$

* **Max Position Cap**: Maximum 1 trade open per strategy, max 2 trades portfolio-wide.
* **Max Daily Drawdown Lockout**: If portfolio drops by **-2.0% in a single day**, all trading halts until the next UTC day.

---

### 2. Real-Time Spread & Slippage Filter
* **Max Allowable Spread**: Reject trade entries if Gold spread exceeds **30 points ($0.30)**.
* **Slippage Penalty**: Apply a **0.2 pip ($0.02) penalty** on all market order fills in backtests.

---

### 3. Economic News Blackout Filter
* **Blackout Window**: **No trade signals generated 10 minutes BEFORE and 10 minutes AFTER** Tier-1 high-impact US economic news releases (CPI, NFP, FOMC, PPI).

---

## 📊 Summary Matrix of All 5 Strategies

| Strategy | SL Structural Anchor | TP1 Target (Partial Exit) | TP2 Target (Runner Exit) | Stop Loss Rule |
| :--- | :--- | :--- | :--- | :--- |
| **1. SMC Sweep & FVG** | Major 15m Swing High/Low | Nearest 5m BOS / 5m FVG | Opposing Liquidity (EQH/EQL / 15m OB) | Lock Breakeven $+ \text{Spread}$ at TP1 |
| **2. Opening Range Breakout** | Opposite 15m Range Edge | Previous Day / Pre-Market High/Low | 1.5x–2.0x Range Height Extension | Lock Breakeven $+ \text{Spread}$ at TP1 |
| **3. Trend Pullback** | Major 5m/15m Trend Swing Point | Recent 5m/15m Trend Extreme | 15m Unmitigated FVG / Liquidity | Lock Breakeven $+ \text{Spread}$ at TP1 |
| **4. Mean Reversion** | Outer 15m Swing / $3.5\sigma$ Band | 100% Exit at Session VWAP Line | N/A (100% Exit at VWAP) | Fixed SL, no trailing |
| **5. Volume Imbalance** | Base of Imbalance Wave | 100% Exit at Nearest 5m FVG / Swing | N/A (100% Exit at 5m FVG) | Fixed SL, no trailing |
