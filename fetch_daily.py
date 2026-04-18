# fetch_daily.py
# Author: Hyson L.
# ─────────────────────────────────────────────────────────────
#  Downloads raw (un-adjusted) grouped daily bars for every US
#  trading day from START_DATE → END_DATE.
#
#  Checkpointing
#  ─────────────
#  Each calendar day is saved immediately to:
#      raw_daily_cache/<YYYY-MM-DD>.parquet
#
#  On a subsequent run, already-cached dates are skipped
#  automatically so interrupted jobs resume cleanly.
#
#  Market-closed days (holidays + weekends caught by calendar)
#  are written as empty sentinel files so they are never retried.
#
#  After fetching all missing dates, the per-day files are merged
#  into a single output/US_Share_Daily.parquet, filtered to the
#  CS tickers in Stock Basic.
# ─────────────────────────────────────────────────────────────

from __future__ import annotations

import logging
import os
from typing import Optional

import pandas as pd

import config
from utils import get_json, all_weekdays

logger = logging.getLogger(__name__)

# Polygon field → our column name
COL_MAP: dict = {
    "T":  "ticker",
    "o":  "open",
    "h":  "high",
    "l":  "low",
    "c":  "close",
    "v":  "volume",
    "vw": "vwap",
    "n":  "transactions",
}


# ── Single-day fetch ──────────────────────────────────────────
def fetch_one_day(date_str: str) -> Optional[pd.DataFrame]:
    """
    Fetch grouped daily bars for `date_str` (YYYY-MM-DD).
    Returns None when the market was closed on that date
    (Polygon returns an empty results list).
    All prices are RAW / un-adjusted (adjusted=false).
    """
    url = (
        f"{config.BASE_URL}/v2/aggs/grouped"
        f"/locale/{config.LOCALE}"
        f"/market/{config.MARKET}"
        f"/{date_str}"
    )
    data = get_json(url, {"adjusted": "false"})

    results = data.get("results")
    if not results:
        return None     # market closed / holiday

    df = pd.DataFrame(results).rename(columns=COL_MAP)

    # Keep only mapped columns that actually exist in the response
    keep = [v for v in COL_MAP.values() if v in df.columns]
    df   = df[keep].copy()
    df.insert(0, "date", pd.to_datetime(date_str).date())

    # Numeric coercions
    for col in ("open", "high", "low", "close", "volume", "vwap"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    if "transactions" in df.columns:
        df["transactions"] = (
            pd.to_numeric(df["transactions"], errors="coerce")
            .astype("Int64")
        )

    return df


# ── Checkpoint loop ───────────────────────────────────────────
def fetch_daily_with_checkpoint(cs_tickers: Optional[set] = None) -> None:
    """
    Iterate over every weekday in [START_DATE, END_DATE].
    Skip dates that already have a cache file.
    Save each trading day to raw_daily_cache/<date>.parquet.
    If `cs_tickers` is supplied, each file is pre-filtered to
    those tickers (keeps cache size small).
    """
    os.makedirs(config.CACHE_DIR, exist_ok=True)

    weekdays = all_weekdays(config.START_DATE, config.END_DATE)

    # Build set of already-cached date strings (exclude splits_cache)
    cached = {
        fname.replace(".parquet", "")
        for fname in os.listdir(config.CACHE_DIR)
        if fname.endswith(".parquet") and not fname.startswith("splits")
    }

    pending = [d for d in weekdays if d not in cached]
    logger.info(
        "Daily fetch: %d weekdays total | %d already cached | %d to fetch",
        len(weekdays), len(cached), len(pending),
    )

    for i, date_str in enumerate(pending, 1):
        logger.info("[%d/%d] Fetching %s …", i, len(pending), date_str)

        df = fetch_one_day(date_str)
        cache_path = os.path.join(config.CACHE_DIR, f"{date_str}.parquet")

        if df is None:
            logger.info("  → Market closed on %s — writing sentinel", date_str)
            # Empty parquet acts as "done" sentinel; skipped during merge
            pd.DataFrame().to_parquet(cache_path, index=False)
            continue

        if cs_tickers:
            df = df[df["ticker"].isin(cs_tickers)]

        df.to_parquet(cache_path, index=False)
        logger.info("  → %d rows saved", len(df))


# ── Merge cache → single parquet ──────────────────────────────
def merge_cache_to_daily() -> pd.DataFrame:
    """
    Read all non-empty cache files and concatenate them into
    output/US_Share_Daily.parquet (sorted by date, then ticker).
    Returns the merged DataFrame.
    """
    logger.info("Merging cache → %s", config.DAILY_FILE)

    cache_files = sorted(
        fname
        for fname in os.listdir(config.CACHE_DIR)
        if fname.endswith(".parquet") and not fname.startswith("splits")
    )

    frames = []
    for fname in cache_files:
        path = os.path.join(config.CACHE_DIR, fname)
        df   = pd.read_parquet(path)
        if not df.empty:
            frames.append(df)

    if not frames:
        logger.warning("No cached daily data found — output file not created")
        return pd.DataFrame()

    merged = pd.concat(frames, ignore_index=True)
    merged = merged.sort_values(["date", "ticker"]).reset_index(drop=True)

    os.makedirs(config.OUTPUT_DIR, exist_ok=True)
    merged.to_parquet(config.DAILY_FILE, index=False)
    logger.info(
        "Daily file saved: %d rows × %d cols → %s",
        len(merged), len(merged.columns), config.DAILY_FILE,
    )
    return merged


# ── Entry point ───────────────────────────────────────────────
def run(cs_tickers: Optional[set] = None) -> pd.DataFrame:
    fetch_daily_with_checkpoint(cs_tickers)
    return merge_cache_to_daily()


if __name__ == "__main__":
    run()
