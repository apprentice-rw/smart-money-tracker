"""
price_provider.py — Historical daily price bar fetching.

V1 uses Yahoo Finance via yfinance. To swap providers:
  1. Subclass PriceProvider
  2. Implement fetch_history()
  3. Pass your new class to fetch_prices.py

Price / volume basis (Yahoo Finance):
    We use auto_adjust=False so yfinance returns both 'Close' (unadjusted)
    and 'Adj Close' (split+dividend-adjusted), plus raw Volume.

    Stored fields:
      close     — unadjusted close (the price actually printed that day)
      adj_close — split+dividend-adjusted close from 'Adj Close' column
      volume    — raw unadjusted share count

    The quarter VWAC (_compute_vwac) is computed as:
        Σ(adj_close × volume) / Σ(volume)

    This pairs adjusted prices with raw volumes. It is consistent for
    quarters without intra-period splits or large special dividends (the
    common case for quarterly 13F-tracked positions). For intra-quarter
    splits the volume denominator is slightly understated for pre-split
    bars, which is a documented V1 approximation. A fully rigorous
    treatment would require deriving split-adjusted volume from corporate
    action history, which is left for a future provider.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class PriceBar:
    date: str                    # YYYY-MM-DD
    close: float                 # unadjusted close
    adj_close: Optional[float]   # split+dividend-adjusted close; None if unavailable
    volume: Optional[int]        # raw unadjusted share count; None if zero or unavailable


class PriceProvider(ABC):
    @abstractmethod
    def fetch_history(self, ticker: str, start: str, end: str) -> list[PriceBar]:
        """
        Fetch daily price bars for *ticker* from *start* to *end* (both inclusive,
        YYYY-MM-DD format). Returns an empty list if the ticker is not found or
        no data exists in the requested range. Never raises on missing data.
        """


class YahooPriceProvider(PriceProvider):
    """
    Yahoo Finance price provider via the yfinance library.

    Uses auto_adjust=False to get explicit unadjusted Close, Adj Close,
    and raw Volume columns. See module docstring for the price/volume basis
    rationale.
    """

    def fetch_history(self, ticker: str, start: str, end: str) -> list[PriceBar]:
        try:
            import yfinance as yf
            from datetime import date, timedelta

            # yfinance history() end is exclusive — add one day
            end_exclusive = (
                date.fromisoformat(end) + timedelta(days=1)
            ).isoformat()

            ticker_obj = yf.Ticker(ticker)
            df = ticker_obj.history(
                start=start,
                end=end_exclusive,
                auto_adjust=False,
                actions=False,
            )

            if df is None or df.empty:
                return []

            bars: list[PriceBar] = []
            for idx, row in df.iterrows():
                try:
                    close_val = float(row["Close"])
                    # "Adj Close" may not be present in all yfinance versions
                    adj_val = float(row["Adj Close"]) if "Adj Close" in row.index else close_val
                    vol = int(row["Volume"]) if row["Volume"] > 0 else None
                except (KeyError, TypeError, ValueError):
                    continue
                bars.append(
                    PriceBar(
                        date=idx.strftime("%Y-%m-%d"),
                        close=close_val,
                        adj_close=adj_val,
                        volume=vol,
                    )
                )
            return bars
        except Exception:
            return []
