"""
fetch_prices.py — Fetch and cache Yahoo Finance daily price bars for all
known tickers into the price_history table.

Usage:
    PYTHONPATH=. python backend/scripts/fetch_prices.py
    PYTHONPATH=. python backend/scripts/fetch_prices.py --ticker AAPL
    PYTHONPATH=. python backend/scripts/fetch_prices.py --years 5

Run AFTER resolve_cusips.py so cusip_ticker_map is populated.
"""

import argparse
import sys
from datetime import date, timedelta

from sqlalchemy.sql import text

from backend.app.core.database import engine
from backend.app.data.price_provider import YahooPriceProvider

DEFAULT_YEARS = 3  # covers 8 quarters + buffer


def _get_tickers(conn, only_ticker):
    if only_ticker:
        return [only_ticker.upper()]
    rows = conn.execute(
        text("SELECT DISTINCT ticker FROM cusip_ticker_map WHERE ticker IS NOT NULL")
    ).fetchall()
    return sorted(r[0] for r in rows)


def _store_bars(conn, ticker, bars):
    if not bars:
        return 0
    conn.execute(
        text("""
        INSERT INTO price_history (ticker, date, close, adj_close, volume, source)
        VALUES (:ticker, :date, :close, :adj_close, :volume, :source)
        ON CONFLICT (ticker, date) DO NOTHING
        """),
        [
            {
                "ticker":    ticker,
                "date":      b.date,
                "close":     b.close,
                "adj_close": b.adj_close,
                "volume":    b.volume,
                "source":    "yahoo",
            }
            for b in bars
        ],
    )
    conn.commit()
    return len(bars)


def main():
    parser = argparse.ArgumentParser(
        description="Fetch Yahoo Finance price history into price_history table."
    )
    parser.add_argument("--ticker", help="Only fetch this ticker (default: all resolved tickers)")
    parser.add_argument("--years", type=int, default=DEFAULT_YEARS,
                        help=f"Years of history to fetch (default: {DEFAULT_YEARS})")
    args = parser.parse_args()

    today = date.today()
    end_date   = today.isoformat()
    start_date = today.replace(year=today.year - args.years).isoformat()

    with engine.connect() as conn:
        tickers = _get_tickers(conn, args.ticker)

    if not tickers:
        print("No tickers found in cusip_ticker_map. Run resolve_cusips.py first.")
        sys.exit(1)

    print(f"Fetching price history for {len(tickers)} ticker(s)  "
          f"({start_date} → {end_date}) ...")

    provider = YahooPriceProvider()
    total_rows = 0
    errors = []

    for i, ticker in enumerate(tickers, 1):
        try:
            bars = provider.fetch_history(ticker, start_date, end_date)
            with engine.connect() as conn:
                n = _store_bars(conn, ticker, bars)
            total_rows += n
            print(f"  [{i:>4}/{len(tickers)}]  {ticker:<12}  {n:>6} bars stored")
        except Exception as exc:
            errors.append((ticker, str(exc)))
            print(f"  [{i:>4}/{len(tickers)}]  {ticker:<12}  ERROR: {exc}")

    print(f"\nDone.  {total_rows:,} price bars stored.  {len(errors)} error(s).")
    if errors:
        print("Errors:")
        for t, e in errors:
            print(f"  {t}: {e}")


if __name__ == "__main__":
    main()
