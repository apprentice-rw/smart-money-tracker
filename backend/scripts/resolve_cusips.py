"""
resolve_cusips.py — CUSIP → ticker resolution entry point.

Thin wrapper around backend.app.data.cusip_lookup.

Usage:
    PYTHONPATH=. python backend/scripts/resolve_cusips.py            # resolve only new CUSIPs
    PYTHONPATH=. python backend/scripts/resolve_cusips.py --all      # re-resolve everything
    PYTHONPATH=. python backend/scripts/resolve_cusips.py --report   # coverage stats, no fetching

Set OPENFIGI_API_KEY in .env for 250 req/min (vs 25 req/min without key).
"""

import argparse
import sys
import os

# Ensure project root is in sys.path when run directly
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backend.app.data.cusip_lookup import build_cusip_ticker_map, print_coverage_report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Resolve holdings CUSIPs to tickers via OpenFIGI + name fallback"
    )
    parser.add_argument(
        "--all", action="store_true",
        help="Re-resolve all CUSIPs (default: only new ones not yet in the table)",
    )
    parser.add_argument(
        "--report", action="store_true",
        help="Show current coverage stats without making any API calls",
    )
    args = parser.parse_args()

    if args.report:
        print_coverage_report()
    else:
        build_cusip_ticker_map(resolve_all=args.all)
