"""
compare_price_sources.py — Print a comparison table of quarter VWAC prices
for a sample of tickers and quarters.

Currently shows Yahoo-derived VWAC from the local price_history table.
Structured so a Polygon or Tiingo column can be appended later.

Usage:
    PYTHONPATH=. python backend/scripts/compare_price_sources.py
    PYTHONPATH=. python backend/scripts/compare_price_sources.py \
        --tickers AAPL,META,NVDA \
        --periods 2024-12-31,2024-09-30
"""

import argparse

from sqlalchemy.sql import text

from backend.app.core.database import engine
from backend.app.data.cost_basis import get_quarter_price


# Default sample — covers a representative set of widely-held stocks
DEFAULT_TICKERS = ["AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOGL", "BRK.B", "JPM"]
DEFAULT_PERIODS = ["2024-12-31", "2024-09-30", "2024-06-30", "2024-03-31"]


def main():
    parser = argparse.ArgumentParser(
        description="Compare quarter price proxy values across sources."
    )
    parser.add_argument("--tickers",
                        help="Comma-separated tickers (default: built-in sample)",
                        default=",".join(DEFAULT_TICKERS))
    parser.add_argument("--periods",
                        help="Comma-separated quarter-end dates (default: last 4 quarters)",
                        default=",".join(DEFAULT_PERIODS))
    args = parser.parse_args()

    tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
    periods = [p.strip() for p in args.periods.split(",") if p.strip()]

    # Column headers — add more sources here when available
    header = f"{'Ticker':<12}  {'Period':<12}  {'Yahoo VWAC':>12}"
    # Future: f"  {'Polygon VWAP':>12}  {'Delta':>10}"
    print(header)
    print("-" * len(header))

    with engine.connect() as conn:
        for period in periods:
            for ticker in tickers:
                yahoo_price = get_quarter_price(ticker, period, conn)

                yahoo_str = f"{yahoo_price:>12.4f}" if yahoo_price is not None else f"{'N/A':>12}"
                # Future: polygon_str = ...

                print(f"{ticker:<12}  {period:<12}  {yahoo_str}")
            print()


if __name__ == "__main__":
    main()
