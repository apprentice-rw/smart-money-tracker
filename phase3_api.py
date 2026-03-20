"""
Phase 3 — FastAPI Backend
Serves smart_money.db (built by phase2_setup_db.py) via REST endpoints.
Also serves the React frontend as static files at /app.
"""

import json
import os
import threading
import time
from pathlib import Path as FilePath
from typing import Any, Generator, Optional

from fastapi import Depends, FastAPI, HTTPException, Path, Query
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

_DEFAULT_ORIGINS = [
    "https://smart-money-tracker-vxr6.vercel.app",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
]

# ALLOWED_ORIGINS env var overrides the default list.
# Set it to a comma-separated list of origins, e.g.:
#   ALLOWED_ORIGINS=https://myapp.vercel.app,https://preview.vercel.app
_raw_origins = os.environ.get("ALLOWED_ORIGINS", "")
_ALLOWED_ORIGINS = (
    [o.strip() for o in _raw_origins.split(",") if o.strip()]
    if _raw_origins
    else _DEFAULT_ORIGINS
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_ALLOWED_ORIGINS,
    allow_methods=["GET"],
    allow_headers=["*"],
)

FRONTEND_DIR = FilePath(__file__).parent / "frontend" / "dist"

# Serve the built React frontend at /app.
# Run `cd frontend && npm run build` first to populate frontend/dist/.
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
    counts = {
        "institutions":    conn.execute(text("SELECT COUNT(*) FROM institutions")).scalar(),
        "filings":         conn.execute(text("SELECT COUNT(*) FROM filings")).scalar(),
        "holdings":        conn.execute(text("SELECT COUNT(*) FROM holdings")).scalar(),
        "position_changes": conn.execute(text("SELECT COUNT(*) FROM position_changes")).scalar(),
    }
    return {
        "status": "ok",
        "database": engine.url.drivername.split("+")[0],
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
# GET /stock/{cusip}/history
# ---------------------------------------------------------------------------

@app.get("/stock/{cusip}/history", tags=["history"])
def get_stock_history(
    cusip: str = Path(description="9-character CUSIP"),
    conn: Connection = Depends(get_conn),
) -> dict:
    """
    Quarter-by-quarter holdings history for a CUSIP across all tracked institutions.
    portfolio_weight is the position's value as a fraction of total portfolio value
    for that quarter.  Ordered oldest → newest.
    """
    rows = conn.execute(
        text("""
        SELECT
            h.cusip,
            h.issuer_name,
            h.shares,
            h.value,
            f.period_of_report,
            i.id           AS institution_id,
            i.display_name AS institution_name,
            CAST(h.value AS REAL) / NULLIF(
                (SELECT SUM(h2.value) FROM holdings h2 WHERE h2.filing_id = f.id),
                0
            ) AS portfolio_weight
        FROM holdings h
        JOIN filings      f ON f.id = h.filing_id
        JOIN institutions i ON i.id = f.institution_id
        WHERE h.cusip = :cusip
        ORDER BY f.period_of_report ASC, i.id ASC
        """),
        {"cusip": cusip.upper()},
    ).mappings().fetchall()

    if not rows:
        raise HTTPException(
            status_code=404,
            detail=f"No holdings found for CUSIP '{cusip}'.",
        )

    last = rows[-1]  # most recent row for header fields
    return {
        "cusip":       last["cusip"],
        "issuer_name": last["issuer_name"],
        "history":     [dict(r) for r in rows],
    }


# ---------------------------------------------------------------------------
# GET /tickers — read CUSIP→ticker map from DB (populated by cusip_lookup.py)
# ---------------------------------------------------------------------------

_ticker_cache: Optional[dict] = None
_ticker_cache_ts: float = 0.0
_ticker_cache_lock = threading.Lock()
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
                text("SELECT cusip, ticker FROM cusip_ticker_map WHERE ticker IS NOT NULL")
            ).fetchall()
        finally:
            conn.close()

        tickers = {r[0]: r[1] for r in rows}
        _ticker_cache = {"tickers": tickers}
        _ticker_cache_ts = time.time()
        return _ticker_cache


# ---------------------------------------------------------------------------
# Consensus helpers
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# GET /consensus/quarters
# ---------------------------------------------------------------------------

@app.get("/consensus/quarters", tags=["consensus"])
def consensus_quarters(conn: Connection = Depends(get_conn)) -> dict:
    """Return all available quarters across all institutions, newest first."""
    rows = conn.execute(
        text("""
        SELECT period_of_report,
               MIN(filing_date) AS filing_date_min,
               MAX(filing_date) AS filing_date_max
        FROM filings
        GROUP BY period_of_report
        ORDER BY period_of_report DESC
        """)
    ).fetchall()
    return {
        "quarters": [
            {"period": r[0], "filing_date_min": r[1], "filing_date_max": r[2]}
            for r in rows
        ]
    }


# ---------------------------------------------------------------------------
# GET /consensus/holdings
# ---------------------------------------------------------------------------

@app.get("/consensus/holdings", tags=["consensus"])
def consensus_holdings(
    period: Optional[str] = Query(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    min_holders: int = Query(default=2, ge=1),
    limit: int = Query(default=50, ge=1, le=500),
    conn: Connection = Depends(get_conn),
) -> dict:
    """Aggregate holdings across institutions for a given quarter."""
    resolved = _consensus_period(conn, period)

    inst_totals_rows = conn.execute(
        text("""
        SELECT f.institution_id, SUM(h.value) AS total_value
        FROM holdings h
        JOIN filings f ON f.id = h.filing_id
        WHERE f.period_of_report = :period
        GROUP BY f.institution_id
        """),
        {"period": resolved},
    ).fetchall()
    inst_totals = {r[0]: r[1] for r in inst_totals_rows}

    total_institutions = conn.execute(
        text("SELECT COUNT(DISTINCT institution_id) FROM filings WHERE period_of_report = :p"),
        {"p": resolved},
    ).scalar() or 0

    rows = conn.execute(
        text("""
        SELECT
            h.cusip,
            h.issuer_name,
            f.institution_id,
            i.display_name AS institution_name,
            h.value,
            h.shares
        FROM holdings h
        JOIN filings f      ON f.id = h.filing_id
        JOIN institutions i ON i.id = f.institution_id
        WHERE f.period_of_report = :period
        ORDER BY h.cusip
        """),
        {"period": resolved},
    ).fetchall()

    # Aggregate in Python
    agg: dict = {}
    for r in rows:
        cusip = r[0]
        if cusip not in agg:
            agg[cusip] = {
                "cusip": cusip,
                "issuer_name": r[1],
                "total_value": 0,
                "total_shares": 0,
                "institution_ids": set(),
                "holders": [],
            }
        agg[cusip]["institution_ids"].add(r[2])
        agg[cusip]["total_value"] += r[4] or 0
        agg[cusip]["total_shares"] += r[5] or 0
        agg[cusip]["holders"].append({
            "institution_id": r[2],
            "name": r[3],
            "value": r[4],
            "shares": r[5],
            "institution_total_value": inst_totals.get(r[2], 0),
        })

    tickers = _consensus_ticker_map(conn, list(agg.keys()))

    results = []
    for item in agg.values():
        holder_count = len(item["institution_ids"])
        if holder_count < min_holders:
            continue
        results.append({
            "cusip": item["cusip"],
            "issuer_name": item["issuer_name"],
            "ticker": tickers.get(item["cusip"]),
            "holder_count": holder_count,
            "total_value": item["total_value"],
            "total_shares": item["total_shares"],
            "holders": item["holders"],
        })

    results.sort(key=lambda x: (-x["holder_count"], -x["total_value"]))
    results = results[:limit]

    return {
        "period": resolved,
        "total_institutions": total_institutions,
        "results": results,
    }


# ---------------------------------------------------------------------------
# GET /consensus/buying
# ---------------------------------------------------------------------------

@app.get("/consensus/buying", tags=["consensus"])
def consensus_buying(
    period: Optional[str] = Query(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    min_buyers: int = Query(default=2, ge=1),
    limit: int = Query(default=50, ge=1, le=500),
    conn: Connection = Depends(get_conn),
) -> dict:
    """Stocks being bought (new or increased) by multiple institutions."""
    resolved = _consensus_period(conn, period)
    prev = _consensus_prev_period(conn, resolved)

    inst_totals_rows = conn.execute(
        text("""
        SELECT f.institution_id, SUM(h.value) AS total_value
        FROM holdings h
        JOIN filings f ON f.id = h.filing_id
        WHERE f.period_of_report = :period
        GROUP BY f.institution_id
        """),
        {"period": resolved},
    ).fetchall()
    inst_totals = {r[0]: r[1] for r in inst_totals_rows}

    rows = conn.execute(
        text("""
        SELECT
            pc.cusip,
            pc.issuer_name,
            pc.change_type,
            pc.curr_value,
            pc.curr_shares,
            pc.prev_value,
            pc.prev_shares,
            pc.shares_pct,
            pc.shares_delta,
            pc.institution_id,
            i.display_name AS institution_name
        FROM position_changes pc
        JOIN filings cf     ON cf.id = pc.curr_filing_id
        JOIN institutions i ON i.id  = pc.institution_id
        WHERE cf.period_of_report = :period
          AND pc.change_type IN ('new', 'increased')
        ORDER BY pc.cusip
        """),
        {"period": resolved},
    ).fetchall()

    agg: dict = {}
    for r in rows:
        cusip = r[0]
        if cusip not in agg:
            agg[cusip] = {
                "cusip": cusip,
                "issuer_name": r[1],
                "total_curr_value": 0,
                "institution_ids": set(),
                "buyers": [],
            }
        agg[cusip]["institution_ids"].add(r[9])
        agg[cusip]["total_curr_value"] += r[3] or 0
        agg[cusip]["buyers"].append({
            "institution_id": r[9],
            "name": r[10],
            "change_type": r[2],
            "curr_value": r[3],
            "shares_pct": r[7],
            "shares_delta": r[8],
            "institution_total_value": inst_totals.get(r[9], 0),
        })

    tickers = _consensus_ticker_map(conn, list(agg.keys()))

    results = []
    for item in agg.values():
        buyer_count = len(item["institution_ids"])
        if buyer_count < min_buyers:
            continue
        results.append({
            "cusip": item["cusip"],
            "issuer_name": item["issuer_name"],
            "ticker": tickers.get(item["cusip"]),
            "buyer_count": buyer_count,
            "total_curr_value": item["total_curr_value"],
            "buyers": item["buyers"],
        })

    results.sort(key=lambda x: (-x["buyer_count"], -x["total_curr_value"]))
    results = results[:limit]

    return {
        "period": resolved,
        "prev_period": prev,
        "results": results,
    }


# ---------------------------------------------------------------------------
# GET /consensus/selling
# ---------------------------------------------------------------------------

@app.get("/consensus/selling", tags=["consensus"])
def consensus_selling(
    period: Optional[str] = Query(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    min_sellers: int = Query(default=2, ge=1),
    limit: int = Query(default=50, ge=1, le=500),
    conn: Connection = Depends(get_conn),
) -> dict:
    """Stocks being sold (closed or decreased) by multiple institutions."""
    resolved = _consensus_period(conn, period)
    prev = _consensus_prev_period(conn, resolved)

    inst_totals_rows = conn.execute(
        text("""
        SELECT f.institution_id, SUM(h.value) AS total_value
        FROM holdings h
        JOIN filings f ON f.id = h.filing_id
        WHERE f.period_of_report = :period
        GROUP BY f.institution_id
        """),
        {"period": resolved},
    ).fetchall()
    inst_totals = {r[0]: r[1] for r in inst_totals_rows}

    rows = conn.execute(
        text("""
        SELECT
            pc.cusip,
            pc.issuer_name,
            pc.change_type,
            pc.curr_value,
            pc.curr_shares,
            pc.prev_value,
            pc.prev_shares,
            pc.shares_pct,
            pc.shares_delta,
            pc.institution_id,
            i.display_name AS institution_name
        FROM position_changes pc
        JOIN filings cf     ON cf.id = pc.curr_filing_id
        JOIN institutions i ON i.id  = pc.institution_id
        WHERE cf.period_of_report = :period
          AND pc.change_type IN ('closed', 'decreased')
        ORDER BY pc.cusip
        """),
        {"period": resolved},
    ).fetchall()

    agg: dict = {}
    for r in rows:
        cusip = r[0]
        if cusip not in agg:
            agg[cusip] = {
                "cusip": cusip,
                "issuer_name": r[1],
                "total_prev_value": 0,
                "institution_ids": set(),
                "sellers": [],
            }
        agg[cusip]["institution_ids"].add(r[9])
        agg[cusip]["total_prev_value"] += r[5] or 0
        agg[cusip]["sellers"].append({
            "institution_id": r[9],
            "name": r[10],
            "change_type": r[2],
            "prev_value": r[5],
            "curr_value": r[3],
            "shares_pct": r[7],
            "shares_delta": r[8],
            "institution_total_value": inst_totals.get(r[9], 0),
        })

    tickers = _consensus_ticker_map(conn, list(agg.keys()))

    results = []
    for item in agg.values():
        seller_count = len(item["institution_ids"])
        if seller_count < min_sellers:
            continue
        results.append({
            "cusip": item["cusip"],
            "issuer_name": item["issuer_name"],
            "ticker": tickers.get(item["cusip"]),
            "seller_count": seller_count,
            "total_prev_value": item["total_prev_value"],
            "sellers": item["sellers"],
        })

    results.sort(key=lambda x: (-x["seller_count"], -x["total_prev_value"]))
    results = results[:limit]

    return {
        "period": resolved,
        "prev_period": prev,
        "results": results,
    }


# ---------------------------------------------------------------------------
# GET /consensus/emerging
# ---------------------------------------------------------------------------

@app.get("/consensus/emerging", tags=["consensus"])
def consensus_emerging(
    period: Optional[str] = Query(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    limit: int = Query(default=50, ge=1, le=500),
    conn: Connection = Depends(get_conn),
) -> dict:
    """Stocks gaining new institutional holders vs the prior quarter."""
    resolved = _consensus_period(conn, period)
    prev = _consensus_prev_period(conn, resolved)
    if not prev:
        raise HTTPException(
            404,
            "No previous quarter available — this is the oldest filing in the database.",
        )

    curr_rows = conn.execute(
        text("""
        SELECT h.cusip, h.issuer_name,
               COUNT(DISTINCT f.institution_id) AS holder_count,
               SUM(h.value) AS total_value
        FROM holdings h
        JOIN filings f ON f.id = h.filing_id
        WHERE f.period_of_report = :period
        GROUP BY h.cusip, h.issuer_name
        """),
        {"period": resolved},
    ).fetchall()

    prev_rows = conn.execute(
        text("""
        SELECT h.cusip, COUNT(DISTINCT f.institution_id) AS holder_count
        FROM holdings h
        JOIN filings f ON f.id = h.filing_id
        WHERE f.period_of_report = :prev
        GROUP BY h.cusip
        """),
        {"prev": prev},
    ).fetchall()

    prev_map = {r[0]: r[1] for r in prev_rows}

    results = []
    for r in curr_rows:
        cusip, issuer_name, curr_holders, total_value = r[0], r[1], r[2], r[3]
        prev_holders = prev_map.get(cusip, 0)
        delta = curr_holders - prev_holders
        if delta > 0:
            results.append({
                "cusip": cusip,
                "issuer_name": issuer_name,
                "curr_holders": curr_holders,
                "prev_holders": prev_holders,
                "holder_delta": delta,
                "total_value": total_value or 0,
            })

    results.sort(key=lambda x: (-x["holder_delta"], -x["curr_holders"]))
    results = results[:limit]

    tickers = _consensus_ticker_map(conn, [r["cusip"] for r in results])
    for r in results:
        r["ticker"] = tickers.get(r["cusip"])

    return {
        "period": resolved,
        "prev_period": prev,
        "results": results,
    }


# ---------------------------------------------------------------------------
# GET /consensus/persistent
# ---------------------------------------------------------------------------

@app.get("/consensus/persistent", tags=["consensus"])
def consensus_persistent(
    min_quarters: int = Query(default=4, ge=1),
    min_holders: int = Query(default=2, ge=1),
    limit: int = Query(default=50, ge=1, le=500),
    conn: Connection = Depends(get_conn),
) -> dict:
    """Stocks held persistently across many quarters by multiple institutions."""
    total_quarters = conn.execute(
        text("SELECT COUNT(DISTINCT period_of_report) FROM filings")
    ).scalar() or 0

    latest_period = conn.execute(
        text("SELECT period_of_report FROM filings ORDER BY period_of_report DESC LIMIT 1")
    ).fetchone()
    if not latest_period:
        raise HTTPException(404, "No filings in database")
    latest = latest_period[0]

    rows = conn.execute(
        text("""
        SELECT
            h.cusip,
            h.issuer_name,
            f.institution_id,
            i.display_name AS institution_name,
            COUNT(DISTINCT f.period_of_report) AS quarters_held
        FROM holdings h
        JOIN filings f      ON f.id = h.filing_id
        JOIN institutions i ON i.id = f.institution_id
        GROUP BY h.cusip, h.issuer_name, f.institution_id, i.display_name
        ORDER BY h.cusip
        """),
    ).fetchall()

    # Institution total portfolio values for latest period
    inst_totals_rows = conn.execute(
        text("""
        SELECT f.institution_id, SUM(h.value) AS total_value
        FROM holdings h
        JOIN filings f ON f.id = h.filing_id
        WHERE f.period_of_report = :latest
        GROUP BY f.institution_id
        """),
        {"latest": latest},
    ).fetchall()
    inst_totals = {r[0]: r[1] for r in inst_totals_rows}

    # Group by cusip
    agg: dict = {}
    for r in rows:
        cusip, issuer_name, inst_id, inst_name, qheld = r[0], r[1], r[2], r[3], r[4]
        if cusip not in agg:
            agg[cusip] = {"cusip": cusip, "issuer_name": issuer_name, "holders": []}
        agg[cusip]["holders"].append({
            "institution_id": inst_id,
            "name": inst_name,
            "quarters_held": qheld,
            "institution_total_value": inst_totals.get(inst_id, 0),
        })

    # Latest value lookup
    latest_value_rows = conn.execute(
        text("""
        SELECT h.cusip, SUM(h.value) AS total_value
        FROM holdings h
        JOIN filings f ON f.id = h.filing_id
        WHERE f.period_of_report = :latest
        GROUP BY h.cusip
        """),
        {"latest": latest},
    ).fetchall()
    latest_values = {r[0]: r[1] for r in latest_value_rows}

    tickers_needed = list(agg.keys())
    tickers = _consensus_ticker_map(conn, tickers_needed)

    results = []
    for item in agg.values():
        qualifying = [h for h in item["holders"] if h["quarters_held"] >= min_quarters]
        if len(qualifying) < min_holders:
            continue
        max_qheld = max(h["quarters_held"] for h in qualifying)
        results.append({
            "cusip": item["cusip"],
            "issuer_name": item["issuer_name"],
            "ticker": tickers.get(item["cusip"]),
            "persistent_holder_count": len(qualifying),
            "max_quarters_held": max_qheld,
            "latest_total_value": latest_values.get(item["cusip"], 0),
            "holders": qualifying,
        })

    results.sort(key=lambda x: (-x["persistent_holder_count"], -x["max_quarters_held"]))
    results = results[:limit]

    return {
        "min_quarters": min_quarters,
        "total_quarters_available": total_quarters,
        "results": results,
    }


# ---------------------------------------------------------------------------
# Dev entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("phase3_api:app", host="127.0.0.1", port=8000, reload=True)
