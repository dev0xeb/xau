# Data Collection Specification — XAUUSD Scalp Lab

> **Document Status:** Standard Specification  
> **Target Asset:** XAUUSD (Gold / US Dollar)  
> **Required Horizons:** Tick Data & M1 (1-Minute) Candles  

---

## 1. Overview

Aggressive intraday scalping requires ultra-fine price granularity and verifiable data integrity. This specification defines the structural requirements for acquiring, ingesting, and storing raw and processed XAUUSD tick and M1 candle datasets.

---

## 2. Granularity & Schema Requirements

### 2.1 Tick Data Schema (`data/raw/` & `data/processed/`)
Tick data represents individual price updates broadcast by the liquidity provider or broker.

| Field Name | Type | Description | Unit / Format |
|---|---|---|---|
| `timestamp` | Datetime (UTC) | Microsecond-precision UTC timestamp | `YYYY-MM-DD HH:MM:SS.ffffff` |
| `bid` | Float64 | Highest price a buyer is willing to pay | USD per Troy Ounce (e.g. `2350.45`) |
| `ask` | Float64 | Lowest price a seller is willing to accept | USD per Troy Ounce (e.g. `2350.60`) |
| `spread` | Float64 | Direct difference (`ask - bid`) | USD (e.g. `0.15`) |
| `volume` | Float64 / Int | Tick volume or executed size (if available) | Units / Contracts |

### 2.2 M1 Candle Schema (`data/raw/` & `data/processed/`)
M1 candles aggregate tick prices over 60-second boundaries.

| Field Name | Type | Description | Unit / Format |
|---|---|---|---|
| `timestamp` | Datetime (UTC) | Start time of 60-second candle boundary | `YYYY-MM-DD HH:MM:00` |
| `open` | Float64 | Opening bid price | USD |
| `high` | Float64 | Highest bid price during candle | USD |
| `low` | Float64 | Lowest bid price during candle | USD |
| `close` | Float64 | Closing bid price | USD |
| `tick_volume` | Int64 | Count of tick updates within candle | Integer count |
| `spread_mean` | Float64 | Average bid-ask spread during candle | USD |
| `spread_max` | Float64 | Peak bid-ask spread during candle | USD |

---

## 3. Mandatory Standardization Rules

1. **Timezone Standardization:** All timestamps must be converted to **Coordinated Universal Time (UTC)**. Local broker timeframes (e.g., EET, EST) must be offset-adjusted during normalization.
2. **Monotonicity:** Timestamps must strictly increase monotonically. Out-of-sequence ticks must be sorted or flagged during cleaning.
3. **Real-Data Only Mandate:** Canonical research files stored in `data/raw/` and `data/processed/` must contain real historical tick/candle data. Synthetic data is prohibited in research datasets.
4. **Storage Formats:**
   - Raw immutable imports: `.csv` or `.csv.gz` stored in `data/raw/`.
   - Processed research datasets: Apache Parquet `.parquet` (Snappy compression) stored in `data/processed/`.

---

## 4. Phase 2 Interface Readiness

In Phase 1, data ingestion scripts establish clean interface contracts for reading and cleaning CSV/Parquet streams. The selection of specific broker endpoints, API keys, or historical bulk downloads is executed in Phase 2.
