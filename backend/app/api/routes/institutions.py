"""Institution endpoints: list, filings, holdings, changes."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.engine import Connection
from sqlalchemy.sql import text

from backend.app.api.deps import (
    _require_institution,
    _resolve_period,
    get_conn,
)

router = APIRouter()


@router.get("/institutions", tags=["institutions"])
def list_institutions(conn: Connection = Depends(get_conn)) -> dict:
    """List all tracked institutions."""
    rows = conn.execute(
        text("SELECT id, cik, name, display_name FROM institutions ORDER BY name")
    ).mappings().fetchall()
    return {"institutions": [dict(r) for r in rows]}


@router.get("/institutions/{institution_id}/filings", tags=["institutions"])
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


@router.get("/institutions/{institution_id}/holdings", tags=["holdings"])
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


@router.get("/institutions/{institution_id}/changes", tags=["changes"])
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

