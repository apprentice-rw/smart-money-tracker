"""GET /tickers — CUSIP → ticker map with in-memory cache."""

import threading
import time
from typing import Optional

from fastapi import APIRouter, HTTPException
from sqlalchemy.sql import text

from backend.app.core.database import engine

router = APIRouter()

# Module-level cache — intentionally bypasses get_conn DI so a single
# long-lived connection isn't held open for the TTL duration.
_ticker_cache: Optional[dict] = None
_ticker_cache_ts: float = 0.0
_ticker_cache_lock = threading.Lock()
_TICKER_TTL = 3600  # seconds


@router.get("/tickers", tags=["meta"])
def get_tickers() -> dict:
    """
    Return CUSIP → ticker mapping from the cusip_ticker_map table.
    The table is populated (and periodically refreshed) by running:
        PYTHONPATH=. python backend/scripts/resolve_cusips.py
    Results are cached in memory for one hour so the DB is not hit on
    every page load.
    """
    global _ticker_cache, _ticker_cache_ts

    # Fast path — no lock needed for a read of an already-populated cache.
    if _ticker_cache is not None and (time.time() - _ticker_cache_ts) < _TICKER_TTL:
        return _ticker_cache

    # Slow path — acquire lock so only one thread hits the DB on cache miss.
    with _ticker_cache_lock:
        # Re-check inside the lock (another thread may have refreshed while we waited).
        if _ticker_cache is not None and (time.time() - _ticker_cache_ts) < _TICKER_TTL:
            return _ticker_cache

        try:
            conn = engine.connect()
        except Exception as exc:
            raise HTTPException(status_code=503, detail=f"Database unavailable: {exc}")

        try:
            rows = conn.execute(
                text("SELECT cusip, ticker, company_name, source FROM cusip_ticker_map WHERE ticker IS NOT NULL")
            ).fetchall()
        finally:
            conn.close()

        tickers = {r[0]: {"ticker": r[1], "name": r[2], "source": r[3]} for r in rows}
        _ticker_cache = {"tickers": tickers}
        _ticker_cache_ts = time.time()
        return _ticker_cache
