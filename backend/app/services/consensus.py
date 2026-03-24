"""
consensus.py — Shared helpers for consensus endpoints.

Extracted from phase3_api.py to eliminate duplication across the 3 consensus
aggregation endpoints (buying, selling, emerging) that share identical patterns.
"""

from typing import Optional

from fastapi import HTTPException
from sqlalchemy.engine import Connection
from sqlalchemy.sql import text


def _consensus_period(conn: Connection, period: Optional[str] = None) -> str:
    """Resolve period for consensus endpoints (not institution-specific)."""
    if period:
        exists = conn.execute(
            text("SELECT 1 FROM filings WHERE period_of_report = :p LIMIT 1"),
            {"p": period},
        ).fetchone()
        if not exists:
            raise HTTPException(404, f"No filings for period {period}")
        return period
    row = conn.execute(
        text("SELECT period_of_report FROM filings ORDER BY period_of_report DESC LIMIT 1")
    ).fetchone()
    if not row:
        raise HTTPException(404, "No filings in database")
    return row[0]


def _consensus_prev_period(conn: Connection, period: str) -> Optional[str]:
    """Return the quarter immediately before `period`, or None."""
    row = conn.execute(
        text(
            "SELECT period_of_report FROM filings "
            "WHERE period_of_report < :p ORDER BY period_of_report DESC LIMIT 1"
        ),
        {"p": period},
    ).fetchone()
    return row[0] if row else None


def _consensus_ticker_map(conn: Connection, cusips: list) -> dict:
    """Batch-resolve CUSIPs to tickers. Returns empty dict if table missing."""
    if not cusips:
        return {}
    try:
        placeholders = ", ".join(f":c{i}" for i in range(len(cusips)))
        params = {f"c{i}": c for i, c in enumerate(cusips)}
        rows = conn.execute(
            text(f"SELECT cusip, ticker FROM cusip_ticker_map WHERE cusip IN ({placeholders})"),
            params,
        ).fetchall()
        return {r[0]: r[1] for r in rows if r[1]}
    except Exception:
        return {}
