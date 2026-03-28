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

from datetime import date
from typing import Optional

from sqlalchemy.engine import Connection
from sqlalchemy.sql import text


# ---------------------------------------------------------------------------
# 1. Quarter price proxy formula
# ---------------------------------------------------------------------------

def _compute_vwac(bars: list[dict]) -> Optional[float]:
    """
    Volume-Weighted Average Close (VWAC) using unadjusted close prices.

    V1 computes VWAC on the unadjusted basis: Σ(close_i × volume_i) / Σ(volume_i).
    Both inputs (unadjusted close and raw volume) are on the same per-share unit,
    so the formula is internally consistent across quarters that include stock splits.

    adj_close is stored in price_history but is NOT used here — pairing adj_close
    with raw volume would be inconsistent around splits (pre-split bars would have
    a lower adjusted price but the same raw share count, understating their weight
    relative to post-split bars).

    Falls back to arithmetic mean of close when total volume is zero or None.
    Returns None if bars is empty or all close values are missing.
    """
    effective_closes = [
        b.get("close") or b.get("adj_close")
        for b in bars
        if b.get("close") or b.get("adj_close")
    ]
    if not effective_closes:
        return None

    total_volume = sum(b.get("volume") or 0 for b in bars)
    if total_volume > 0:
        weighted = sum(
            (b.get("close") or b.get("adj_close") or 0.0) * (b.get("volume") or 0)
            for b in bars
        )
        return weighted / total_volume

    # Fallback: arithmetic mean
    return sum(effective_closes) / len(effective_closes)


# ---------------------------------------------------------------------------
# 2. Quarter representative price — reads from price_history in DB
# ---------------------------------------------------------------------------

def _quarter_start(period_dt: date) -> date:
    """
    Return the first day of the calendar quarter that ends on *period_dt*.

    Standard 13F quarter-end dates and their quarter starts:
      YYYY-03-31 → YYYY-01-01   (Q1)
      YYYY-06-30 → YYYY-04-01   (Q2)
      YYYY-09-30 → YYYY-07-01   (Q3)
      YYYY-12-31 → YYYY-10-01   (Q4)
    """
    quarter_start_month = ((period_dt.month - 1) // 3) * 3 + 1
    return date(period_dt.year, quarter_start_month, 1)


# ---------------------------------------------------------------------------
# 2b. Split ratio lookup
# ---------------------------------------------------------------------------

def _get_cumulative_split_ratio(
    ticker: str,
    after_period: str,
    up_to_period: str,
    conn: Connection,
) -> float:
    """
    Return the product of all split ratios for *ticker* with effective date
    strictly after *after_period* and on or before *up_to_period*.

    Returns 1.0 if no splits exist in the interval (the common case).

    Example: a 2:1 split (ratio=2.0) and a 3:2 split (ratio=1.5) in the same
    interval yield a cumulative ratio of 3.0.
    """
    rows = conn.execute(
        text("""
        SELECT ratio FROM stock_splits
        WHERE ticker = :t
          AND date >  :after
          AND date <= :upto
        ORDER BY date ASC
        """),
        {"t": ticker, "after": after_period, "upto": up_to_period},
    ).fetchall()
    result = 1.0
    for r in rows:
        result *= r[0]
    return result


def get_quarter_price(
    ticker: Optional[str],
    period: str,
    conn: Connection,
) -> Optional[float]:
    """
    Returns the quarter representative buy price for (ticker, period).

    Reads from the price_history table — no network calls at query time.
    The quarter window is the exact calendar quarter that ends on *period*:
      [quarter_start, period]  — e.g. 2024-01-01 to 2024-03-31 for Q1 2024.
    The result is in unadjusted price terms (see _compute_vwac docstring).

    Returns None if:
      - ticker is None (CUSIP not resolved)
      - no price_history rows exist for the ticker in the window
      - _compute_vwac returns None (all-missing data)
    """
    if not ticker:
        return None

    period_dt = date.fromisoformat(period)
    start_dt = _quarter_start(period_dt)

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
    Average Cost (WAC) accounting with split awareness.

    Split-adjustment rule (applied before each state transition):
      1. Query stock_splits for all split events between prev_period and curr_period.
      2. Compute cumulative_ratio = Π(ratio_i).
      3. Adjust running state:
           split_adj_prev_shares = round(prev_shares × cumulative_ratio)
           prev_cost             = prev_cost / cumulative_ratio
      4. Compute effective_delta = curr_shares - split_adj_prev_shares.
         Only treat a positive effective_delta as a true buy.

    State transitions (after split adjustment):
      new                       → avg_cost = quarter_buy_price
      closed                    → avg_cost = NULL
      effective_delta > 0       → WAC blend: (adj_prev × prev_cost + delta × buy_price) / curr
      effective_delta <= 0      → avg_cost = prev_cost (split-only, hold, or partial sell)

    If ticker is unresolved or price data is absent for a buy event, avg_cost
    is stored as NULL with price_source = NULL.

    Remaining V1 approximations:
      - Exact intra-quarter trade dates are unknown (13F is a snapshot).
      - Split + discretionary trading in the same interval requires approximation:
        shares beyond the split-adjusted count are treated as bought at the quarter VWAC.
      - Fractional shares from odd-ratio splits are rounded to the nearest integer.

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
            pf.period_of_report  AS prev_period,
            m.ticker
        FROM position_changes pc
        JOIN  filings cf ON cf.id = pc.curr_filing_id
        LEFT JOIN filings pf ON pf.id = pc.prev_filing_id
        LEFT JOIN cusip_ticker_map m ON m.cusip = pc.cusip
        WHERE pc.institution_id = :inst_id
        ORDER BY cf.period_of_report ASC, pc.cusip ASC
        """),
        {"inst_id": institution_id},
    ).mappings().fetchall()

    # running_cost: cusip -> avg_cost_per_share in current split-adjusted terms
    running_cost: dict[str, Optional[float]] = {}
    written = 0

    for row in rows:
        cusip        = row["cusip"]
        period       = row["period"]
        prev_period  = row["prev_period"]   # None only if prev_filing is missing (shouldn't happen)
        change_type  = row["change_type"]
        prev_shares  = row["prev_shares"] or 0
        curr_shares  = row["curr_shares"] or 0
        ticker       = row["ticker"]
        issuer_name  = row["issuer_name"] or ""

        prev_cost = running_cost.get(cusip)  # cost from prior quarter (already split-adjusted)

        # ---------------------------------------------------------------
        # Split adjustment
        # Applies to all continuing positions (not "new" — no prior state to adjust).
        # For "closed", splits happened but cost will be NULL regardless; skip for cleanliness.
        # ---------------------------------------------------------------
        split_ratio = 1.0
        if ticker and prev_period and change_type not in ("new", "closed"):
            split_ratio = _get_cumulative_split_ratio(ticker, prev_period, period, conn)

        if split_ratio != 1.0:
            # Rescale running cost to the new post-split per-share basis
            if prev_cost is not None:
                prev_cost = prev_cost / split_ratio
            # Rescale prev_shares to post-split equivalent for delta comparison
            # round() handles minor floating-point imprecision on odd ratios
            prev_shares = int(round(prev_shares * split_ratio))

        # ---------------------------------------------------------------
        # Quarter representative buy price (only fetched when needed)
        # ---------------------------------------------------------------
        quarter_buy_price: Optional[float] = None

        # ---------------------------------------------------------------
        # Apply state transition
        # ---------------------------------------------------------------
        if change_type == "closed":
            new_cost = None

        elif change_type == "new":
            quarter_buy_price = get_quarter_price(ticker, period, conn)
            new_cost = quarter_buy_price  # None if no price available

        else:
            # increased / decreased / unchanged — recalculate effective delta
            # after split adjustment. split_ratio=1.0 → behaviour identical to old engine.
            effective_delta = curr_shares - prev_shares  # prev_shares already split-adjusted above

            if effective_delta > 0:
                # True buy (beyond what splits explain)
                quarter_buy_price = get_quarter_price(ticker, period, conn)
                if quarter_buy_price is not None and curr_shares > 0:
                    if prev_cost is not None:
                        # Normal WAC blend: weight old cost by prior shares, new buy at VWAC
                        new_cost = (
                            prev_shares * prev_cost
                            + effective_delta * quarter_buy_price
                        ) / curr_shares
                    else:
                        # Bootstrap: no prior cost recorded (position existed before our
                        # earliest filing so the engine never saw a "new" event).
                        # Treat the full current position as entered at quarter_buy_price.
                        # This is the same approximation used for the "new" branch.
                        new_cost = quarter_buy_price
                else:
                    # Price unavailable — leave cost unknown
                    new_cost = prev_cost
            else:
                # Split-only, hold, or partial sell: Average Cost unchanged
                new_cost = prev_cost

        # ---------------------------------------------------------------
        # Derived fields and upsert
        # ---------------------------------------------------------------
        total_cost = (new_cost * curr_shares) if (new_cost is not None and curr_shares > 0) else None
        price_src  = "yahoo" if quarter_buy_price is not None else None

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
