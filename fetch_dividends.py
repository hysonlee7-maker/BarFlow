# fetch_dividends.py
# Author: Hyson L.
# ─────────────────────────────────────────────────────────────
#  Downloads all dividend events since START_DATE and writes:
#      output/US_Share_Dividend.parquet
#
#  Endpoint: GET /stocks/v1/dividends
#
#  Key field: historical_adjustment_factor
#  ────────────────────────────────────────
#  Polygon-provided cumulative adjustment factor for dividends.
#  To backward-adjust a raw price on date D:
#      find the first dividend for that ticker with
#      ex_dividend_date > D, then:
#      adj_price = raw_price × historical_adjustment_factor
#
#  distribution_type values:
#      recurring, special, supplemental, irregular, unknown
#
#  frequency values (dividends per year):
#      0=one-time, 1=annual, 2=semi-annual, 3=trimester,
#      4=quarterly, 12=monthly, 24=bi-monthly, 52=weekly
# ─────────────────────────────────────────────────────────────

from __future__ import annotations

import logging
import os
from typing import Optional

import pandas as pd

import config
from utils import paginate

logger = logging.getLogger(__name__)

KEEP_COLS: list = [
    "ticker",
    "ex_dividend_date",
    "declaration_date",
    "record_date",
    "pay_date",
    "cash_amount",
    "split_adjusted_cash_amount",   # cash amount adjusted for subsequent splits
    "distribution_type",            # recurring / special / supplemental / irregular / unknown
    "frequency",
    "historical_adjustment_factor", # ← cumulative div-only factor provided by Polygon
]

DATE_COLS: list = [
    "ex_dividend_date",
    "declaration_date",
    "record_date",
    "pay_date",
]


def fetch_dividends(cs_tickers: Optional[set] = None) -> pd.DataFrame:
    """
    Download all dividend events with ex_dividend_date >= START_DATE.
    Filters to cs_tickers if provided.
    """
    logger.info("Fetching dividends (ex_date >= %s)…", config.START_DATE)

    url    = f"{config.CORPORATE_ACTIONS_BASE_URL}/stocks/v1/dividends"
    params = {
        "ex_dividend_date.gte": config.START_DATE,
        "limit": 5000,
    }
    records = paginate(url, params)

    if not records:
        logger.warning("No dividend records returned!")
        return pd.DataFrame(columns=KEEP_COLS)

    df = pd.DataFrame(records)

    for col in KEEP_COLS:
        if col not in df.columns:
            df[col] = None
    df = df[KEEP_COLS].copy()

    # ── Type coercions ────────────────────────────────────────
    for col in DATE_COLS:
        df[col] = pd.to_datetime(df[col], errors="coerce").dt.date

    df["cash_amount"]                = pd.to_numeric(df["cash_amount"],                errors="coerce")
    df["split_adjusted_cash_amount"] = pd.to_numeric(df["split_adjusted_cash_amount"], errors="coerce")
    df["historical_adjustment_factor"] = pd.to_numeric(df["historical_adjustment_factor"], errors="coerce")
    df["frequency"] = pd.to_numeric(df["frequency"], errors="coerce").astype("Int64")

    if cs_tickers:
        df = df[df["ticker"].isin(cs_tickers)]

    df = df.dropna(subset=["ex_dividend_date", "cash_amount"])
    df = df.sort_values(["ticker", "ex_dividend_date"]).reset_index(drop=True)

    logger.info("Dividends: %d records for %d tickers",
                len(df), df["ticker"].nunique())
    return df


def run(cs_tickers: Optional[set] = None) -> pd.DataFrame:
    os.makedirs(config.OUTPUT_DIR, exist_ok=True)
    df = fetch_dividends(cs_tickers)
    df.to_parquet(config.DIVIDEND_FILE, index=False)
    logger.info("Saved → %s  (%d rows)", config.DIVIDEND_FILE, len(df))
    return df


if __name__ == "__main__":
    run()
