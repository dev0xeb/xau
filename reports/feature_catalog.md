# Feature Engineering Catalog — XAUUSD Scalp Lab

> **Document Status:** Reference Specification  
> **Total Engineered Features:** `56`  

---

## Feature List & Definitions

| Feature Name | Type | Description |
|---|---|---|
| `timestamp` | `datetime64[us, UTC]` | Standard research feature |
| `open` | `float64` | Standard research feature |
| `high` | `float64` | Standard research feature |
| `low` | `float64` | Standard research feature |
| `close` | `float64` | Standard research feature |
| `tick_volume` | `int64` | Standard research feature |
| `spread` | `float64` | Standard research feature |
| `mid` | `float64` | Standard research feature |
| `ret_abs` | `float64` | Standard research feature |
| `ret_log` | `float64` | Standard research feature |
| `high_low_range` | `float64` | Standard research feature |
| `body_size` | `float64` | Standard research feature |
| `upper_wick` | `float64` | Standard research feature |
| `lower_wick` | `float64` | Standard research feature |
| `atr_14` | `float64` | Standard research feature |
| `vol_rolling_20` | `float64` | Standard research feature |
| `vol_rolling_60` | `float64` | Standard research feature |
| `spread_rolling_mean_100` | `float64` | Standard research feature |
| `spread_percentile_100` | `float64` | Standard research feature |
| `spread_expansion` | `float64` | Standard research feature |
| `spread_contraction` | `float64` | Standard research feature |
| `swing_high_5` | `float64` | Standard research feature |
| `swing_low_5` | `float64` | Standard research feature |
| `swing_high_15` | `float64` | Standard research feature |
| `swing_low_15` | `float64` | Standard research feature |
| `trend_slope_20` | `float64` | Standard research feature |
| `consecutive_bullish` | `int64` | Standard research feature |
| `consecutive_bearish` | `int64` | Standard research feature |
| `compression_period` | `int64` | Standard research feature |
| `expansion_period` | `int64` | Standard research feature |
| `utc_hour` | `int32` | Standard research feature |
| `utc_minute` | `int32` | Standard research feature |
| `day_of_week` | `int32` | Standard research feature |
| `week_of_year` | `int64` | Standard research feature |
| `month` | `int32` | Standard research feature |
| `session_label` | `str` | Standard research feature |
| `event_asian_open` | `int64` | Standard research feature |
| `event_london_open` | `int64` | Standard research feature |
| `event_ny_open` | `int64` | Standard research feature |
| `event_london_close` | `int64` | Standard research feature |
| `event_ny_close` | `int64` | Standard research feature |
| `event_friday_close` | `int64` | Standard research feature |
| `macro_nfp_window` | `int64` | Standard research feature |
| `macro_cpi_window` | `int64` | Standard research feature |
| `macro_fomc_window` | `int64` | Standard research feature |
| `regime_trending` | `int64` | Standard research feature |
| `regime_ranging` | `int64` | Standard research feature |
| `regime_expanding` | `int64` | Standard research feature |
| `regime_contracting` | `int64` | Standard research feature |
| `regime_high_vol` | `int64` | Standard research feature |
| `regime_low_vol` | `int64` | Standard research feature |
| `estimated_spread_usd` | `float64` | Standard research feature |
| `estimated_commission_usd` | `float64` | Standard research feature |
| `estimated_slippage_usd` | `float64` | Standard research feature |
| `estimated_roundtrip_cost_usd` | `float64` | Standard research feature |
| `estimated_roundtrip_cost_pts` | `float64` | Standard research feature |