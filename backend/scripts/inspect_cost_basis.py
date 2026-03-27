"""
inspect_cost_basis.py — Print estimated cost basis timeline for manual validation.

Use this to compare our computed numbers against external references (e.g. HedgeFollow).

Usage:
    PYTHONPATH=. python backend/scripts/inspect_cost_basis.py --institution-id 1
    PYTHONPATH=. python backend/scripts/inspect_cost_basis.py --institution "Berkshire Hathaway"
    PYTHONPATH=. python backend/scripts/inspect_cost_basis.py --institution-id 1 --ticker AAPL
    PYTHONPATH=. python backend/scripts/inspect_cost_basis.py --institution-id 1 --cusip 037833100
    PYTHONPATH=. python backend/scripts/inspect_cost_basis.py --institution-id 1 --ticker AAPL --csv
"""

import argparse
import csv
import sys

from sqlalchemy.sql import text

from backend.app.core.database import engine


def _resolve_institution_id(conn, args) -> int:
    if args.institution_id:
        row = conn.execute(
            text("SELECT id FROM institutions WHERE id = :i"),
            {"i": args.institution_id},
        ).fetchone()
        if not row:
            print(f"Institution id={args.institution_id} not found.", file=sys.stderr)
            sys.exit(1)
        return row[0]

    row = conn.execute(
        text("SELECT id FROM institutions WHERE name LIKE :n OR display_name LIKE :n LIMIT 1"),
        {"n": f"%{args.institution}%"},
    ).fetchone()
    if not row:
        print(f"Institution matching '{args.institution}' not found.", file=sys.stderr)
        sys.exit(1)
    return row[0]


def main():
    parser = argparse.ArgumentParser(
        description="Inspect estimated cost basis for one institution."
    )
    grp = parser.add_mutually_exclusive_group(required=True)
    grp.add_argument("--institution-id", type=int, help="Institution database id")
    grp.add_argument("--institution",    help="Institution name (partial match)")
    parser.add_argument("--ticker", help="Filter to this ticker symbol")
    parser.add_argument("--cusip",  help="Filter to this CUSIP")
    parser.add_argument("--csv",    action="store_true", help="Output as CSV instead of table")
    args = parser.parse_args()

    with engine.connect() as conn:
        inst_id = _resolve_institution_id(conn, args)

        inst_name = conn.execute(
            text("SELECT display_name FROM institutions WHERE id = :i"), {"i": inst_id}
        ).fetchone()[0]

        filters  = ["ecb.institution_id = :inst_id"]
        params   = {"inst_id": inst_id}

        if args.ticker:
            filters.append("ecb.ticker = :ticker")
            params["ticker"] = args.ticker.upper()
        if args.cusip:
            filters.append("ecb.cusip = :cusip")
            params["cusip"] = args.cusip.upper()

        where = " AND ".join(filters)
        rows = conn.execute(text(f"""
            SELECT
                ecb.period,
                ecb.ticker,
                ecb.cusip,
                ecb.issuer_name,
                ecb.shares,
                ecb.avg_cost_per_share,
                ecb.total_cost_basis,
                ecb.quarter_buy_price,
                ecb.change_type,
                ecb.price_source
            FROM estimated_cost_basis ecb
            WHERE {where}
            ORDER BY ecb.ticker ASC, ecb.period ASC
        """), params).mappings().fetchall()

    if not rows:
        print("No cost basis data found. Run compute_cost_basis.py first.")
        sys.exit(0)

    COLS = [
        "period", "ticker", "cusip", "issuer_name", "shares",
        "avg_cost_per_share", "total_cost_basis", "quarter_buy_price",
        "change_type", "price_source",
    ]

    if args.csv:
        writer = csv.DictWriter(sys.stdout, fieldnames=COLS)
        writer.writeheader()
        for r in rows:
            writer.writerow({c: r[c] for c in COLS})
        return

    # Table output
    print(f"\nEstimated Cost Basis — {inst_name}")
    print(f"{'─' * 110}")
    header = (
        f"{'Period':<12}  {'Ticker':<8}  {'Shares':>12}  "
        f"{'AvgCost':>10}  {'TotalCost':>16}  "
        f"{'BuyPrice':>10}  {'Change':<12}  {'Src':<6}  {'Issuer'}"
    )
    print(header)
    print("─" * 110)
    for r in rows:
        avg   = f"${r['avg_cost_per_share']:>9.2f}" if r["avg_cost_per_share"] is not None else f"{'N/A':>10}"
        total = f"${r['total_cost_basis']:>14,.0f}" if r["total_cost_basis"] is not None else f"{'N/A':>16}"
        buy   = f"${r['quarter_buy_price']:>9.2f}" if r["quarter_buy_price"] is not None else f"{'—':>10}"
        src   = r["price_source"] or "—"
        print(
            f"{r['period']:<12}  {(r['ticker'] or '?'):<8}  {r['shares']:>12,}  "
            f"{avg}  {total}  "
            f"{buy}  {(r['change_type'] or '?'):<12}  {src:<6}  {r['issuer_name'] or ''}"
        )
    print()


if __name__ == "__main__":
    main()
