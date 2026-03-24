"""
deps.py — FastAPI dependency injection helpers.

Shared across all route files: DB connection, institution lookup, period resolution.
"""

from typing import Any, Generator, Optional

from fastapi import Depends, HTTPException
from sqlalchemy.engine import Connection
from sqlalchemy.sql import text

from backend.app.core.database import engine


# ---------------------------------------------------------------------------
# DB dependency — one connection per request
# ---------------------------------------------------------------------------

def _get_conn() -> Generator[Connection, None, None]:
    try:
        conn = engine.connect()
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Database unavailable. Run setup_db.py first. ({exc})",
        )
    try:
        yield conn
    finally:
        conn.close()


def get_conn(conn: Connection = Depends(_get_conn)) -> Connection:
    return conn


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def _row_to_dict(row) -> dict[str, Any]:
    return dict(row._mapping)


def _require_institution(conn: Connection, institution_id: int) -> dict:
    row = conn.execute(
        text("SELECT id, cik, name, display_name FROM institutions WHERE id = :id"),
        {"id": institution_id},
    ).mappings().fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"Institution {institution_id} not found.")
    return dict(row)


def _resolve_period(
    conn: Connection,
    institution_id: int,
    period: Optional[str],
) -> dict:
    """
    Return the filings row for the given institution + period.
    If period is None, use the most recent filing.
    """
    if period:
        row = conn.execute(
            text("""
            SELECT id, period_of_report, filing_date, accession_number
            FROM filings
            WHERE institution_id = :inst_id AND period_of_report = :period
            """),
            {"inst_id": institution_id, "period": period},
        ).mappings().fetchone()
        if row is None:
            raise HTTPException(
                status_code=404,
                detail=f"No filing found for institution {institution_id} and period '{period}'.",
            )
    else:
        row = conn.execute(
            text("""
            SELECT id, period_of_report, filing_date, accession_number
            FROM filings
            WHERE institution_id = :inst_id
            ORDER BY period_of_report DESC
            LIMIT 1
            """),
            {"inst_id": institution_id},
        ).mappings().fetchone()
        if row is None:
            raise HTTPException(
                status_code=404,
                detail=f"No filings found for institution {institution_id}.",
            )
    return dict(row)
