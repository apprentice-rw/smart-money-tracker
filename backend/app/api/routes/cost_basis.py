"""cost_basis.py — GET /institutions/{id}/cost-basis endpoint."""

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.engine import Connection
from sqlalchemy.sql import text

from backend.app.api.deps import _require_institution, get_conn

router = APIRouter()


@router.get("/institutions/{institution_id}/cost-basis", tags=["cost-basis"])
def get_cost_basis(
    institution_id: int,
    period: Optional[str] = Query(
        default=None,
        pattern=r"^\d{4}-\d{2}-\d{2}$",
        description="Filter to a single quarter (YYYY-MM-DD).",
    ),
    cusip: Optional[str] = Query(
        default=None,
        description="Filter to a single CUSIP.",
    ),
    conn: Connection = Depends(get_conn),
) -> dict:
    """
    Estimated average cost basis for all positions held by an institution.

    Returns per-(institution, stock, quarter) estimated average cost per share
    computed by the Average Cost engine in cost_basis.py. Rows with
    avg_cost_per_share = null indicate positions where cost basis could not
    be estimated (unresolved CUSIP or missing price data).

    Query parameter behaviour:
      period — restrict to a single quarter-end date
      cusip  — restrict to a single CUSIP
    """
    inst = _require_institution(conn, institution_id)

    filters = ["ecb.institution_id = :inst_id"]
    params: dict = {"inst_id": institution_id}

    if period:
        filters.append("ecb.period = :period")
        params["period"] = period
    if cusip:
        filters.append("ecb.cusip = :cusip")
        params["cusip"] = cusip.upper()

    where_clause = " AND ".join(filters)

    rows = conn.execute(
        text(f"""
        SELECT
            ecb.cusip,
            ecb.ticker,
            ecb.issuer_name,
            ecb.period,
            ecb.shares,
            ecb.avg_cost_per_share,
            ecb.total_cost_basis,
            ecb.quarter_buy_price,
            ecb.change_type,
            ecb.price_source
        FROM estimated_cost_basis ecb
        WHERE {where_clause}
        ORDER BY ecb.period DESC,
                 CASE WHEN ecb.avg_cost_per_share IS NULL THEN 1 ELSE 0 END ASC,
                 ecb.avg_cost_per_share DESC
        """),
        params,
    ).mappings().fetchall()

    return {
        "institution": inst,
        "cost_basis": [dict(r) for r in rows],
    }
