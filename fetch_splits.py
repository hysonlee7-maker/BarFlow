# fetch_splits.py
# Author: Hyson L.
# ─────────────────────────────────────────────────────────────
#  Downloads all stock split events since START_DATE and writes:
#      output/US_Share_Splits.parquet
#
#  Endpoint: GET /stocks/v1/splits
#
#  Key field: historical_adjustment_factor
#  ────────────────────────────────────────
#  Polygon-provided cumulative adjustment factor for splits.
#  To backward-adjust a raw price on date D:
#      find the first split for that ticker with
#      execution_date > D, then:
#      adj_price = raw_price × historical_adjustment_factor
#
#  Combined full adjustment (splits + dividends):
#      adj_price = raw_price × split_factor × div_factor
#
#  adjustment_type values:
#      forward_split   – share count increases, price decreases
#      reverse_split   – share count decreases, price increases
#      stock_dividend  – shares issued as a dividend
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
    "execution_date",
    "adjustment_type",              # forward_split / reverse_split / stock_dividend
    "split_from",                   # old share count (denominator)
    "split_to",                     # new share count (numerator)
    "historical_adjustment_factor", # ← cumulative split-only factor provided by Polygon
]


def fetch_splits(cs_tickers: Optional[set] = None) -> pd.DataFrame:
    """
    Download all split events with execution_date >= START_DATE.
    Filters to cs_tickers if provided.
    """
    logger.info("Fetching splits (execution_date >= %s)…", config.START_DATE)

    url    = f"{config.CORPORATE_ACTIONS_BASE_URL}/stocks/v1/splits"
    params = {
        "execution_date.gte": config.START_DATE,
        "limit": 5000,
    }
    records = paginate(url, params)

    if not records:
        logger.info("No split records found since %s.", config.START_DATE)
        return pd.DataFrame(columns=KEEP_COLS)

    df = pd.DataFrame(records)

    for col in KEEP_COLS:
        if col not in df.columns:
            df[col] = None
    df = df[KEEP_COLS].copy()

    # ── Type coercions ────────────────────────────────────────
    df["execution_date"] = pd.to_datetime(df["execution_date"], errors="coerce").dt.date
    df["split_from"]     = pd.to_numeric(df["split_from"],     errors="coerce")
    df["split_to"]       = pd.to_numeric(df["split_to"],       errors="coerce")
    df["historical_adjustment_factor"] = pd.to_numeric(
        df["historical_adjustment_factor"], errors="coerce"
    )

    if cs_tickers:
        df = df[df["ticker"].isin(cs_tickers)]

    df = df.dropna(subset=["execution_date"])
    df = df.sort_values(["ticker", "execution_date"]).reset_index(drop=True)

    logger.info("Splits: %d records for %d tickers",
                len(df), df["ticker"].nunique())
    return df


def run(cs_tickers: Optional[set] = None) -> pd.DataFrame:
    os.makedirs(config.OUTPUT_DIR, exist_ok=True)
    df = fetch_splits(cs_tickers)
    df.to_parquet(config.SPLITS_FILE, index=False)
    logger.info("Saved → %s  (%d rows)", config.SPLITS_FILE, len(df))
    return df


if __name__ == "__main__":
    run()
