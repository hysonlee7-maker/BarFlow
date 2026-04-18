# config.py
# Author: Hyson L.
# ─────────────────────────────────────────────────────────────
#  ALL tunable parameters live here.
#  Edit this file before running; nothing else needs to change.
# ─────────────────────────────────────────────────────────────

import os
from datetime import date, timedelta

# ── API ───────────────────────────────────────────────────────
POLYGON_API_KEY            = "..."   # ← replace
BASE_URL                   = "https://api.polygon.io"       # grouped daily bars / reference tickers
CORPORATE_ACTIONS_BASE_URL = "https://api.massive.com"       # dividends & splits (v1 endpoints)

# ── Data Scope ────────────────────────────────────────────────
START_DATE  = "2025-01-01"
END_DATE    = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")  # yesterday

LOCALE      = "us"
MARKET      = "stocks"
TICKER_TYPE = "CS"      # CS = Common Stock only

# ── Rate Limiting  (free tier: 5 calls / 60 s) ───────────────
RATE_LIMIT_CALLS  = 5
RATE_LIMIT_PERIOD = 60    # seconds in the sliding window
REQUEST_TIMEOUT   = 30    # seconds per HTTP call
MAX_RETRIES       = 3     # retries before giving up

# ── Force-refresh flags ───────────────────────────────────────
FORCE_REFRESH_STOCK_BASIC = False

# ── Paths ─────────────────────────────────────────────────────
BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR  = os.path.join(BASE_DIR, "raw_daily_cache")   # per-day checkpoint files
OUTPUT_DIR = os.path.join(BASE_DIR, "output")

# ── Output file names (the 4 final files) ─────────────────────
STOCK_BASIC_FILE = os.path.join(OUTPUT_DIR, "US_Share_Stock_Basic_All.parquet")
DAILY_FILE       = os.path.join(OUTPUT_DIR, "US_Share_Daily.parquet")
DIVIDEND_FILE    = os.path.join(OUTPUT_DIR, "US_Share_Dividend.parquet")
SPLITS_FILE      = os.path.join(OUTPUT_DIR, "US_Share_Splits.parquet")
