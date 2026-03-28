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
        Σ(close_i × volume_i) / Σ(volume_i)

    Both inputs are on the same unadjusted basis — close is the actual market
    price that day, volume is the raw share count that day — so the formula
    is internally consistent across the entire quarter, including around
    stock-split events. The result is the historical volume-weighted average
    price per share in the unadjusted price basis.

    adj_close is stored for future use (e.g. a V2 provider that applies
    split-adjusted volume normalization) but is not used in V1 VWAC.
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


@dataclass
class SplitEvent:
    date: str    # YYYY-MM-DD, effective date of the split
    ratio: float # post_shares / pre_shares; 2.0 = 2-for-1 forward, 0.5 = 1-for-2 reverse


class PriceProvider(ABC):
    @abstractmethod
    def fetch_history(self, ticker: str, start: str, end: str) -> list[PriceBar]:
        """
        Fetch daily price bars for *ticker* from *start* to *end* (both inclusive,
        YYYY-MM-DD format). Returns an empty list if the ticker is not found or
        no data exists in the requested range. Never raises on missing data.
        """

    @abstractmethod
    def fetch_splits(self, ticker: str, start: str, end: str) -> list["SplitEvent"]:
        """
        Fetch stock split events for *ticker* with effective date between *start*
        and *end* (both inclusive, YYYY-MM-DD). Returns an empty list when no
        splits exist in the range. Never raises on missing data.

        ratio = post_shares / pre_shares:
          2.0  — 2-for-1 forward split (shares double, price halves)
          0.5  — 1-for-2 reverse split (shares halve, price doubles)
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

    def fetch_splits(self, ticker: str, start: str, end: str) -> list[SplitEvent]:
        """
        Retrieves split history via yfinance Ticker.splits (a pandas Series
        indexed by date with ratio values). Filters to the requested date range.
        """
        try:
            import yfinance as yf
            ticker_obj = yf.Ticker(ticker)
            splits = ticker_obj.splits  # pandas Series; empty if no splits
            if splits is None or splits.empty:
                return []
            result: list[SplitEvent] = []
            for dt, ratio in splits.items():
                date_str = (
                    dt.strftime("%Y-%m-%d") if hasattr(dt, "strftime") else str(dt)[:10]
                )
                if start <= date_str <= end and ratio > 0:
                    result.append(SplitEvent(date=date_str, ratio=float(ratio)))
            return result
        except Exception:
            return []
