# Data Catalog Schema Specification — XAUUSD Scalp Lab

> **Document Status:** Metadata Schema Specification  
> **Schema Version:** 1.0.0  

---

## 1. Overview

Every clean research dataset residing in `data/processed/` must be paired with an immutable JSON catalog metadata entry stored in `data/metadata/`. This ensures strict traceability, cryptographic integrity verification, and dataset version control.

---

## 2. Catalog JSON Metadata Schema

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "XAUUSDDatasetCatalogMetadata",
  "type": "object",
  "required": [
    "dataset_id",
    "version",
    "instrument",
    "granularity",
    "source",
    "created_at_utc",
    "sha256_checksum",
    "file_path",
    "row_count",
    "date_range",
    "schema",
    "audit_summary"
  ],
  "properties": {
    "dataset_id": {
      "type": "string",
      "example": "XAUUSD_M1_2024_Q1"
    },
    "version": {
      "type": "string",
      "example": "1.0.0"
    },
    "instrument": {
      "type": "string",
      "enum": ["XAUUSD"]
    },
    "granularity": {
      "type": "string",
      "enum": ["TICK", "M1", "M5"]
    },
    "source": {
      "type": "string",
      "example": "HISTORICAL_BROKER_EXPORT"
    },
    "created_at_utc": {
      "type": "string",
      "format": "date-time"
    },
    "sha256_checksum": {
      "type": "string",
      "pattern": "^[a-f0-9]{64}$"
    },
    "file_path": {
      "type": "string",
      "example": "data/processed/XAUUSD_M1_2024_Q1.parquet"
    },
    "row_count": {
      "type": "integer",
      "minimum": 1
    },
    "date_range": {
      "type": "object",
      "required": ["start_utc", "end_utc"],
      "properties": {
        "start_utc": { "type": "string", "format": "date-time" },
        "end_utc": { "type": "string", "format": "date-time" }
      }
    },
    "schema": {
      "type": "object",
      "description": "Column name to data type mappings"
    },
    "audit_summary": {
      "type": "object",
      "required": ["quality_score", "passed_audit"],
      "properties": {
        "quality_score": { "type": "number", "minimum": 0.0, "maximum": 100.0 },
        "passed_audit": { "type": "boolean" },
        "anomalies_detected": { "type": "integer" }
      }
    }
  }
}
```
