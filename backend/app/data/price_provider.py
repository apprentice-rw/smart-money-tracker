"""
price_provider.py — Historical daily price bar fetching.

V1 uses Yahoo Finance via yfinance. To swap providers:
  1. Subclass PriceProvider
  2. Implement fetch_history()
  3. Pass your new class to fetch_prices.py

Design note: the YahooPriceProvider uses auto_adjust=True so the 'Close'
column returned by yfinance already reflects split and dividend adjustments.
adj_close is set equal to close for consistency with the PriceBar contract.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class PriceBar:
    date: str                    # YYYY-MM-DD
    close: float                 # split/dividend-adjusted close (for YahooProvider)
    adj_close: Optional[float]   # same as close when auto_adjust=True
    volume: Optional[int]        # None if not available or zero


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

    Uses Ticker.history(auto_adjust=True) so 'Close' is always the
    split/dividend-adjusted price. Volume is set to None when yfinance
    returns 0 (uninformative for VWAC weighting).
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
                auto_adjust=True,
                actions=False,
            )

            if df is None or df.empty:
                return []

            bars: list[PriceBar] = []
            for idx, row in df.iterrows():
                try:
                    close_val = float(row["Close"])
                    vol = int(row["Volume"]) if row["Volume"] > 0 else None
                except (KeyError, TypeError, ValueError):
                    continue
                bars.append(
                    PriceBar(
                        date=idx.strftime("%Y-%m-%d"),
                        close=close_val,
                        adj_close=close_val,  # auto_adjust=True: Close is already adjusted
                        volume=vol,
                    )
                )
            return bars
        except Exception:
            return []
