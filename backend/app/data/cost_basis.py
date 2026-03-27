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


# ---------------------------------------------------------------------------
# 3. Rolling Average Cost engine
# ---------------------------------------------------------------------------

def compute_institution_cost_basis(institution_id: int, conn: Connection) -> int:
    """
    Walk all (cusip, period) position-change rows for *institution_id* in
    chronological order and compute an estimated average cost per share using
    Average Cost (WAC) accounting.

    State transition rules:
      new       → avg_cost = quarter_buy_price
      increased → avg_cost = (prev_shares*prev_cost + delta*buy_price) / curr_shares
                  (if prev_cost is None: stored as None — position predates our window)
      decreased → avg_cost = prev_avg_cost  (Average Cost: cost unchanged on partial sale)
      unchanged → avg_cost = prev_avg_cost
      closed    → avg_cost = NULL; shares = 0

    If ticker is unresolved or price data is absent for a buy event, avg_cost
    is stored as NULL with price_source = NULL.

    Returns the number of rows upserted.
    """
    rows = conn.execute(
        text("""
        SELECT
            pc.cusip,
            pc.issuer_name,
            pc.change_type,
            pc.prev_shares,
            pc.curr_shares,
            cf.period_of_report  AS period,
            m.ticker
        FROM position_changes pc
        JOIN filings cf ON cf.id = pc.curr_filing_id
        LEFT JOIN cusip_ticker_map m ON m.cusip = pc.cusip
        WHERE pc.institution_id = :inst_id
        ORDER BY cf.period_of_report ASC, pc.cusip ASC
        """),
        {"inst_id": institution_id},
    ).mappings().fetchall()

    # running_cost: cusip -> avg_cost_per_share (None = unknown / position closed)
    running_cost: dict[str, Optional[float]] = {}
    written = 0

    for row in rows:
        cusip       = row["cusip"]
        period      = row["period"]
        change_type = row["change_type"]
        prev_shares = row["prev_shares"] or 0
        curr_shares = row["curr_shares"] or 0
        ticker      = row["ticker"]
        issuer_name = row["issuer_name"] or ""

        prev_cost = running_cost.get(cusip)  # None if first seen or after close

        # Fetch quarter buy price only when shares are being acquired
        quarter_buy_price: Optional[float] = None
        if change_type in ("new", "increased"):
            quarter_buy_price = get_quarter_price(ticker, period, conn)

        # Apply Average Cost state transition
        if change_type == "closed":
            new_cost = None

        elif change_type == "new":
            new_cost = quarter_buy_price  # None if no price available

        elif change_type == "increased":
            delta = curr_shares - prev_shares
            if quarter_buy_price is not None and prev_cost is not None:
                new_cost = (prev_shares * prev_cost + delta * quarter_buy_price) / curr_shares
            else:
                # Cannot update: prior cost unknown or price unavailable
                new_cost = prev_cost

        else:  # decreased, unchanged
            new_cost = prev_cost  # Average Cost: cost unchanged on partial sale / hold

        # Derived fields
        total_cost = (new_cost * curr_shares) if (new_cost is not None and curr_shares > 0) else None
        price_src  = "yahoo" if (quarter_buy_price is not None and change_type in ("new", "increased")) else None

        conn.execute(
            text("""
            INSERT INTO estimated_cost_basis (
                institution_id, cusip, period, ticker, issuer_name, shares,
                avg_cost_per_share, total_cost_basis,
                quarter_buy_price, change_type, price_source
            ) VALUES (
                :inst_id, :cusip, :period, :ticker, :issuer, :shares,
                :avg_cost, :total_cost,
                :buy_price, :ctype, :src
            )
            ON CONFLICT(institution_id, cusip, period) DO UPDATE SET
                ticker             = excluded.ticker,
                issuer_name        = excluded.issuer_name,
                shares             = excluded.shares,
                avg_cost_per_share = excluded.avg_cost_per_share,
                total_cost_basis   = excluded.total_cost_basis,
                quarter_buy_price  = excluded.quarter_buy_price,
                change_type        = excluded.change_type,
                price_source       = excluded.price_source,
                computed_at        = CURRENT_TIMESTAMP
            """),
            {
                "inst_id":    institution_id,
                "cusip":      cusip,
                "period":     period,
                "ticker":     ticker,
                "issuer":     issuer_name,
                "shares":     curr_shares,
                "avg_cost":   new_cost,
                "total_cost": total_cost,
                "buy_price":  quarter_buy_price,
                "ctype":      change_type,
                "src":        price_src,
            },
        )
        written += 1
        running_cost[cusip] = new_cost

    conn.commit()
    return written
