"""
cost_basis.py — Quarter price proxy and rolling Average Cost engine.

Three concerns are kept strictly separate:

  1. _compute_vwac()                 — formula for quarter price proxy
  2. get_quarter_price()             — reads price_history from DB; calls _compute_vwac
  3. compute_institution_cost_basis() — rolling Average Cost engine (added in Task 4)

To swap the proxy formula: only change _compute_vwac().
To swap the price source:  only change fetch_prices.py + price_provider.py.
The rolling engine in (3) calls (2) and is unaffected by either change.
"""

from datetime import date, timedelta
from typing import Optional

from sqlalchemy.engine import Connection
from sqlalchemy.sql import text


# ---------------------------------------------------------------------------
# 1. Quarter price proxy formula
# ---------------------------------------------------------------------------

def _compute_vwac(bars: list[dict]) -> Optional[float]:
    """
    Volume-Weighted Average Close (VWAC).

    Each bar dict must have 'adj_close' (preferred) or 'close', and 'volume'.
    Falls back to arithmetic mean of adj_close when total volume is zero or None.
    Returns None if bars is empty or all close values are missing.

    Formula: Σ(adj_close_i × volume_i) / Σ(volume_i)
    """
    effective_closes = [
        b.get("adj_close") or b.get("close")
        for b in bars
        if b.get("adj_close") or b.get("close")
    ]
    if not effective_closes:
        return None

    total_volume = sum(b.get("volume") or 0 for b in bars)
    if total_volume > 0:
        weighted = sum(
            (b.get("adj_close") or b.get("close") or 0.0) * (b.get("volume") or 0)
            for b in bars
        )
        return weighted / total_volume

    # Fallback: arithmetic mean
    return sum(effective_closes) / len(effective_closes)


# ---------------------------------------------------------------------------
# 2. Quarter representative price — reads from price_history in DB
# ---------------------------------------------------------------------------

def get_quarter_price(
    ticker: Optional[str],
    period: str,
    conn: Connection,
) -> Optional[float]:
    """
    Returns the quarter representative buy price for (ticker, period).

    Reads from the price_history table — no network calls at query time.
    The quarter window is [period - 95 days, period], which covers an
    approximate calendar quarter for any standard quarter-end date.

    Returns None if:
      - ticker is None (CUSIP not resolved)
      - no price_history rows exist for the ticker in the window
      - _compute_vwac returns None (all-missing data)
    """
    if not ticker:
        return None

    period_dt = date.fromisoformat(period)
    start_dt = period_dt - timedelta(days=95)

    rows = conn.execute(
        text("""
        SELECT adj_close, close, volume
        FROM price_history
        WHERE ticker = :ticker
          AND date >= :start
          AND date <= :end
        ORDER BY date ASC
        """),
        {"ticker": ticker, "start": start_dt.isoformat(), "end": period},
    ).mappings().fetchall()

    if not rows:
        return None

    return _compute_vwac([dict(r) for r in rows])
