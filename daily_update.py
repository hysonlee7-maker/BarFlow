# daily_update.py
# Author: Hyson L.
# ─────────────────────────────────────────────────────────────
#  Runs every trading day to keep all 4 files current.
#
#  Pipeline
#  ────────
#  1. Stock Basic  — full re-fetch, detect new / delisted tickers
#  2. Daily        — checkpoint system appends any missing dates
#  3. Dividend     — full overwrite (factors auto-updated by Polygon)
#  4. Splits       — full overwrite (factors auto-updated by Polygon)
#
#  Usage
#  ─────
#  python daily_update.py
# ─────────────────────────────────────────────────────────────

from __future__ import annotations

import logging
import os
from typing import Optional

import pandas as pd

import config
from fetch_stock_basic import fetch_stock_basic   # raw fetch, bypasses cache guard
from fetch_daily       import run as run_daily
from fetch_dividends   import run as run_dividends
from fetch_splits      import run as run_splits

logger = logging.getLogger(__name__)

DIVIDER = "=" * 56


# ── Step 1: Stock Basic ───────────────────────────────────────
def update_stock_basic() -> tuple:
    """
    Re-fetch all CS tickers and overwrite the file.
    Returns (updated_df, new_tickers, delisted_tickers).
    """
    # Load existing snapshot for comparison
    if os.path.exists(config.STOCK_BASIC_FILE):
        old_df      = pd.read_parquet(config.STOCK_BASIC_FILE)
        old_tickers = set(old_df["ticker"])
        old_active  = set(old_df.loc[old_df["active"] == True, "ticker"])
    else:
        old_tickers = set()
        old_active  = set()

    # Fresh fetch from Polygon (always, regardless of FORCE_REFRESH flag)
    new_df      = fetch_stock_basic()
    new_tickers = set(new_df["ticker"])
    new_active  = set(new_df.loc[new_df["active"] == True, "ticker"])

    # ── Change detection (for logging only) ──────────────────
    added    = new_tickers - old_tickers           # brand-new tickers
    delisted = old_active  - new_active            # were active, now inactive

    if added:
        logger.info(
            "New tickers:    %d  →  %s%s",
            len(added),
            ", ".join(sorted(added)[:10]),
            "  …" if len(added) > 10 else "",
        )
    if delisted:
        logger.info(
            "Newly delisted: %d  →  %s%s",
            len(delisted),
            ", ".join(sorted(delisted)[:10]),
            "  …" if len(delisted) > 10 else "",
        )
    if not added and not delisted:
        logger.info("Stock Basic: no changes detected.")

    # Overwrite file with fresh data
    os.makedirs(config.OUTPUT_DIR, exist_ok=True)
    new_df.to_parquet(config.STOCK_BASIC_FILE, index=False)
    logger.info("Stock Basic saved: %d tickers total", len(new_df))

    return new_df, added, delisted


# ── Orchestrator ──────────────────────────────────────────────
def main() -> None:
    os.makedirs(config.OUTPUT_DIR, exist_ok=True)
    os.makedirs(config.CACHE_DIR,  exist_ok=True)

    # ── STEP 1 ────────────────────────────────────────────────
    logger.info(DIVIDER)
    logger.info("STEP 1 / 4  —  Stock Basic")
    logger.info(DIVIDER)
    stock_df, new_tickers, delisted_tickers = update_stock_basic()
    cs_tickers = set(stock_df["ticker"].unique())
    logger.info("Active CS universe: %d tickers", len(cs_tickers))

    # ── STEP 2 ────────────────────────────────────────────────
    logger.info(DIVIDER)
    logger.info("STEP 2 / 4  —  Daily OHLCV  (append missing dates)")
    logger.info(DIVIDER)
    # Checkpoint system automatically fetches any date not yet cached,
    # including data for newly listed tickers (they appear in grouped
    # daily bars from their first trading day onward).
    run_daily(cs_tickers=cs_tickers)

    # ── STEP 3 ────────────────────────────────────────────────
    logger.info(DIVIDER)
    logger.info("STEP 3 / 4  —  Dividend  (full overwrite)")
    logger.info(DIVIDER)
    run_dividends(cs_tickers=cs_tickers)

    # ── STEP 4 ────────────────────────────────────────────────
    logger.info(DIVIDER)
    logger.info("STEP 4 / 4  —  Splits  (full overwrite)")
    logger.info(DIVIDER)
    run_splits(cs_tickers=cs_tickers)

    # ── Summary ───────────────────────────────────────────────
    logger.info(DIVIDER)
    logger.info("DAILY UPDATE COMPLETE")
    logger.info("  New tickers    : %d", len(new_tickers))
    logger.info("  Newly delisted : %d", len(delisted_tickers))
    logger.info("  Date range     : %s → %s", config.START_DATE, config.END_DATE)
    logger.info("")
    for label, path in [
        ("Stock Basic", config.STOCK_BASIC_FILE),
        ("Daily",       config.DAILY_FILE),
        ("Dividend",    config.DIVIDEND_FILE),
        ("Splits",      config.SPLITS_FILE),
    ]:
        status = "✓" if os.path.exists(path) else "✗"
        logger.info("  [%s] %-12s → %s", status, label, path)
    logger.info(DIVIDER)


if __name__ == "__main__":
    main()
