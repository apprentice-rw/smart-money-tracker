# Estimated Cost Basis — V1 Design Spec

**Date:** 2026-03-26
**Status:** Approved
**Scope:** Per-institution, per-stock, per-quarter estimated average cost basis (remaining position only)

---

## Overview

This feature adds an *Estimated Cost Basis* engine to Smart Money Tracker.

**What it is:** A model-derived estimate of the average price an institution paid per share for its current remaining position in a given stock, computed from quarterly 13F snapshots and historical market prices.

**What it is not:**
- Not a reconstruction of actual trade prices (13F filings report end-of-quarter positions only, not individual trade dates or prices)
- Not FIFO lot tracking — V1 uses **Average Cost** accounting only
- Not a realised P&L or exit-price tracker
- Not an aggregate cross-institution metric (V1 is per-institution only)
- Not a cash-balance model

**Accounting method:** Average Cost (WAC)
**Price source:** Yahoo Finance historical daily bars via `yfinance`
**Price unit:** Adjusted close price (split-aware)

---

## Model: State Transition Rules

For each `(institution, cusip)` pair, the engine walks quarters in chronological order and applies:

| Change type | Rule |
|---|---|
| **New** (`prev_shares = 0`, `curr_shares > 0`) | `avg_cost = quarter_buy_price` |
| **Increased** (`curr_shares > prev_shares`) | `avg_cost = (prev_shares × prev_cost + delta × quarter_buy_price) / curr_shares` |
| **Decreased** (`curr_shares < prev_shares`, `curr_shares > 0`) | `avg_cost = prev_avg_cost` (unchanged — Average Cost method) |
| **Unchanged** | `avg_cost = prev_avg_cost` (no buy activity, cost unchanged) |
| **Closed** (`curr_shares = 0`) | `avg_cost = NULL` for this period; `last_cost_before_exit` preserved for audit |

`quarter_buy_price` is the representative market price for the quarter (see below). If it is unavailable (no ticker, no price data), `avg_cost` is stored as `NULL` with `price_source = NULL`.

---

## Quarter Representative Price (Proxy)

### V1: Volume-Weighted Average Close (VWAC)

For a given `(ticker, quarter)`:

1. Fetch all daily bars in the quarter window: `[quarter_start_date, period_of_report]`
2. Compute: `Σ(adj_close_i × volume_i) / Σ(volume_i)`
3. Fallback: if `Σ(volume_i) = 0` or volume data is unavailable → arithmetic mean of adj_close values

**Rationale:** VWAC is more realistic than a simple mean — high-volume trading days carry proportionally more weight. It is computed entirely from standard daily OHLCV bars available from Yahoo Finance.

**Limitations / documented assumptions:**
- 13F filings report end-of-quarter positions. The actual trade execution date within the quarter is unknown.
- VWAC over the full quarter approximates the average acquisition price under the assumption that purchases were distributed proportionally to volume throughout the quarter.
- This will be less accurate for large block buys on specific dates.

### Abstraction

The proxy is isolated behind a single function signature:

```python
def get_quarter_price(ticker: str, period: str, conn) -> float | None:
    """
    Returns the quarter representative buy price for (ticker, period).
    period is the quarter-end date as YYYY-MM-DD.
    Returns None if insufficient price data is available.
    """
```

To swap providers (e.g. Polygon VWAP, Tiingo, or direct intraday data), only this function — and the price fetching layer it delegates to — needs to change. The cost-basis engine is isolated from the provider.

---

## Architecture

### New Modules

```
backend/app/data/
  price_provider.py    — PriceProvider ABC + YahooPriceProvider implementation
  cost_basis.py        — Quarter proxy function + rolling average cost engine

backend/app/api/routes/
  cost_basis.py        — New API routes

backend/scripts/
  fetch_prices.py      — CLI: fetch and cache price history for all known tickers

backend/tests/
  test_cost_basis.py   — Unit tests (no network, no DB)
```

### New DB Tables

```sql
-- Daily price bars. Provider-agnostic; supports future Polygon/Tiingo column.
CREATE TABLE price_history (
    ticker      TEXT    NOT NULL,
    date        TEXT    NOT NULL,   -- YYYY-MM-DD
    close       REAL    NOT NULL,
    adj_close   REAL,               -- split/dividend-adjusted; preferred for cost basis
    volume      BIGINT,
    source      TEXT    NOT NULL DEFAULT 'yahoo',
    PRIMARY KEY (ticker, date)
);

-- Precomputed per-institution, per-stock, per-quarter cost basis.
CREATE TABLE estimated_cost_basis (
    id                  BIGSERIAL / AUTOINCREMENT PRIMARY KEY,
    institution_id      INTEGER NOT NULL REFERENCES institutions(id),
    cusip               TEXT    NOT NULL,
    period              TEXT    NOT NULL,   -- quarter-end YYYY-MM-DD
    ticker              TEXT,
    shares              BIGINT  NOT NULL,
    avg_cost_per_share  REAL,               -- NULL if no price available
    total_cost_basis    REAL,               -- avg_cost_per_share × shares (NULL if no price)
    quarter_buy_price   REAL,               -- proxy price used for new/increased buys this quarter
    change_type         TEXT,               -- from position_changes for this quarter
    price_source        TEXT,               -- 'yahoo' | NULL
    computed_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (institution_id, cusip, period)
);
```

Indexes: `(institution_id, period)`, `(cusip)`, `(ticker, date)` on price_history.

---

## Data Flow

```
SEC EDGAR 13F
     │
     ▼
holdings + position_changes   (existing ETL)
     │
     ▼
cusip_ticker_map              (existing resolve_cusips.py)
     │
     ▼
price_history                 (NEW: fetch_prices.py → YahooPriceProvider)
     │
     ▼
estimated_cost_basis          (NEW: cost_basis.py rolling engine)
     │
     ▼
API: GET /stock/{cusip}/history       (EXTENDED: adds avg_cost_per_share per row)
     GET /institutions/{id}/cost-basis  (NEW)
```

### Execution order for a fresh DB

```
1. python backend/scripts/setup_db.py        # existing
2. python backend/scripts/resolve_cusips.py  # existing
3. python backend/scripts/fetch_prices.py    # NEW
4. python backend/scripts/compute_cost_basis.py  # NEW
```

Steps 3 and 4 are incremental / idempotent: re-running adds only missing data.

---

## Price Provider Abstraction

```python
# price_provider.py

class PriceProvider(ABC):
    def fetch_history(self, ticker: str, start: str, end: str) -> list[PriceBar]:
        """Fetch daily OHLCV bars for ticker between start and end (inclusive, YYYY-MM-DD)."""

@dataclass
class PriceBar:
    date: str        # YYYY-MM-DD
    close: float
    adj_close: float | None
    volume: int | None

class YahooPriceProvider(PriceProvider):
    """Uses yfinance. Returns adjusted close from yfinance's 'Adj Close' column."""
```

The `fetch_prices.py` script instantiates `YahooPriceProvider`, iterates all tickers in `cusip_ticker_map`, and populates `price_history`. Future: swap in `PolygonPriceProvider` or `TiingoPriceProvider` by passing a different provider instance.

---

## Rolling Cost-Basis Engine

`cost_basis.py::compute_institution_cost_basis(institution_id, conn)` walks all `(cusip, period)` pairs for that institution in chronological order:

1. Load all `position_changes` rows for the institution, sorted by period.
2. For each period:
   a. Look up `ticker` from `cusip_ticker_map`.
   b. Call `get_quarter_price(ticker, period, conn)` → reads from `price_history` in DB (no network call at compute time).
   c. Apply the state transition rule.
   d. Upsert result into `estimated_cost_basis`.
3. If `ticker` is NULL or `quarter_buy_price` is NULL, store row with `avg_cost_per_share = NULL`.

The engine is a pure function of DB state — no network calls. It can be re-run any time after `fetch_prices.py` has been run.

---

## API Surface

### Extended: `GET /stock/{cusip}/history`

Existing response shape — adds two new nullable fields per history row:

```json
{
  "cusip": "...",
  "issuer_name": "...",
  "history": [
    {
      "institution_id": 1,
      "institution_name": "Berkshire Hathaway",
      "period_of_report": "2025-09-30",
      "shares": 400000000,
      "value": 80000000000,
      "portfolio_weight": 0.42,
      "estimated_avg_cost": 192.34,      // NEW — null if unavailable
      "estimated_total_cost": 76936000000 // NEW — null if unavailable
    }
  ]
}
```

### New: `GET /institutions/{id}/cost-basis`

Returns full cost-basis timeline for one institution across all tracked stocks, newest period first. Supports optional `?period=YYYY-MM-DD` and `?cusip=` filters.

```json
{
  "institution": { "id": 1, "name": "Berkshire Hathaway" },
  "cost_basis": [
    {
      "cusip": "0231351067",
      "ticker": "AAPL",
      "issuer_name": "APPLE INC",
      "period": "2025-09-30",
      "shares": 400000000,
      "avg_cost_per_share": 192.34,
      "total_cost_basis": 76936000000,
      "quarter_buy_price": 215.48,
      "change_type": "decreased",
      "price_source": "yahoo"
    }
  ]
}
```

---

## Tests (`backend/tests/test_cost_basis.py`)

All tests use in-memory SQLite and mock price data — no network calls.

| Test | What it covers |
|---|---|
| `test_quarter_proxy_vwac` | VWAC formula with known daily bars |
| `test_quarter_proxy_fallback` | Falls back to mean close when volume = 0 |
| `test_new_position` | avg_cost = buy price on first entry |
| `test_increased_position` | Weighted average blends old cost + new buy |
| `test_decreased_position` | avg_cost unchanged on partial sale |
| `test_closed_position` | avg_cost = NULL at close, last cost preserved |
| `test_no_price_data` | avg_cost = NULL gracefully when no price available |
| `test_api_cost_basis_endpoint` | Response shape for `/institutions/{id}/cost-basis` |
| `test_stock_history_includes_cost_basis` | `/stock/{cusip}/history` includes new fields |

---

## Comparison Hook (nice-to-have)

`backend/scripts/compare_price_sources.py` — accepts a list of tickers + quarters, prints a table of Yahoo VWAC values. Columns are structured so a `polygon_vwap` column can be appended later without changing the comparison logic.

---

## Dependencies

Add to `requirements.txt`:
```
yfinance>=0.2.54
```

No new runtime dependencies beyond yfinance.

---

## What Remains for V2

| Item | Notes |
|---|---|
| Realised P&L | Need sell price at close time; currently not tracked |
| FIFO lot tracking | More complex engine; `last_cost_before_exit` already preserved for this |
| Cross-institution aggregate cost | Weighted average across institutions for consensus view |
| Polygon/Tiingo price source comparison | Comparison hook already scaffolded |
| Frontend UI surface | StockDrawer chart is the natural home; cost basis line overlay on value/share chart |
| Intraday data for better entry price | Would require a paid data source |
| Periodic price refresh | Cron/trigger to update price_history as new quarters arrive |

---

## Explicit Assumptions

1. **13F is a snapshot, not a trade log.** Entry prices are modelled, not observed.
2. **All purchases in a quarter are modelled as occurring at the quarter VWAC.** Large block buys on specific dates will diverge from this estimate.
3. **Adjusted close is used**, which accounts for stock splits and dividends. This means cost basis estimates are comparable across pre/post-split periods.
4. **Value field in holdings is the SEC-reported market value** (raw USD), not used for cost basis computation — market price is fetched independently from Yahoo.
5. **CUSIP → ticker resolution must be complete** before cost basis can be computed. Positions with unresolved tickers will have `avg_cost_per_share = NULL`.
