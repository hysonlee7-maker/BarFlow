# main.py
# Author: Hyson L.
# ─────────────────────────────────────────────────────────────
#  Orchestrator — runs all four data-pipeline steps in sequence.
#
#  Output files
#  ────────────
#  1. US_Share_Stock_Basic_All.parquet   ← fetch_stock_basic.py
#  2. US_Share_Daily.parquet             ← fetch_daily.py  (checkpointed)
#  3. US_Share_Dividend.parquet          ← fetch_dividends.py
#  4. US_Share_Splits.parquet            ← fetch_splits.py
#
#  How to get an adjusted price
#  ────────────────────────────
#  adj_price = raw_price × split_factor × div_factor
#
#  split_factor: from US_Share_Splits — for date D, find the
#    first row where execution_date > D for that ticker.
#  div_factor:   from US_Share_Dividend — for date D, find the
#    first row where ex_dividend_date > D for that ticker.
#  If no row exists, the factor defaults to 1.0.
#
#  Usage
#  ─────
#  Full run (first time):
#      python main.py
#
#  Daily update (append new bars only):
#      python main.py --daily-only
#
#  Refresh corporate actions only (dividends + splits):
#      python main.py --corporate-only
# ─────────────────────────────────────────────────────────────

from __future__ import annotations

import argparse
import logging
import os
import sys

import pandas as pd

import config
from fetch_stock_basic import run as run_stock_basic
from fetch_daily       import run as run_daily
from fetch_dividends   import run as run_dividends
from fetch_splits      import run as run_splits

logger = logging.getLogger(__name__)

DIVIDER = "=" * 56


def _banner(step: str, total: int, label: str) -> None:
    logger.info(DIVIDER)
    logger.info("STEP %s / %s  —  %s", step, total, label)
    logger.info(DIVIDER)


def main(daily_only: bool = False, corporate_only: bool = False) -> None:
    if daily_only and corporate_only:
        logger.error("--daily-only and --corporate-only are mutually exclusive.")
        sys.exit(1)

    os.makedirs(config.OUTPUT_DIR, exist_ok=True)
    os.makedirs(config.CACHE_DIR,  exist_ok=True)

    # ── STEP 1: Stock Basic ───────────────────────────────────
    if not daily_only and not corporate_only:
        _banner("1", "4", "Stock Basic")
        stock_df = run_stock_basic()
    else:
        logger.info("Loading existing stock basic → %s", config.STOCK_BASIC_FILE)
        stock_df = pd.read_parquet(config.STOCK_BASIC_FILE)

    cs_tickers = set(stock_df["ticker"].unique())
    logger.info("Common-stock universe: %d tickers", len(cs_tickers))

    # ── STEP 2: Daily OHLCV (raw) ─────────────────────────────
    if not corporate_only:
        _banner("2", "4", "Daily OHLCV — raw prices (checkpointed)")
        run_daily(cs_tickers=cs_tickers)
    else:
        logger.info("Skipping daily fetch (--corporate-only mode)")

    # ── STEP 3: Dividends ─────────────────────────────────────
    if not daily_only:
        _banner("3", "4", "Dividends")
        run_dividends(cs_tickers=cs_tickers)
    else:
        logger.info("Skipping dividends (--daily-only mode)")

    # ── STEP 4: Splits ────────────────────────────────────────
    if not daily_only:
        _banner("4", "4", "Splits")
        run_splits(cs_tickers=cs_tickers)
    else:
        logger.info("Skipping splits (--daily-only mode)")

    # ── Summary ───────────────────────────────────────────────
    logger.info(DIVIDER)
    logger.info("ALL DONE — output files:")
    for label, path in [
        ("Stock Basic", config.STOCK_BASIC_FILE),
        ("Daily",       config.DAILY_FILE),
        ("Dividend",    config.DIVIDEND_FILE),
        ("Splits",      config.SPLITS_FILE),
    ]:
        status = "✓" if os.path.exists(path) else "✗ (not generated this run)"
        logger.info("  [%s] %-12s → %s", status, label, path)
    logger.info(DIVIDER)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="US common-stock data pipeline"
    )
    parser.add_argument(
        "--daily-only",
        action="store_true",
        help="Only append new daily OHLCV bars (skip dividends & splits)",
    )
    parser.add_argument(
        "--corporate-only",
        action="store_true",
        help="Only refresh dividends & splits (skip daily bars)",
    )
    args = parser.parse_args()
    main(daily_only=args.daily_only, corporate_only=args.corporate_only)
