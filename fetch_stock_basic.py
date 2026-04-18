# fetch_stock_basic.py
# Author: Hyson L.
# ─────────────────────────────────────────────────────────────
#  Fetches metadata for every US Common-Stock ticker (active
#  and delisted) from Polygon and writes:
#      output/US_Share_Stock_Basic_All.parquet
# ─────────────────────────────────────────────────────────────

from __future__ import annotations

import logging
import os

import pandas as pd

import config
from utils import paginate

logger = logging.getLogger(__name__)

# Columns to retain from Polygon's /v3/reference/tickers response
KEEP_COLS: list = [
    "ticker",
    "name",
    "type",
    "active",
    "currency_name",
    "primary_exchange",
    "composite_figi",
    "share_class_figi",
    "cik",
    "sic_code",
    "sic_description",
    "list_date",          # IPO / first-trade date
    "delisted_utc",       # None if still active
    "market_cap",
    "weighted_shares_outstanding",
    "total_employees",
    "homepage_url",
]


def fetch_stock_basic() -> pd.DataFrame:
    """
    Download all CS tickers (active + delisted) and return a
    cleaned, deduplicated DataFrame.
    """
    base_params = {
        "type":   config.TICKER_TYPE,
        "market": config.MARKET,
        "locale": config.LOCALE,
        "limit":  1000,
    }
    url = f"{config.BASE_URL}/v3/reference/tickers"

    logger.info("Fetching active tickers (type=%s)…", config.TICKER_TYPE)
    records = paginate(url, {**base_params, "active": "true"})

    logger.info("Fetching delisted tickers (type=%s)…", config.TICKER_TYPE)
    records += paginate(url, {**base_params, "active": "false"})

    if not records:
        logger.warning("No ticker records returned from Polygon!")
        return pd.DataFrame(columns=KEEP_COLS)

    df = pd.DataFrame(records)

    # Add any missing expected columns as NaN
    for col in KEEP_COLS:
        if col not in df.columns:
            df[col] = None
    df = df[KEEP_COLS].copy()

    # ── Type coercions ────────────────────────────────────────
    for date_col in ("list_date", "delisted_utc"):
        df[date_col] = pd.to_datetime(df[date_col], errors="coerce").dt.date

    df["active"]                      = df["active"].astype("boolean")
    df["market_cap"]                  = pd.to_numeric(df["market_cap"],  errors="coerce")
    df["weighted_shares_outstanding"] = pd.to_numeric(
        df["weighted_shares_outstanding"], errors="coerce"
    )
    # Use nullable Int64 so NaN doesn't force float dtype
    df["total_employees"] = (
        pd.to_numeric(df["total_employees"], errors="coerce")
        .astype("Int64")
    )

    df = df.drop_duplicates(subset=["ticker"])
    df = df.sort_values("ticker").reset_index(drop=True)

    logger.info("Stock basic: %d tickers (active + delisted)", len(df))
    return df


def run() -> pd.DataFrame:
    os.makedirs(config.OUTPUT_DIR, exist_ok=True)

    if os.path.exists(config.STOCK_BASIC_FILE) and not config.FORCE_REFRESH_STOCK_BASIC:
        logger.info(
            "Stock basic file already exists (FORCE_REFRESH_STOCK_BASIC=False). "
            "Loading from disk: %s",
            config.STOCK_BASIC_FILE,
        )
        return pd.read_parquet(config.STOCK_BASIC_FILE)

    df = fetch_stock_basic()
    df.to_parquet(config.STOCK_BASIC_FILE, index=False)
    logger.info("Saved → %s  (%d rows)", config.STOCK_BASIC_FILE, len(df))
    return df


if __name__ == "__main__":
    run()
