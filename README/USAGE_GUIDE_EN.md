# Usage Guide

> US Common Stock Market Data Pipeline

---

## 1. Setup

### Requirements

```bash
pip install -r requirements.txt
```

### Configure API Key

Open `config.py` and fill in your API keys:

```python
POLYGON_API_KEY            = "your_polygon_key_here"   # for daily bars
CORPORATE_ACTIONS_BASE_URL = "https://api.massive.com" # for dividends & splits
```

### Project Structure

```
BarFlow/
├── config.py               # All parameters
├── main.py                 # One-time initial run
├── daily_update.py         # Daily incremental update
├── fetch_stock_basic.py
├── fetch_daily.py
├── fetch_dividends.py
├── fetch_splits.py
├── utils.py
├── raw_daily_cache/        # Per-day checkpoint files
└── output/                 # Final parquet files
    ├── US_Share_Stock_Basic_All.parquet
    ├── US_Share_Daily.parquet
    ├── US_Share_Dividend.parquet
    └── US_Share_Splits.parquet
```

---

## 2. Running the Pipeline

### First-time Full Run

Run once to download all data from `START_DATE` (default: 2025-01-01) to yesterday.

```bash
python main.py
```

This will execute 4 steps in order:
1. Fetch all CS ticker metadata
2. Download daily bars day-by-day with checkpointing
3. Download dividend history
4. Download split history

> **Note:** Step 2 fetches ~330 trading days at 1 call/day.
> At 5 calls/min (free tier), expect ~70 minutes for the initial run.
> If interrupted, simply re-run — already-cached days are skipped automatically.

### Daily Incremental Update

Run every trading day (e.g. via cron after market close):

```bash
python daily_update.py
```

What it does each run:

| Step | Action |
|------|--------|
| 1 | Re-fetch Stock Basic, log new/delisted tickers |
| 2 | Append yesterday's bars (checkpoint auto-handles gaps) |
| 3 | Full overwrite of Dividend file |
| 4 | Full overwrite of Splits file |

### Other Run Modes

```bash
# Append daily bars only (fastest, ~1 min)
python main.py --daily-only

# Refresh dividends & splits only
python main.py --corporate-only
```

---

## 3. Reading the Data

```python
import pandas as pd

daily    = pd.read_parquet("output/US_Share_Daily.parquet")
basic    = pd.read_parquet("output/US_Share_Stock_Basic_All.parquet")
dividend = pd.read_parquet("output/US_Share_Dividend.parquet")
splits   = pd.read_parquet("output/US_Share_Splits.parquet")
```

---

## 4. Computing Adjusted Prices

Backward-adjusted price formula:

```
adj_price = raw_price × split_factor × div_factor
```

If no event exists after date D, the factor defaults to 1.0.

### Full Example

```python
import pandas as pd
import numpy as np

daily    = pd.read_parquet("output/US_Share_Daily.parquet")
dividend = pd.read_parquet("output/US_Share_Dividend.parquet")
splits   = pd.read_parquet("output/US_Share_Splits.parquet")

def get_adj_close(ticker: str) -> pd.DataFrame:
    """Return backward-adjusted close prices for a given ticker."""
    df = daily[daily["ticker"] == ticker][["date", "close"]].copy()

    # ── Split factor ──────────────────────────────────────────
    t_splits = splits[splits["ticker"] == ticker].sort_values("execution_date")

    def get_split_factor(date):
        future = t_splits[t_splits["execution_date"] > date]
        return future.iloc[0]["historical_adjustment_factor"] if not future.empty else 1.0

    # ── Dividend factor ───────────────────────────────────────
    t_divs = dividend[dividend["ticker"] == ticker].sort_values("ex_dividend_date")

    def get_div_factor(date):
        future = t_divs[t_divs["ex_dividend_date"] > date]
        return future.iloc[0]["historical_adjustment_factor"] if not future.empty else 1.0

    df["split_factor"] = df["date"].apply(get_split_factor)
    df["div_factor"]   = df["date"].apply(get_div_factor)
    df["adj_close"]    = df["close"] * df["split_factor"] * df["div_factor"]

    return df[["date", "close", "adj_close"]]

# Usage
aapl = get_adj_close("AAPL")
print(aapl.tail())
```

### Vectorised Version (faster)

```python
def get_adj_close_fast(ticker: str) -> pd.DataFrame:
    df = daily[daily["ticker"] == ticker][["date", "close"]].copy().sort_values("date")

    t_splits = (
        splits[splits["ticker"] == ticker]
        [["execution_date", "historical_adjustment_factor"]]
        .rename(columns={"execution_date": "date",
                         "historical_adjustment_factor": "split_factor"})
        .sort_values("date")
    )
    t_divs = (
        dividend[dividend["ticker"] == ticker]
        [["ex_dividend_date", "historical_adjustment_factor"]]
        .rename(columns={"ex_dividend_date": "date",
                         "historical_adjustment_factor": "div_factor"})
        .sort_values("date")
    )

    # For each price date, find the FIRST event date strictly after it
    df = pd.merge_asof(df, t_splits, on="date", direction="forward").fillna({"split_factor": 1.0})
    df = pd.merge_asof(df, t_divs,   on="date", direction="forward").fillna({"div_factor":   1.0})
    df["adj_close"] = df["close"] * df["split_factor"] * df["div_factor"]

    return df[["date", "close", "adj_close", "split_factor", "div_factor"]]
```

---

## 5. Common Queries

### Filter by Exchange

```python
# NASDAQ stocks only
nasdaq = basic[basic["primary_exchange"] == "XNAS"]["ticker"].tolist()

# NYSE stocks only
nyse = basic[basic["primary_exchange"] == "XNYS"]["ticker"].tolist()
```

### Filter by Date Range

```python
mask = (daily["date"] >= pd.to_datetime("2025-06-01").date()) & \
       (daily["date"] <= pd.to_datetime("2025-12-31").date())
h2_2025 = daily[mask]
```

### Get Active Tickers

```python
active_tickers = basic[basic["active"] == True]["ticker"].tolist()
```

### Dividend Yield

```python
# Annualised dividend yield for a ticker
ticker = "AAPL"
latest_price  = daily[daily["ticker"] == ticker].sort_values("date").iloc[-1]["close"]
annual_div    = dividend[dividend["ticker"] == ticker]["cash_amount"].sum()
div_yield     = annual_div / latest_price
print(f"{ticker} dividend yield: {div_yield:.2%}")
```

### Stocks that Underwent Splits

```python
# All forward splits in our data range
forward_splits = splits[splits["adjustment_type"] == "forward_split"]
print(forward_splits[["ticker", "execution_date", "split_from", "split_to"]])
```

---

## 6. Config Reference

All parameters are in `config.py`. Key settings:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `POLYGON_API_KEY` | — | API key for daily bars |
| `CORPORATE_ACTIONS_BASE_URL` | `https://api.massive.com` | Base URL for dividends & splits |
| `START_DATE` | `2025-01-01` | Earliest date to fetch |
| `END_DATE` | Yesterday | Latest date to fetch |
| `TICKER_TYPE` | `CS` | Stock type filter |
| `RATE_LIMIT_CALLS` | `5` | Max API calls per window |
| `RATE_LIMIT_PERIOD` | `60` | Rate limit window (seconds) |
| `FORCE_REFRESH_STOCK_BASIC` | `False` | Force re-fetch Stock Basic on `main.py` |

---

## 7. Troubleshooting

| Problem | Cause | Solution |
|---------|-------|----------|
| `403 Forbidden` on today's date | Free tier has no same-day data | Fixed: `END_DATE` defaults to yesterday |
| `403 Forbidden` on any date | Wrong or missing API key | Check `POLYGON_API_KEY` in `config.py` |
| `404` on dividends/splits | Wrong `CORPORATE_ACTIONS_BASE_URL` | Set to `https://api.massive.com` |
| Pipeline interrupted mid-run | Any error during daily fetch | Re-run: cached days are skipped automatically |
| Dividend fetch very slow | Many pages to paginate | Normal; limit is set to 5000 per page |
