"""
setup_db.py — Database setup entry point.

Thin wrapper around backend.app.data.etl.

Usage:
    PYTHONPATH=. python backend/scripts/setup_db.py
"""

import sys
import os

# Ensure project root is in sys.path when run directly
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backend.app.core.database import engine
from backend.app.data.etl import apply_schema, run_etl, print_verification, wipe_db


def main() -> None:
    print(f"Smart Money Tracker — Database Setup")
    print(f"Target: {engine.url}\n")

    wipe_db()

    with engine.connect() as conn:
        apply_schema(conn)
        run_etl(conn)
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
