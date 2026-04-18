# Data Dictionary

> US Common Stock Market Data — Powered by Polygon.io

---

## Overview

| File | Rows | Update | Description |
|------|------|--------|-------------|
| `US_Share_Stock_Basic_All.parquet` | ~10,000 | Full overwrite | Ticker metadata |
| `US_Share_Daily.parquet` | ~3M+ | Append | Raw daily OHLCV |
| `US_Share_Dividend.parquet` | ~50,000+ | Full overwrite | Dividend events |
| `US_Share_Splits.parquet` | ~100–500 | Full overwrite | Split events |

**Date range:** 2025-01-01 → present
**Universe:** US Common Stock (CS) only
**Prices:** All prices in USD, raw (unadjusted)

---

## 1. US_Share_Stock_Basic_All.parquet

Ticker-level reference data for all US common stocks (active and delisted).

| Column | Type | Description |
|--------|------|-------------|
| `ticker` | string | Stock symbol |
| `name` | string | Full company name |
| `type` | string | Always `CS` (Common Stock) |
| `active` | boolean | `True` = currently listed |
| `currency_name` | string | Trading currency (e.g. `usd`) |
| `primary_exchange` | string | Primary exchange (e.g. `XNAS`, `XNYS`) |
| `composite_figi` | string | Bloomberg composite FIGI identifier |
| `share_class_figi` | string | Bloomberg share-class FIGI |
| `cik` | string | SEC CIK number |
| `sic_code` | string | SIC industry code |
| `sic_description` | string | SIC industry description |
| `list_date` | date | IPO / first trading date |
| `delisted_utc` | date | Delisting date (`null` if active) |
| `market_cap` | float | Market capitalisation (USD) |
| `weighted_shares_outstanding` | float | Weighted shares outstanding |
| `total_employees` | Int64 | Number of employees |
| `homepage_url` | string | Company website URL |

---

## 2. US_Share_Daily.parquet

Raw (unadjusted) daily bar data for all CS tickers from 2025-01-01.

| Column | Type | Description |
|--------|------|-------------|
| `date` | date | Trading date |
| `ticker` | string | Stock symbol |
| `open` | float | Opening price (raw) |
| `high` | float | Intraday high (raw) |
| `low` | float | Intraday low (raw) |
| `close` | float | Closing price (raw) |
| `volume` | float | Share volume traded |
| `vwap` | float | Volume-weighted average price |
| `transactions` | Int64 | Number of trades executed |

> **Note:** All prices are **raw / unadjusted**. To obtain adjusted prices,
> combine with `US_Share_Splits` and `US_Share_Dividend` — see Usage Guide.

---

## 3. US_Share_Dividend.parquet

Cash dividend events for all CS tickers since 2025-01-01.

| Column | Type | Description |
|--------|------|-------------|
| `ticker` | string | Stock symbol |
| `ex_dividend_date` | date | Ex-dividend date (key date for pricing) |
| `declaration_date` | date | Date dividend was announced |
| `record_date` | date | Shareholder-of-record date |
| `pay_date` | date | Payment date |
| `cash_amount` | float | Dividend per share (USD) |
| `split_adjusted_cash_amount` | float | `cash_amount` adjusted for subsequent splits |
| `distribution_type` | string | `recurring` / `special` / `supplemental` / `irregular` / `unknown` |
| `frequency` | Int64 | Dividends per year (0=one-time, 1=annual, 2=semi-annual, 4=quarterly, 12=monthly) |
| `historical_adjustment_factor` | float | Cumulative dividend-only backward adjustment factor |

> **Key field:** `historical_adjustment_factor`
> To adjust a raw price on date **D** for dividend effects only:
> find the **first row** where `ex_dividend_date > D` for that ticker,
> then: `div_adj_price = raw_price × historical_adjustment_factor`

---

## 4. US_Share_Splits.parquet

Stock split events for all CS tickers since 2025-01-01.

| Column | Type | Description |
|--------|------|-------------|
| `ticker` | string | Stock symbol |
| `execution_date` | date | Date the split took effect |
| `adjustment_type` | string | `forward_split` / `reverse_split` / `stock_dividend` |
| `split_from` | float | Share count before split (denominator) |
| `split_to` | float | Share count after split (numerator) |
| `historical_adjustment_factor` | float | Cumulative split-only backward adjustment factor |

> **Key field:** `historical_adjustment_factor`
> To adjust a raw price on date **D** for split effects only:
> find the **first row** where `execution_date > D` for that ticker,
> then: `split_adj_price = raw_price × historical_adjustment_factor`

---

## Adjustment Factor Logic

Full backward-adjusted price (splits + dividends):

```
adj_price = raw_price × split_factor × div_factor
```

| Term | Source | Default |
|------|--------|---------|
| `raw_price` | `US_Share_Daily.close` | — |
| `split_factor` | `US_Share_Splits.historical_adjustment_factor` (first split after date D) | `1.0` |
| `div_factor` | `US_Share_Dividend.historical_adjustment_factor` (first dividend after date D) | `1.0` |
