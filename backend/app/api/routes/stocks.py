"""Stock endpoints: search and per-CUSIP history."""

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy.engine import Connection
from sqlalchemy.sql import text

from backend.app.api.deps import get_conn

router = APIRouter()


@router.get("/search", tags=["search"])
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


@router.get("/stock/{cusip}/history", tags=["history"])
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
            ) AS portfolio_weight,
            ecb.avg_cost_per_share  AS estimated_avg_cost,
            ecb.total_cost_basis    AS estimated_total_cost
        FROM holdings h
        JOIN filings      f   ON f.id = h.filing_id
        JOIN institutions i   ON i.id = f.institution_id
        LEFT JOIN estimated_cost_basis ecb
               ON ecb.institution_id = i.id
              AND ecb.cusip           = h.cusip
              AND ecb.period          = f.period_of_report
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
