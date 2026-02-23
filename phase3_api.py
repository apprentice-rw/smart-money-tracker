"""
Phase 3 — FastAPI Backend
Serves smart_money.db (built by phase2_setup_db.py) via REST endpoints.
Also serves the React frontend as static files at /app.
"""

import json
import time
import urllib.request
from pathlib import Path
from typing import Any, Generator, Optional

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy.engine import Connection
from sqlalchemy.sql import text

from db import engine

# ---------------------------------------------------------------------------
# App + CORS
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Smart Money Tracker API",
    description="13F holdings data for institutional investors",
    version="0.4.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

FRONTEND_DIR = Path(__file__).parent / "frontend"

# Serve the React frontend at /app (eliminates cross-origin issues in local dev)
if FRONTEND_DIR.exists():
    app.mount("/app", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")


# ---------------------------------------------------------------------------
# DB dependency — one connection per request
# ---------------------------------------------------------------------------

def _get_conn() -> Generator[Connection, None, None]:
    try:
        conn = engine.connect()
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Database unavailable. Run phase2_setup_db.py first. ({exc})",
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


# ---------------------------------------------------------------------------
# GET /health
# ---------------------------------------------------------------------------

@app.get("/health", tags=["meta"])
def health(conn: Connection = Depends(get_conn)) -> dict:
    """
    Returns database row counts for all tables.
    Useful for confirming the DB is populated and the API can reach it.
    """
    tables = ["institutions", "filings", "holdings", "position_changes"]
    counts = {
        tbl: conn.execute(text(f"SELECT COUNT(*) FROM {tbl}")).fetchone()[0]
        for tbl in tables
    }
    return {
        "status": "ok",
        "database": str(engine.url),
        "row_counts": counts,
    }


# ---------------------------------------------------------------------------
# GET /institutions
# ---------------------------------------------------------------------------

@app.get("/institutions", tags=["institutions"])
def list_institutions(conn: Connection = Depends(get_conn)) -> dict:
    """List all tracked institutions."""
    rows = conn.execute(
        text("SELECT id, cik, name, display_name FROM institutions ORDER BY name")
    ).mappings().fetchall()
    return {"institutions": [dict(r) for r in rows]}


# ---------------------------------------------------------------------------
# GET /institutions/{institution_id}/filings
# ---------------------------------------------------------------------------

@app.get("/institutions/{institution_id}/filings", tags=["institutions"])
def list_filings(institution_id: int, conn: Connection = Depends(get_conn)) -> dict:
    """List all available quarters for a given institution, newest first."""
    inst = _require_institution(conn, institution_id)
    rows = conn.execute(
        text("""
        SELECT id, period_of_report, filing_date, accession_number
        FROM filings
        WHERE institution_id = :inst_id
        ORDER BY period_of_report DESC
        """),
        {"inst_id": institution_id},
    ).mappings().fetchall()
    return {
        "institution": inst,
        "filings": [dict(r) for r in rows],
    }


# ---------------------------------------------------------------------------
# GET /institutions/{institution_id}/holdings
# ---------------------------------------------------------------------------

@app.get("/institutions/{institution_id}/holdings", tags=["holdings"])
def get_holdings(
    institution_id: int,
    period: Optional[str] = Query(
        default=None,
        description="Quarter end date YYYY-MM-DD. Defaults to most recent.",
        pattern=r"^\d{4}-\d{2}-\d{2}$",
    ),
    conn: Connection = Depends(get_conn),
) -> dict:
    """
    Return all holdings for a given institution and quarter, sorted by value descending.
    Omit `period` to get the most recent filing.
    """
    inst = _require_institution(conn, institution_id)
    filing = _resolve_period(conn, institution_id, period)

    rows = conn.execute(
        text("""
        SELECT cusip, issuer_name, shares, value, share_type
        FROM holdings
        WHERE filing_id = :filing_id
        ORDER BY value DESC
        """),
        {"filing_id": filing["id"]},
    ).mappings().fetchall()

    holdings = [dict(r) for r in rows]
    for rank, h in enumerate(holdings, start=1):
        h["rank"] = rank

    total_value = sum(h["value"] for h in holdings)

    return {
        "institution": inst,
        "period_of_report": filing["period_of_report"],
        "filing_date": filing["filing_date"],
        "total_positions": len(holdings),
        "total_value": total_value,
        "holdings": holdings,
    }


# ---------------------------------------------------------------------------
# GET /institutions/{institution_id}/changes
# ---------------------------------------------------------------------------

@app.get("/institutions/{institution_id}/changes", tags=["changes"])
def get_changes(
    institution_id: int,
    period: Optional[str] = Query(
        default=None,
        description=(
            "Quarter end date YYYY-MM-DD for the *current* quarter being compared. "
            "Defaults to most recent."
        ),
        pattern=r"^\d{4}-\d{2}-\d{2}$",
    ),
    include_unchanged: bool = Query(
        default=False,
        description="Include unchanged positions in the response (can be large).",
    ),
    conn: Connection = Depends(get_conn),
) -> dict:
    """
    Return precomputed quarter-over-quarter position changes for an institution.
    Results are grouped by change_type: new, closed, increased, decreased.
    The `period` parameter selects the *current* (newer) quarter of the comparison.
    """
    inst = _require_institution(conn, institution_id)
    curr_filing = _resolve_period(conn, institution_id, period)

    rows = conn.execute(
        text("""
        SELECT
            pc.cusip,
            pc.issuer_name,
            pc.change_type,
            pc.prev_shares,
            pc.curr_shares,
            pc.prev_value,
            pc.curr_value,
            pc.shares_delta,
            pc.shares_pct,
            pf.period_of_report AS prev_period,
            cf.period_of_report AS curr_period
        FROM position_changes pc
        JOIN filings pf ON pf.id = pc.prev_filing_id
        JOIN filings cf ON cf.id = pc.curr_filing_id
        WHERE pc.institution_id = :inst_id
          AND pc.curr_filing_id = :curr_filing_id
        ORDER BY pc.change_type, ABS(COALESCE(pc.shares_pct, 0)) DESC
        """),
        {"inst_id": institution_id, "curr_filing_id": curr_filing["id"]},
    ).mappings().fetchall()

    if not rows:
        raise HTTPException(
            status_code=404,
            detail=(
                f"No position changes found for institution {institution_id} "
                f"with current period '{curr_filing['period_of_report']}'. "
                "This may be the oldest filing in the database — there is no prior "
                "quarter to compare against."
            ),
        )

    prev_period = rows[0]["prev_period"]
    curr_period = rows[0]["curr_period"]

    # Group by change_type
    grouped: dict[str, list[dict]] = {
        "new": [],
        "closed": [],
        "increased": [],
        "decreased": [],
    }
    if include_unchanged:
        grouped["unchanged"] = []

    summary: dict[str, int] = {}

    for row in rows:
        ct = row["change_type"]
        summary[ct] = summary.get(ct, 0) + 1
        if ct in grouped:
            grouped[ct].append(dict(row))

    # Sort each group for useful default ordering
    grouped["new"] = sorted(
        grouped["new"], key=lambda x: x["curr_value"] or 0, reverse=True
    )
    grouped["closed"] = sorted(
        grouped["closed"], key=lambda x: x["prev_value"] or 0, reverse=True
    )
    grouped["increased"] = sorted(
        grouped["increased"],
        key=lambda x: x["shares_pct"] or 0,
        reverse=True,
    )
    grouped["decreased"] = sorted(
        grouped["decreased"],
        key=lambda x: x["shares_pct"] or 0,
    )

    return {
        "institution": inst,
        "prev_period": prev_period,
        "curr_period": curr_period,
        "summary": summary,
        "changes": grouped,
    }


# ---------------------------------------------------------------------------
# GET /search
# ---------------------------------------------------------------------------

@app.get("/search", tags=["search"])
def search_holdings(
    q: str = Query(
        min_length=2,
        description="Search term — matches issuer name (partial) or CUSIP (exact prefix).",
    ),
    limit: int = Query(default=50, ge=1, le=500),
    conn: Connection = Depends(get_conn),
) -> dict:
    """
    Search holdings across all institutions and quarters by issuer name or CUSIP.
    Case-insensitive partial match on name; case-insensitive prefix match on CUSIP.
    Results include institution name and period for context. Sorted by value descending.
    """
    term = q.strip()
    like_term = f"%{term}%"

    rows = conn.execute(
        text("""
        SELECT
            h.cusip,
            h.issuer_name,
            h.shares,
            h.value,
            h.share_type,
            f.period_of_report,
            f.filing_date,
            i.id   AS institution_id,
            i.name AS institution_name
        FROM holdings h
        JOIN filings      f ON f.id = h.filing_id
        JOIN institutions i ON i.id = f.institution_id
        WHERE LOWER(h.issuer_name) LIKE LOWER(:like_term)
           OR LOWER(h.cusip)       LIKE LOWER(:like_term)
        ORDER BY h.value DESC
        LIMIT :limit
        """),
        {"like_term": like_term, "limit": limit},
    ).mappings().fetchall()

    return {
        "query": term,
        "result_count": len(rows),
        "results": [dict(r) for r in rows],
    }


# ---------------------------------------------------------------------------
# GET /tickers — read CUSIP→ticker map from DB (populated by cusip_lookup.py)
# ---------------------------------------------------------------------------

_ticker_cache: Optional[dict] = None
_ticker_cache_ts: float = 0.0
_TICKER_TTL = 3600  # seconds


@app.get("/tickers", tags=["meta"])
def get_tickers() -> dict:
    """
    Return CUSIP → ticker mapping from the cusip_ticker_map table.
    The table is populated (and periodically refreshed) by running:
        python3 cusip_lookup.py
    Results are cached in memory for one hour so the DB is not hit on
    every page load.
    """
    global _ticker_cache, _ticker_cache_ts

    if _ticker_cache is not None and (time.time() - _ticker_cache_ts) < _TICKER_TTL:
        return _ticker_cache

    try:
        conn = engine.connect()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Database unavailable: {exc}")

    try:
        rows = conn.execute(
            text("SELECT cusip, ticker FROM cusip_ticker_map WHERE ticker IS NOT NULL")
        ).fetchall()
    finally:
        conn.close()

    tickers = {r[0]: r[1] for r in rows}
    _ticker_cache = {"tickers": tickers}
    _ticker_cache_ts = time.time()
    return _ticker_cache


# ---------------------------------------------------------------------------
# Dev entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("phase3_api:app", host="127.0.0.1", port=8000, reload=True)
