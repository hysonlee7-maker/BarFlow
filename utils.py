# utils.py
# Author: Hyson L.
# ─────────────────────────────────────────────────────────────
#  Shared utilities: logging, rate-limiter, HTTP helper,
#  paginator, and weekday-date generator.
# ─────────────────────────────────────────────────────────────

from __future__ import annotations

import logging
import time
from collections import deque
from datetime import datetime, timedelta
from typing import Optional

import requests

import config

# ── Logging setup ─────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


# ── Sliding-window Rate Limiter ───────────────────────────────
class RateLimiter:
    """
    Allow at most `max_calls` calls within a rolling `period`-second window.
    Thread-safe for single-threaded use; add a Lock for multi-threaded code.
    """

    def __init__(
        self,
        max_calls: int = config.RATE_LIMIT_CALLS,
        period: float = config.RATE_LIMIT_PERIOD,
    ) -> None:
        self.max_calls = max_calls
        self.period    = period
        self._calls: deque = deque()

    def acquire(self) -> None:
        now = time.monotonic()
        # Purge timestamps outside the current window
        while self._calls and now - self._calls[0] >= self.period:
            self._calls.popleft()
        if len(self._calls) >= self.max_calls:
            sleep_for = self.period - (now - self._calls[0]) + 0.05
            logger.debug("Rate-limit pause: %.2fs", sleep_for)
            time.sleep(sleep_for)
        self._calls.append(time.monotonic())


# Module-level singleton — all fetch modules share one limiter
_rate_limiter = RateLimiter()


# ── HTTP Helper ───────────────────────────────────────────────
def get_json(
    url: str,
    params: Optional[dict] = None,
    retries: int = config.MAX_RETRIES,
) -> dict:
    """
    GET `url` with rate-limiting and exponential-backoff retries.
    Automatically appends the API key from config.
    Raises RuntimeError after exhausting all retries.
    """
    if params is None:
        params = {}
    params = dict(params)                         # avoid mutating caller's dict
    params["apiKey"] = config.POLYGON_API_KEY

    for attempt in range(1, retries + 1):
        _rate_limiter.acquire()
        try:
            resp = requests.get(url, params=params, timeout=config.REQUEST_TIMEOUT)

            if resp.status_code == 200:
                return resp.json()

            if resp.status_code == 429:
                wait = config.RATE_LIMIT_PERIOD * attempt
                logger.warning("429 Too Many Requests — sleeping %ds", wait)
                time.sleep(wait)
                continue

            if resp.status_code == 403:
                from datetime import date
                today = date.today().strftime("%Y-%m-%d")
                if today in url:
                    logger.warning("403 on today's date — free tier has no same-day access, skipping.")
                    return {}
                raise RuntimeError(f"403 Forbidden — check your API key / subscription plan.\nURL: {url}")


            logger.warning(
                "HTTP %d for %s (attempt %d/%d)",
                resp.status_code, url, attempt, retries,
            )
            time.sleep(5 * attempt)

        except requests.exceptions.RequestException as exc:
            logger.warning("Request error: %s (attempt %d/%d)", exc, attempt, retries)
            time.sleep(5 * attempt)

    raise RuntimeError(f"Failed to fetch {url} after {retries} retries")


# ── Paginator ─────────────────────────────────────────────────
def paginate(url: str, params: Optional[dict] = None) -> list:
    """
    Iterate all pages of a Polygon v3 list endpoint.
    Returns the concatenated `results` list across all pages.

    Polygon embeds all query params (except apiKey) in `next_url`,
    so we only inject apiKey for subsequent pages.
    """
    if params is None:
        params = {}
    params = dict(params)
    params.setdefault("limit", 1000)

    MAX_PAGES = 200   # safety cap — raises if exceeded

    results: list = []
    next_url: Optional[str] = url
    first_page = True
    page = 0

    while next_url:
        page += 1
        if page > MAX_PAGES:
            logger.warning(
                "paginate() hit MAX_PAGES (%d) — possible infinite loop, stopping early. "
                "%d records collected so far.",
                MAX_PAGES, len(results),
            )
            break

        data = get_json(next_url, params if first_page else None)
        batch = data.get("results") or []
        results.extend(batch)
        next_url   = data.get("next_url")   # None when no more pages
        first_page = False
        logger.info(
            "Paginating… page %d | %d records so far%s",
            page, len(results),
            " (last page)" if not next_url else "",
        )

    return results


# ── Weekday Generator ─────────────────────────────────────────
def all_weekdays(start: str, end: str) -> list:
    """
    Return every Monday–Friday between `start` and `end` (inclusive).
    Dates are returned as YYYY-MM-DD strings.
    Actual market holidays are handled by treating empty API responses
    as closed-market days (see fetch_daily.py).
    """
    s = datetime.strptime(start, "%Y-%m-%d").date()
    e = datetime.strptime(end,   "%Y-%m-%d").date()
    out = []
    cur = s
    while cur <= e:
        if cur.weekday() < 5:       # 0 = Mon … 4 = Fri
            out.append(cur.strftime("%Y-%m-%d"))
        cur += timedelta(days=1)
    return out
