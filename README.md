# BarFlow

**A lightweight, free-tier US stock market data pipeline — powered by [Polygon.io](https://polygon.io).**  
Fetch, store, and incrementally update daily OHLCV bars, dividends, and splits for the entire US common stock universe.

> 中文版：[README_ZH.md](README_ZH.md)

---

## What It Does

- Downloads daily OHLCV bars for ~10,000 US common stocks (active + delisted)
- Tracks dividend and split history with pre-computed backward adjustment factors
- Saves everything as Parquet files — fast, compact, and easy to query with pandas
- Checkpoint resumption — safe to interrupt and re-run at any time
- Built for the **Polygon.io free tier** (5 calls/min) — no paid plan needed

---

## Project Structure

```
BarFlow/
├── config.py               # All parameters (API keys, dates, paths)
├── main.py                 # Full pipeline — run once to initialise
├── daily_update.py         # Incremental update — run daily after market close
├── fetch_stock_basic.py    # Fetch ticker metadata from Polygon.io
├── fetch_daily.py          # Fetch OHLCV bars from Polygon.io (with checkpoint/resume)
├── fetch_dividends.py      # Fetch dividend history
├── fetch_splits.py         # Fetch split history
├── utils.py                # Rate limiter, HTTP helpers, pagination
├── raw_daily_cache/        # Per-day checkpoint files (auto-generated)
└── output/                 # Final Parquet output files (auto-generated)
```

---

## Quick Start

**1. Install dependencies**
```bash
pip install -r requirements.txt
```

**2. Get a free API key** at [polygon.io](https://polygon.io) — no credit card needed.

**3. Open `config.py` and fill in your key:**
```python
POLYGON_API_KEY = "your_polygon_key_here"
```

**4. Run the initial download** (~70 min on free tier):
```bash
python main.py
```

**5. Keep it updated** — run once per trading day after market close:
```bash
python daily_update.py
```

If interrupted, just re-run — cached days are skipped automatically.

**Other modes:**
```bash
python main.py --daily-only       # bars only
python main.py --corporate-only   # dividends & splits only
```

---

## Reading the Data

```python
import pandas as pd

daily    = pd.read_parquet("output/US_Share_Daily.parquet")
basic    = pd.read_parquet("output/US_Share_Stock_Basic_All.parquet")
dividend = pd.read_parquet("output/US_Share_Dividend.parquet")
splits   = pd.read_parquet("output/US_Share_Splits.parquet")
```

**Common queries:**
```python
# Active tickers only
active = basic[basic["active"] == True]["ticker"].tolist()

# NASDAQ stocks
nasdaq = basic[basic["primary_exchange"] == "XNAS"]["ticker"].tolist()

# Filter by date range
mask = (daily["date"] >= pd.to_datetime("2025-06-01").date()) & \
       (daily["date"] <= pd.to_datetime("2025-12-31").date())
h2_2025 = daily[mask]
```

---

## Adjusted Prices

All prices are raw (unadjusted). Use the adjustment factors to compute backward-adjusted prices:

```
adj_price = raw_price × split_factor × div_factor
```

```python
def get_adj_close(ticker: str) -> pd.DataFrame:
    df = daily[daily["ticker"] == ticker][["date", "close"]].copy().sort_values("date")

    t_splits = (
        splits[splits["ticker"] == ticker]
        [["execution_date", "historical_adjustment_factor"]]
        .rename(columns={"execution_date": "date", "historical_adjustment_factor": "split_factor"})
        .sort_values("date")
    )
    t_divs = (
        dividend[dividend["ticker"] == ticker]
        [["ex_dividend_date", "historical_adjustment_factor"]]
        .rename(columns={"ex_dividend_date": "date", "historical_adjustment_factor": "div_factor"})
        .sort_values("date")
    )

    df = pd.merge_asof(df, t_splits, on="date", direction="forward").fillna({"split_factor": 1.0})
    df = pd.merge_asof(df, t_divs,   on="date", direction="forward").fillna({"div_factor":   1.0})
    df["adj_close"] = df["close"] * df["split_factor"] * df["div_factor"]
    return df[["date", "close", "adj_close"]]

aapl = get_adj_close("AAPL")
```

If no event exists after date D, the factor defaults to 1.0.

---

## Data Dictionary

### US_Share_Stock_Basic_All.parquet
Ticker-level metadata for all US common stocks (active + delisted). Updated: full overwrite.

| Column | Type | Description |
|--------|------|-------------|
| `ticker` | string | Stock symbol |
| `name` | string | Full company name |
| `active` | boolean | `True` = currently listed |
| `primary_exchange` | string | Exchange code (e.g. `XNAS`, `XNYS`) |
| `list_date` | date | IPO / first trading date |
| `delisted_utc` | date | Delisting date (`null` if active) |
| `market_cap` | float | Market capitalisation (USD) |
| `sic_code` / `sic_description` | string | Industry classification |
| `cik` | string | SEC CIK number |
| `composite_figi` | string | Bloomberg FIGI identifier |
| `weighted_shares_outstanding` | float | Weighted shares outstanding |
| `total_employees` | Int64 | Number of employees |
| `homepage_url` | string | Company website |

### US_Share_Daily.parquet
Raw daily OHLCV bars from 2025-01-01. Updated: append only.

| Column | Type | Description |
|--------|------|-------------|
| `date` | date | Trading date |
| `ticker` | string | Stock symbol |
| `open` / `high` / `low` / `close` | float | Raw unadjusted prices (USD) |
| `volume` | float | Share volume traded |
| `vwap` | float | Volume-weighted average price |
| `transactions` | Int64 | Number of trades executed |

### US_Share_Dividend.parquet
Dividend events since 2025-01-01. Updated: full overwrite.

| Column | Type | Description |
|--------|------|-------------|
| `ticker` | string | Stock symbol |
| `ex_dividend_date` | date | Ex-dividend date |
| `pay_date` | date | Payment date |
| `cash_amount` | float | Dividend per share (USD) |
| `split_adjusted_cash_amount` | float | Cash amount adjusted for subsequent splits |
| `distribution_type` | string | `recurring` / `special` / `supplemental` / `irregular` |
| `frequency` | Int64 | Per year: 1=annual, 2=semi, 4=quarterly, 12=monthly |
| `historical_adjustment_factor` | float | Cumulative dividend-only backward adjustment factor |

### US_Share_Splits.parquet
Split events since 2025-01-01. Updated: full overwrite.

| Column | Type | Description |
|--------|------|-------------|
| `ticker` | string | Stock symbol |
| `execution_date` | date | Date split took effect |
| `adjustment_type` | string | `forward_split` / `reverse_split` / `stock_dividend` |
| `split_from` / `split_to` | float | Ratio (e.g. 1→4 for a 4-for-1 split) |
| `historical_adjustment_factor` | float | Cumulative split-only backward adjustment factor |

---

## Config Reference

All settings in `config.py`:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `POLYGON_API_KEY` | — | Polygon.io API key |
| `START_DATE` | `2025-01-01` | Earliest date to fetch |
| `END_DATE` | Yesterday | Latest date to fetch |
| `TICKER_TYPE` | `CS` | Stock type filter |
| `RATE_LIMIT_CALLS` | `5` | Max API calls per window |
| `RATE_LIMIT_PERIOD` | `60` | Rate limit window (seconds) |
| `FORCE_REFRESH_STOCK_BASIC` | `False` | Force re-fetch on `main.py` |

---

## Troubleshooting

| Problem | Cause | Solution |
|---------|-------|----------|
| `403` on today's date | Free tier has no same-day data | Fixed: `END_DATE` defaults to yesterday |
| `403` on any date | Wrong or missing API key | Check `POLYGON_API_KEY` in `config.py` |
| `404` on dividends/splits | Wrong base URL | Set `CORPORATE_ACTIONS_BASE_URL` to `https://api.massive.com` |
| Pipeline interrupted | Any fetch error | Re-run: cached days skipped automatically |
| Dividend fetch slow | Large dataset, many pages | Normal — page size is set to 5000 |

---

*Built by Hyson L.*
