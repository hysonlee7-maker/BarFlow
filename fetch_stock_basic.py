# fetch_stock_basic.py
# Author: Hyson L.
# ─────────────────────────────────────────────────────────────
#  Fetches metadata for every US Common-Stock ticker (active
#  and delisted) from Polygon and writes:
#      output/US_Share_Stock_Basic_All.parquet
#
#  SIC enrichment
#  ──────────────
#  Polygon's list endpoint does not return sic_code. After the
#  Polygon fetch, enrich_sic() fills null sic_code /
#  sic_description values using the free SEC EDGAR API (~8
#  req/sec, no key required). Only rows with a CIK but no
#  sic_code are queried, so daily updates only hit SEC for
#  newly listed tickers.
# ─────────────────────────────────────────────────────────────

from __future__ import annotations

import logging
import os
import time

import pandas as pd
import requests

import config
from utils import paginate

# ── SEC EDGAR settings ────────────────────────────────────────
_SEC_BASE   = "https://data.sec.gov/submissions"
_USER_AGENT = "BarFlow hysonlee7-maker"
_SEC_DELAY  = 0.12   # ~8 req/sec, safely under SEC's 10/sec limit

logger = logging.getLogger(__name__)


# ── SEC EDGAR helpers ─────────────────────────────────────────
def _fetch_sic(cik: str) -> tuple[str | None, str | None]:
    """Return (sic_code, sic_description) from SEC EDGAR for one CIK."""
    try:
        url = f"{_SEC_BASE}/CIK{cik.zfill(10)}.json"
        r = requests.get(url, headers={"User-Agent": _USER_AGENT}, timeout=10)
        if r.status_code == 200:
            data = r.json()
            sic = data.get("sic")
            return (str(sic) if sic else None), data.get("sicDescription")
    except Exception as e:
        logger.debug("SEC EDGAR CIK %s → error: %s", cik, e)
    return None, None


def enrich_sic(df: pd.DataFrame) -> pd.DataFrame:
    """
    Fill null sic_code / sic_description for any row that has a CIK.
    Skips rows already filled — safe to call on partial or full DataFrames.
    """
    targets = df[df["cik"].notna() & df["sic_code"].isna()].index.tolist()
    if not targets:
        logger.info("SIC enrichment: nothing to do.")
        return df

    logger.info("SIC enrichment: querying SEC EDGAR for %d tickers…", len(targets))
    filled = 0
    for i, idx in enumerate(targets, 1):
        sic, desc = _fetch_sic(str(df.at[idx, "cik"]))
        if sic:
            df.at[idx, "sic_code"]        = sic
            df.at[idx, "sic_description"] = desc
            filled += 1
        if i % 50 == 0:
            logger.info("  SIC: %d / %d  (filled: %d)", i, len(targets), filled)
        time.sleep(_SEC_DELAY)

    logger.info("SIC enrichment done: filled %d / %d", filled, len(targets))
    return df

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
    df = enrich_sic(df)
    df.to_parquet(config.STOCK_BASIC_FILE, index=False)
    logger.info("Saved → %s  (%d rows)", config.STOCK_BASIC_FILE, len(df))
    return df


if __name__ == "__main__":
    run()
