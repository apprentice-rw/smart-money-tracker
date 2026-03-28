"""
setup_db.py — Database setup entry point.

Thin wrapper around backend.app.data.etl.

Usage:
    # Standard 2-year refresh (8 quarters, all institutions):
    PYTHONPATH=. python backend/scripts/setup_db.py

    # Cost-basis deep backfill (40 quarters / 10 years, high-turnover managers excluded):
    PYTHONPATH=. python backend/scripts/setup_db.py \\
        --quarters 40 --cost-basis-exclude

    # Custom depth + manual exclusion list:
    PYTHONPATH=. python backend/scripts/setup_db.py \\
        --quarters 20 --exclude "Soros Fund Management,Bridgewater Associates"
"""

import argparse
import sys
import os

# Ensure project root is in sys.path when run directly
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backend.app.core.database import engine
from backend.app.data.etl import (
    apply_schema, run_etl, print_verification, wipe_db,
    NUM_QUARTERS, COST_BASIS_QUARTERS, COST_BASIS_EXCLUDE,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Smart Money Tracker — wipe and rebuild the database from SEC EDGAR."
    )
    parser.add_argument(
        "--quarters", type=int, default=None,
        help=(
            f"Number of 13F quarters to backfill per institution "
            f"(default: {NUM_QUARTERS}; use {COST_BASIS_QUARTERS} for cost-basis depth)"
        ),
    )
    parser.add_argument(
        "--exclude", default="",
        help="Comma-separated institution names to skip (case-sensitive, exact match)",
    )
    parser.add_argument(
        "--cost-basis-exclude", action="store_true",
        help=(
            "Skip high-turnover managers unsuitable for cost-basis modelling: "
            + ", ".join(sorted(COST_BASIS_EXCLUDE))
        ),
    )
    args = parser.parse_args()

    # Build exclusion set
    exclude: set = set()
    if args.cost_basis_exclude:
        exclude.update(COST_BASIS_EXCLUDE)
    if args.exclude:
        for name in args.exclude.split(","):
            name = name.strip()
            if name:
                exclude.add(name)

    num_quarters = args.quarters if args.quarters is not None else NUM_QUARTERS

    print(f"Smart Money Tracker — Database Setup")
    print(f"Target:   {engine.url}")
    print(f"Quarters: {num_quarters}")
    if exclude:
        print(f"Excluded: {', '.join(sorted(exclude))}")
    print()

    wipe_db()

    with engine.connect() as conn:
        apply_schema(conn)

    run_etl(num_quarters=num_quarters, exclude=exclude)

    with engine.connect() as conn:
        print(f"\n{'=' * 55}")
        print("  ETL complete — running verification ...")
        print_verification(conn)

    # Resolve any new CUSIPs that aren't yet in the ticker cache
    print(f"\n{'=' * 55}")
    print("  Resolving new CUSIPs via OpenFIGI ...")
    print(f"{'=' * 55}")
    try:
        from backend.app.data.cusip_lookup import build_cusip_ticker_map
        build_cusip_ticker_map(resolve_all=False)
    except Exception as exc:
        print(f"  WARNING: CUSIP lookup failed — run resolve_cusips.py manually. ({exc})")


if __name__ == "__main__":
    main()
