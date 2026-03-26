"""Consensus endpoints: quarters, holdings, buying, selling, emerging, persistent."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.engine import Connection
from sqlalchemy.sql import text

from backend.app.api.deps import get_conn
from backend.app.services.consensus import (
    _consensus_period,
    _consensus_prev_period,
    _consensus_ticker_map,
    _inst_totals,
)

router = APIRouter()


@router.get("/consensus/quarters", tags=["consensus"])
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


@router.get("/consensus/holdings", tags=["consensus"])
def consensus_holdings(
    period: Optional[str] = Query(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    min_holders: int = Query(default=2, ge=1),
    limit: int = Query(default=50, ge=1, le=500),
    conn: Connection = Depends(get_conn),
) -> dict:
    """Aggregate holdings across institutions for a given quarter."""
    resolved = _consensus_period(conn, period)
    inst_totals = _inst_totals(conn, resolved)

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


@router.get("/consensus/buying", tags=["consensus"])
def consensus_buying(
    period: Optional[str] = Query(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    min_buyers: int = Query(default=2, ge=1),
    limit: int = Query(default=50, ge=1, le=500),
    conn: Connection = Depends(get_conn),
) -> dict:
    """Stocks being bought (new or increased) by multiple institutions."""
    resolved = _consensus_period(conn, period)
    prev = _consensus_prev_period(conn, resolved)
    inst_totals = _inst_totals(conn, resolved)

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


@router.get("/consensus/selling", tags=["consensus"])
def consensus_selling(
    period: Optional[str] = Query(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    min_sellers: int = Query(default=2, ge=1),
    limit: int = Query(default=50, ge=1, le=500),
    conn: Connection = Depends(get_conn),
) -> dict:
    """Stocks being sold (closed or decreased) by multiple institutions."""
    resolved = _consensus_period(conn, period)
    prev = _consensus_prev_period(conn, resolved)
    inst_totals = _inst_totals(conn, resolved)

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


@router.get("/consensus/emerging", tags=["consensus"])
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


@router.get("/consensus/persistent", tags=["consensus"])
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

    inst_totals = _inst_totals(conn, latest)

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
