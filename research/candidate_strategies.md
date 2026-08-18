# Deterministic Candidate Strategies Specification

## Candidate Strategy 1: Session Liquidity Sweep & Reversal Scalper
* **Market Regime**: Mean-Reverting / Range Sweep
* **Preferred Session**: London/NY Overlap (12:20 – 15:30 UTC)
* **Deterministic Rules**:
  ```text
  IF 12:20 <= time <= 15:30 UTC
  AND 5m low < prior 15m low (Bullish Sweep)
  AND 5m close > 5m open (Bullish Displacement)
  THEN BUY at Close + Spread ($0.20)
  SL = 5m Low - $1.20
  TP = Opposing Daily High / $10.00 Expansion
  ```

---

## Candidate Strategy 2: London/NY Overlap 15m ORB Breakout Engine
* **Market Regime**: High-Volatility Breakout
* **Preferred Session**: London/NY Overlap (12:20 UTC)
* **Deterministic Rules**:
  ```text
  IF time == 12:20 UTC
  AND 5m close > 15m Opening Range High (12:00-12:15) + $0.50
  THEN BUY at Close + Spread ($0.20)
  SL = 5m Low - $1.20
  TP = Entry + 1.5 * ORB Range
  ```

---

## Candidate Strategy 3: Daily Session Open Bias Trend Follower
* **Market Regime**: Strong Trend Expansion Day
* **Preferred Session**: London/NY Overlap (12:20 – 15:30 UTC)
* **Deterministic Rules**:
  ```text
  IF 12:20 <= time <= 15:30 UTC
  AND Current Price > 00:00 UTC Daily Open
  AND 5m low < prior 15m low AND 5m close > 5m open
  THEN BUY at Close + Spread ($0.20)
  SL = 5m Low - $1.20
  TP = Full Daily High Extreme
  ```

---

## Candidate Strategy 4: 5m Displacement Candle Retrace Engine
* **Market Regime**: Post-Displacement Impulse
* **Preferred Session**: 12:00 – 16:00 UTC
* **Deterministic Rules**:
  ```text
  IF 12:00 <= time <= 16:00 UTC
  AND 5m Candle Body >= $3.00
  AND 5m close > 5m open
  THEN BUY on 50% Retrace into FVG Gap
  SL = 5m Low - $1.20
  TP = 2.0 * Displacement Length
  ```

---

## Candidate Strategy 5: Adaptive Market State Hybrid Engine
* **Market Regime**: Adaptive (Trend & Range Dual State)
* **Preferred Session**: London/NY Overlap (12:20 – 15:30 UTC)
* **Deterministic Rules**:
  ```text
  IF 12:20 <= time <= 15:30 UTC
  IF Session Expansion (|Price - Daily Open|) >= $12.00:
      Route Signal -> Strategy 3 (Daily Open Bias Trend Follower)
  ELSE:
      Route Signal -> Strategy 1 (Session Liquidity Sweep & Reversal)
  ```
