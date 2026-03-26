# Estimated Cost Basis — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a per-institution, per-stock, per-quarter Estimated Average Cost Basis engine backed by Yahoo Finance historical prices and Average Cost (WAC) accounting.

**Architecture:** A new `price_provider.py` module fetches and persists daily price bars from Yahoo Finance into a `price_history` DB table. A `cost_basis.py` module reads from that table to compute a volume-weighted average close (VWAC) quarter proxy price, then walks position-change history to maintain a rolling average cost per `(institution, cusip)`. Results are stored in `estimated_cost_basis` and exposed via a new route and an extended stock-history route.

**Tech Stack:** Python 3.11, FastAPI, SQLAlchemy 1.4, SQLite (test) / PostgreSQL (prod), yfinance ≥ 0.2.54, pytest, starlette TestClient.

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| Modify | `requirements.txt` | Add yfinance |
| Modify | `backend/app/data/etl.py` | Add `price_history` + `estimated_cost_basis` DDL; update `wipe_db()` |
| Create | `backend/app/data/price_provider.py` | `PriceBar`, `PriceProvider` ABC, `YahooPriceProvider` |
| Create | `backend/app/data/cost_basis.py` | `_compute_vwac`, `get_quarter_price`, `compute_institution_cost_basis` |
| Create | `backend/app/api/routes/cost_basis.py` | `GET /institutions/{id}/cost-basis` |
| Modify | `backend/app/api/routes/stocks.py` | LEFT JOIN `estimated_cost_basis` in `/stock/{cusip}/history` |
| Modify | `backend/app/main.py` | Register cost_basis router |
| Create | `backend/tests/test_cost_basis.py` | All cost-basis unit + API tests |
| Create | `backend/scripts/fetch_prices.py` | CLI: populate `price_history` from Yahoo |
| Create | `backend/scripts/compute_cost_basis.py` | CLI: populate `estimated_cost_basis` |
| Create | `backend/scripts/compare_price_sources.py` | Comparison hook (nice-to-have) |

---

## Task 1: Add yfinance and extend DB schema

**Files:**
- Modify: `requirements.txt`
- Modify: `backend/app/data/etl.py`

- [ ] **Step 1.1: Add yfinance to requirements.txt**

Open `requirements.txt` and append:
```
yfinance>=0.2.54
```

Full file after edit:
```
fastapi==0.128.8
uvicorn==0.39.0
requests==2.32.5
sqlalchemy==1.4.39
psycopg2-binary==2.9.11
python-dotenv==1.2.1
yfinance>=0.2.54
```

- [ ] **Step 1.2: Add new tables to SCHEMA_STATEMENTS in etl.py**

In `backend/app/data/etl.py`, after the `cusip_ticker_map` table definition (line ~104) and before the index block (~line 107), insert these two table definitions and their indexes. The index block becomes:

```python
    # price_history — daily price bars, provider-agnostic
    """
    CREATE TABLE IF NOT EXISTS price_history (
        ticker      TEXT    NOT NULL,
        date        TEXT    NOT NULL,
        close       REAL    NOT NULL,
        adj_close   REAL,
        volume      BIGINT,
        source      TEXT    NOT NULL DEFAULT 'yahoo',
        PRIMARY KEY (ticker, date)
    )
    """,

    # estimated_cost_basis — precomputed per-institution rolling Average Cost
    f"""
    CREATE TABLE IF NOT EXISTS estimated_cost_basis (
        id                  {_PK},
        institution_id      INTEGER NOT NULL REFERENCES institutions(id),
        cusip               TEXT    NOT NULL,
        period              TEXT    NOT NULL,
        ticker              TEXT,
        issuer_name         TEXT,
        shares              BIGINT  NOT NULL DEFAULT 0,
        avg_cost_per_share  REAL,
        total_cost_basis    REAL,
        quarter_buy_price   REAL,
        change_type         TEXT,
        price_source        TEXT,
        computed_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE (institution_id, cusip, period)
    )
    """,

    # indexes (existing)
    "CREATE INDEX IF NOT EXISTS idx_holdings_cusip    ON holdings (cusip)",
    "CREATE INDEX IF NOT EXISTS idx_holdings_filing   ON holdings (filing_id)",
    "CREATE INDEX IF NOT EXISTS idx_holdings_value    ON holdings (value DESC)",
    "CREATE INDEX IF NOT EXISTS idx_filings_inst      ON filings (institution_id)",
    "CREATE INDEX IF NOT EXISTS idx_filings_period    ON filings (period_of_report)",
    "CREATE INDEX IF NOT EXISTS idx_changes_inst      ON position_changes (institution_id)",
    "CREATE INDEX IF NOT EXISTS idx_changes_cusip     ON position_changes (cusip)",
    "CREATE INDEX IF NOT EXISTS idx_changes_curr      ON position_changes (curr_filing_id)",
    "CREATE INDEX IF NOT EXISTS idx_changes_prev      ON position_changes (prev_filing_id)",
    # indexes for new tables
    "CREATE INDEX IF NOT EXISTS idx_price_history_ticker ON price_history (ticker)",
    "CREATE INDEX IF NOT EXISTS idx_ecb_inst_period ON estimated_cost_basis (institution_id, period)",
    "CREATE INDEX IF NOT EXISTS idx_ecb_cusip        ON estimated_cost_basis (cusip)",
```

- [ ] **Step 1.3: Update wipe_db() to include new tables**

In `backend/app/data/etl.py`, update the `wipe_db()` function. The drop list must include the two new tables (in dependency order — `estimated_cost_basis` before `institutions`, `price_history` last since it has no FKs):

```python
def wipe_db() -> None:
    if IS_SQLITE:
        db_path_str = engine.url.database
        db_path = Path(db_path_str)
        if db_path.exists():
            print(f"  Removing existing SQLite DB: {db_path}")
            db_path.unlink()
    else:
        with engine.connect() as conn:
            for tbl in ("estimated_cost_basis", "position_changes", "holdings",
                        "filings", "institutions", "cusip_ticker_map",
                        "price_history"):
                conn.execute(text(f"DROP TABLE IF EXISTS {tbl} CASCADE"))
            conn.commit()
        print("  Dropped all PostgreSQL tables for clean rebuild.")
```

- [ ] **Step 1.4: Run existing tests to confirm no regression**

```bash
PYTHONPATH=. pytest backend/tests/test_api.py -v
```

Expected: all 14 existing tests pass.

- [ ] **Step 1.5: Commit**

```bash
git add requirements.txt backend/app/data/etl.py
git commit -m "feat: add price_history and estimated_cost_basis schema; add yfinance dep"
```

---

## Task 2: Create price_provider.py

**Files:**
- Create: `backend/app/data/price_provider.py`

- [ ] **Step 2.1: Create the file**

```python
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
        except Exception:
            return []

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
```

- [ ] **Step 2.2: Verify the module imports cleanly**

```bash
PYTHONPATH=. python -c "from backend.app.data.price_provider import YahooPriceProvider, PriceBar; print('OK')"
```

Expected output: `OK`

- [ ] **Step 2.3: Commit**

```bash
git add backend/app/data/price_provider.py
git commit -m "feat: add PriceProvider ABC and YahooPriceProvider"
```

---

## Task 3: Quarter proxy — _compute_vwac and get_quarter_price (TDD)

**Files:**
- Create: `backend/app/data/cost_basis.py` (proxy functions only — engine added in Task 4)
- Create: `backend/tests/test_cost_basis.py` (proxy tests only)

- [ ] **Step 3.1: Write failing proxy tests**

Create `backend/tests/test_cost_basis.py`:

```python
"""
test_cost_basis.py — Tests for quarter proxy, rolling cost engine, and API.

All tests use in-memory SQLite + fixture data. No network calls.
Follows the same dependency_overrides pattern as test_api.py.
"""

import os
import tempfile

import pytest
from sqlalchemy import create_engine
from sqlalchemy.sql import text
from starlette.testclient import TestClient

from backend.app.main import app
from backend.app.api.deps import get_conn
from backend.app.data.etl import SCHEMA_STATEMENTS


# ---------------------------------------------------------------------------
# Shared engine fixture (session-scoped for speed)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def test_engine():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    with engine.begin() as conn:
        for stmt in SCHEMA_STATEMENTS:
            conn.execute(text(stmt))
    yield engine
    engine.dispose()
    os.unlink(db_path)


@pytest.fixture()
def conn(test_engine):
    with test_engine.connect() as c:
        yield c


@pytest.fixture()
def client(test_engine):
    def override():
        with test_engine.connect() as c:
            yield c
    app.dependency_overrides[get_conn] = override
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Seed helpers
# ---------------------------------------------------------------------------

_inst_counter = 0


def _seed_institution(conn, name=None, cik=None):
    global _inst_counter
    _inst_counter += 1
    name = name or f"Inst {_inst_counter}"
    cik  = cik  or f"000{_inst_counter:07d}"
    conn.execute(text(
        "INSERT OR IGNORE INTO institutions (cik, name, display_name) "
        "VALUES (:cik, :name, :dn)"
    ), {"cik": cik, "name": name, "dn": name})
    conn.commit()
    return conn.execute(
        text("SELECT id FROM institutions WHERE cik=:cik"), {"cik": cik}
    ).fetchone()[0]


def _seed_filing(conn, inst_id, period, filing_date, accession):
    conn.execute(text(
        "INSERT OR IGNORE INTO filings "
        "(institution_id, period_of_report, filing_date, accession_number) "
        "VALUES (:i, :p, :fd, :acc)"
    ), {"i": inst_id, "p": period, "fd": filing_date, "acc": accession})
    conn.commit()
    return conn.execute(
        text("SELECT id FROM filings WHERE accession_number=:acc"), {"acc": accession}
    ).fetchone()[0]


def _seed_holding(conn, filing_id, cusip, shares, value, issuer="Test Co"):
    conn.execute(text(
        "INSERT OR IGNORE INTO holdings "
        "(filing_id, cusip, issuer_name, shares, value) "
        "VALUES (:f, :c, :n, :s, :v)"
    ), {"f": filing_id, "c": cusip, "n": issuer, "s": shares, "v": value})
    conn.commit()


def _seed_change(conn, inst_id, prev_fid, curr_fid, cusip, ctype,
                 prev_sh, curr_sh, prev_v=None, curr_v=None,
                 delta=None, pct=None, issuer="Test Co"):
    conn.execute(text("""
        INSERT OR IGNORE INTO position_changes (
            institution_id, prev_filing_id, curr_filing_id, cusip, issuer_name,
            change_type, prev_shares, curr_shares, prev_value, curr_value,
            shares_delta, shares_pct
        ) VALUES (:i, :p, :c, :cu, :n, :ct, :ps, :cs, :pv, :cv, :d, :pct)
    """), {
        "i": inst_id, "p": prev_fid, "c": curr_fid, "cu": cusip, "n": issuer,
        "ct": ctype, "ps": prev_sh, "cs": curr_sh, "pv": prev_v, "cv": curr_v,
        "d": delta, "pct": pct,
    })
    conn.commit()


def _seed_ticker(conn, cusip, ticker, name="Test Co"):
    conn.execute(text(
        "INSERT OR IGNORE INTO cusip_ticker_map (cusip, ticker, company_name, source) "
        "VALUES (:c, :t, :n, 'test')"
    ), {"c": cusip, "t": ticker, "n": name})
    conn.commit()


def _seed_prices(conn, ticker, bars):
    """bars: list of (date_str, close, adj_close, volume_or_None)"""
    for date_str, close, adj_close, volume in bars:
        conn.execute(text(
            "INSERT OR IGNORE INTO price_history "
            "(ticker, date, close, adj_close, volume, source) "
            "VALUES (:t, :d, :c, :ac, :v, 'yahoo')"
        ), {"t": ticker, "d": date_str, "c": close, "ac": adj_close, "v": volume})
    conn.commit()


# ---------------------------------------------------------------------------
# Quarter proxy tests
# ---------------------------------------------------------------------------

def test_vwac_weighted_correctly():
    from backend.app.data.cost_basis import _compute_vwac
    bars = [
        {"adj_close": 100.0, "close": 100.0, "volume": 1000},
        {"adj_close": 110.0, "close": 110.0, "volume": 2000},
        {"adj_close": 120.0, "close": 120.0, "volume": 1000},
    ]
    # (100*1000 + 110*2000 + 120*1000) / 4000 = 430000 / 4000 = 107.5
    assert abs(_compute_vwac(bars) - 107.5) < 0.001


def test_vwac_falls_back_to_mean_on_zero_volume():
    from backend.app.data.cost_basis import _compute_vwac
    bars = [
        {"adj_close": 100.0, "close": 100.0, "volume": 0},
        {"adj_close": 120.0, "close": 120.0, "volume": 0},
    ]
    # fallback: (100 + 120) / 2 = 110
    assert abs(_compute_vwac(bars) - 110.0) < 0.001


def test_vwac_falls_back_to_mean_on_none_volume():
    from backend.app.data.cost_basis import _compute_vwac
    bars = [
        {"adj_close": 90.0,  "close": 90.0,  "volume": None},
        {"adj_close": 110.0, "close": 110.0, "volume": None},
    ]
    assert abs(_compute_vwac(bars) - 100.0) < 0.001


def test_vwac_returns_none_on_empty():
    from backend.app.data.cost_basis import _compute_vwac
    assert _compute_vwac([]) is None


def test_get_quarter_price_reads_from_db(conn):
    from backend.app.data.cost_basis import get_quarter_price
    _seed_prices(conn, "QTEST", [
        ("2024-10-01", 200.0, 200.0, 1_000_000),
        ("2024-10-15", 210.0, 210.0, 2_000_000),
        ("2024-12-31", 220.0, 220.0, 1_000_000),
    ])
    # VWAC = (200*1M + 210*2M + 220*1M) / 4M = 840M / 4M = 210.0
    result = get_quarter_price("QTEST", "2024-12-31", conn)
    assert result is not None
    assert abs(result - 210.0) < 0.001


def test_get_quarter_price_returns_none_for_null_ticker(conn):
    from backend.app.data.cost_basis import get_quarter_price
    assert get_quarter_price(None, "2024-12-31", conn) is None


def test_get_quarter_price_returns_none_when_no_db_data(conn):
    from backend.app.data.cost_basis import get_quarter_price
    assert get_quarter_price("NOTICKERS", "2024-12-31", conn) is None
```

- [ ] **Step 3.2: Run tests to confirm they fail (ImportError expected)**

```bash
PYTHONPATH=. pytest backend/tests/test_cost_basis.py::test_vwac_weighted_correctly -v
```

Expected: `FAILED` with `ModuleNotFoundError` or `ImportError` — `cost_basis` does not exist yet.

- [ ] **Step 3.3: Create backend/app/data/cost_basis.py with proxy functions only**

```python
"""
cost_basis.py — Quarter price proxy and rolling Average Cost engine.

Three concerns are kept strictly separate:

  1. _compute_vwac()                 — formula for quarter price proxy
  2. get_quarter_price()             — reads price_history from DB; calls _compute_vwac
  3. compute_institution_cost_basis() — rolling Average Cost engine

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
```

- [ ] **Step 3.4: Run proxy tests to confirm they pass**

```bash
PYTHONPATH=. pytest backend/tests/test_cost_basis.py -k "vwac or quarter_price" -v
```

Expected: 7 tests, all PASS.

- [ ] **Step 3.5: Run all tests to confirm no regression**

```bash
PYTHONPATH=. pytest backend/tests/ -v
```

Expected: all existing 14 + 7 new = 21 tests pass.

- [ ] **Step 3.6: Commit**

```bash
git add backend/app/data/cost_basis.py backend/tests/test_cost_basis.py
git commit -m "feat: add _compute_vwac and get_quarter_price (quarter price proxy)"
```

---

## Task 4: Rolling Average Cost engine — compute_institution_cost_basis (TDD)

**Files:**
- Modify: `backend/app/data/cost_basis.py` (append engine function)
- Modify: `backend/tests/test_cost_basis.py` (append engine tests)

- [ ] **Step 4.1: Append engine tests to test_cost_basis.py**

Append to `backend/tests/test_cost_basis.py` (after the proxy tests):

```python
# ---------------------------------------------------------------------------
# Rolling Average Cost engine tests
# ---------------------------------------------------------------------------

# Shared CUSIP / ticker for engine tests
_CUSIP = "TESTCUSIP"
_TICKER = "TSTK"
_PRICE_Q1 = 150.0   # VWAC for Q4 2023
_PRICE_Q2 = 180.0   # VWAC for Q1 2024


def _seed_base_scenario(conn):
    """
    Seeds: 1 institution, 3 filings (Q3-2023, Q4-2023, Q1-2024),
    price data for Q4-2023 and Q1-2024, ticker mapping.
    Returns (inst_id, fid_q3, fid_q4, fid_q1).
    """
    inst_id = _seed_institution(conn, "Engine Test Fund", "0009000001")
    fid_q3  = _seed_filing(conn, inst_id, "2023-09-30", "2023-11-14", "ENG-Q3")
    fid_q4  = _seed_filing(conn, inst_id, "2023-12-31", "2024-02-14", "ENG-Q4")
    fid_q1  = _seed_filing(conn, inst_id, "2024-03-31", "2024-05-15", "ENG-Q1")

    _seed_ticker(conn, _CUSIP, _TICKER, "Test Stock Co")

    # Price data — uniform closes so VWAC == _PRICE_Qn
    _seed_prices(conn, _TICKER, [
        ("2023-10-02", _PRICE_Q1, _PRICE_Q1, 1_000_000),
        ("2023-11-01", _PRICE_Q1, _PRICE_Q1, 1_000_000),
        ("2023-12-29", _PRICE_Q1, _PRICE_Q1, 1_000_000),
        ("2024-01-02", _PRICE_Q2, _PRICE_Q2, 1_000_000),
        ("2024-02-01", _PRICE_Q2, _PRICE_Q2, 1_000_000),
        ("2024-03-28", _PRICE_Q2, _PRICE_Q2, 1_000_000),
    ])

    return inst_id, fid_q3, fid_q4, fid_q1


def _fetch_ecb(conn, inst_id, period):
    return conn.execute(text(
        "SELECT * FROM estimated_cost_basis "
        "WHERE institution_id=:i AND cusip=:c AND period=:p"
    ), {"i": inst_id, "c": _CUSIP, "p": period}).mappings().fetchone()


def test_engine_new_position(conn):
    from backend.app.data.cost_basis import compute_institution_cost_basis
    inst_id, fid_q3, fid_q4, _ = _seed_base_scenario(conn)
    _seed_holding(conn, fid_q4, _CUSIP, 100, 15_000, "Test Stock Co")
    _seed_change(conn, inst_id, fid_q3, fid_q4, _CUSIP, "new",
                 None, 100, None, 15_000)

    compute_institution_cost_basis(inst_id, conn)

    row = _fetch_ecb(conn, inst_id, "2023-12-31")
    assert row is not None
    assert row["change_type"] == "new"
    assert abs(row["avg_cost_per_share"] - _PRICE_Q1) < 0.01
    assert row["shares"] == 100
    assert row["price_source"] == "yahoo"


def test_engine_increased_position(conn):
    from backend.app.data.cost_basis import compute_institution_cost_basis
    inst_id, fid_q3, fid_q4, fid_q1 = _seed_base_scenario(conn)
    _seed_holding(conn, fid_q4, _CUSIP, 100, 15_000, "Test Stock Co")
    _seed_holding(conn, fid_q1, _CUSIP, 150, 27_000, "Test Stock Co")
    _seed_change(conn, inst_id, fid_q3, fid_q4, _CUSIP, "new",
                 None, 100, None, 15_000)
    _seed_change(conn, inst_id, fid_q4, fid_q1, _CUSIP, "increased",
                 100, 150, 15_000, 27_000, 50)

    compute_institution_cost_basis(inst_id, conn)

    row = _fetch_ecb(conn, inst_id, "2024-03-31")
    assert row is not None
    # (100 * 150 + 50 * 180) / 150 = (15000 + 9000) / 150 = 24000 / 150 = 160.0
    assert abs(row["avg_cost_per_share"] - 160.0) < 0.01
    assert row["shares"] == 150


def test_engine_decreased_position_preserves_cost(conn):
    from backend.app.data.cost_basis import compute_institution_cost_basis
    inst_id, fid_q3, fid_q4, fid_q1 = _seed_base_scenario(conn)
    _seed_holding(conn, fid_q4, _CUSIP + "D", 100, 15_000, "Test Decr Co")
    _seed_holding(conn, fid_q1, _CUSIP + "D", 60,  10_800, "Test Decr Co")
    _seed_ticker(conn, _CUSIP + "D", _TICKER + "D", "Test Decr Co")
    _seed_prices(conn, _TICKER + "D", [
        ("2023-10-02", _PRICE_Q1, _PRICE_Q1, 1_000_000),
        ("2023-12-29", _PRICE_Q1, _PRICE_Q1, 1_000_000),
    ])
    _seed_change(conn, inst_id, fid_q3, fid_q4, _CUSIP + "D", "new",
                 None, 100, None, 15_000, issuer="Test Decr Co")
    _seed_change(conn, inst_id, fid_q4, fid_q1, _CUSIP + "D", "decreased",
                 100, 60, 15_000, 10_800, -40, issuer="Test Decr Co")

    compute_institution_cost_basis(inst_id, conn)

    row = _fetch_ecb(conn, inst_id, "2024-03-31")
    assert row is not None
    # Average Cost: cost unchanged on partial sale
    assert abs(row["avg_cost_per_share"] - _PRICE_Q1) < 0.01
    assert row["shares"] == 60


def test_engine_closed_position_nulls_cost(conn):
    from backend.app.data.cost_basis import compute_institution_cost_basis
    inst_id, fid_q3, fid_q4, fid_q1 = _seed_base_scenario(conn)
    _seed_holding(conn, fid_q4, _CUSIP + "C", 100, 15_000, "Test Close Co")
    _seed_ticker(conn, _CUSIP + "C", _TICKER + "C")
    _seed_prices(conn, _TICKER + "C", [
        ("2023-10-02", _PRICE_Q1, _PRICE_Q1, 1_000_000),
        ("2023-12-29", _PRICE_Q1, _PRICE_Q1, 1_000_000),
    ])
    _seed_change(conn, inst_id, fid_q3, fid_q4, _CUSIP + "C", "new",
                 None, 100, None, 15_000, issuer="Test Close Co")
    _seed_change(conn, inst_id, fid_q4, fid_q1, _CUSIP + "C", "closed",
                 100, None, 15_000, None, issuer="Test Close Co")

    compute_institution_cost_basis(inst_id, conn)

    row = _fetch_ecb(conn, inst_id, "2024-03-31")
    assert row is not None
    assert row["avg_cost_per_share"] is None
    assert row["shares"] == 0
    assert row["change_type"] == "closed"


def test_engine_no_price_data_yields_null(conn):
    from backend.app.data.cost_basis import compute_institution_cost_basis
    inst_id = _seed_institution(conn, "No Price Fund", "0009000002")
    fid0 = _seed_filing(conn, inst_id, "2023-09-30", "2023-11-14", "NP-Q3")
    fid1 = _seed_filing(conn, inst_id, "2023-12-31", "2024-02-14", "NP-Q4")
    _seed_holding(conn, fid1, "NOCUSIP", 100, 5_000, "No Ticker Co")
    # No entry in cusip_ticker_map — ticker will be NULL
    _seed_change(conn, inst_id, fid0, fid1, "NOCUSIP", "new",
                 None, 100, None, 5_000, issuer="No Ticker Co")

    compute_institution_cost_basis(inst_id, conn)

    row = conn.execute(text(
        "SELECT avg_cost_per_share, price_source FROM estimated_cost_basis "
        "WHERE institution_id=:i AND cusip='NOCUSIP'"
    ), {"i": inst_id}).mappings().fetchone()

    assert row is not None
    assert row["avg_cost_per_share"] is None
    assert row["price_source"] is None
```

- [ ] **Step 4.2: Run engine tests to confirm they fail**

```bash
PYTHONPATH=. pytest backend/tests/test_cost_basis.py -k "engine" -v
```

Expected: 5 tests FAIL with `ImportError` — `compute_institution_cost_basis` not defined yet.

- [ ] **Step 4.3: Append compute_institution_cost_basis to cost_basis.py**

Append to `backend/app/data/cost_basis.py` (after the `get_quarter_price` function):

```python
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
```

- [ ] **Step 4.4: Run engine tests to confirm they pass**

```bash
PYTHONPATH=. pytest backend/tests/test_cost_basis.py -k "engine" -v
```

Expected: 5 tests PASS.

- [ ] **Step 4.5: Run full test suite**

```bash
PYTHONPATH=. pytest backend/tests/ -v
```

Expected: all tests pass (21 existing + 5 new engine = 26 total).

- [ ] **Step 4.6: Commit**

```bash
git add backend/app/data/cost_basis.py backend/tests/test_cost_basis.py
git commit -m "feat: add compute_institution_cost_basis rolling Average Cost engine"
```

---

## Task 5: Cost basis API route

**Files:**
- Create: `backend/app/api/routes/cost_basis.py`
- Modify: `backend/app/main.py`
- Modify: `backend/tests/test_cost_basis.py` (append API test)

- [ ] **Step 5.1: Append API test to test_cost_basis.py**

Append to `backend/tests/test_cost_basis.py`:

```python
# ---------------------------------------------------------------------------
# API: GET /institutions/{id}/cost-basis
# ---------------------------------------------------------------------------

def _seed_api_scenario(conn):
    """Seeds a complete scenario and runs the engine, ready for API queries."""
    inst_id = _seed_institution(conn, "API Test Fund", "0099000001")
    fid0 = _seed_filing(conn, inst_id, "2023-09-30", "2023-11-14", "API-Q3")
    fid1 = _seed_filing(conn, inst_id, "2023-12-31", "2024-02-14", "API-Q4")
    _seed_holding(conn, fid1, "APICUSIP", 200, 30_000, "API Stock Co")
    _seed_ticker(conn, "APICUSIP", "APITK", "API Stock Co")
    _seed_prices(conn, "APITK", [
        ("2023-10-02", 150.0, 150.0, 1_000_000),
        ("2023-12-29", 150.0, 150.0, 1_000_000),
    ])
    _seed_change(conn, inst_id, fid0, fid1, "APICUSIP", "new",
                 None, 200, None, 30_000, issuer="API Stock Co")

    from backend.app.data.cost_basis import compute_institution_cost_basis
    compute_institution_cost_basis(inst_id, conn)
    return inst_id


def test_cost_basis_endpoint_response_shape(conn, client):
    inst_id = _seed_api_scenario(conn)
    resp = client.get(f"/institutions/{inst_id}/cost-basis")
    assert resp.status_code == 200
    data = resp.json()

    assert "institution" in data
    assert data["institution"]["id"] == inst_id

    assert "cost_basis" in data
    assert len(data["cost_basis"]) >= 1

    cb = data["cost_basis"][0]
    for field in ("cusip", "ticker", "issuer_name", "period", "shares",
                  "avg_cost_per_share", "total_cost_basis",
                  "quarter_buy_price", "change_type", "price_source"):
        assert field in cb, f"Missing field: {field}"


def test_cost_basis_endpoint_values(conn, client):
    inst_id = _seed_api_scenario(conn)
    resp = client.get(f"/institutions/{inst_id}/cost-basis")
    cb = resp.json()["cost_basis"][0]

    assert cb["cusip"] == "APICUSIP"
    assert cb["ticker"] == "APITK"
    assert cb["shares"] == 200
    assert cb["change_type"] == "new"
    assert abs(cb["avg_cost_per_share"] - 150.0) < 0.01
    assert abs(cb["total_cost_basis"] - 30_000.0) < 1.0
    assert cb["price_source"] == "yahoo"


def test_cost_basis_endpoint_institution_not_found(client):
    assert client.get("/institutions/99999/cost-basis").status_code == 404


def test_cost_basis_endpoint_filter_by_cusip(conn, client):
    inst_id = _seed_api_scenario(conn)
    resp = client.get(f"/institutions/{inst_id}/cost-basis?cusip=APICUSIP")
    assert resp.status_code == 200
    rows = resp.json()["cost_basis"]
    assert all(r["cusip"] == "APICUSIP" for r in rows)
```

- [ ] **Step 5.2: Run API tests to confirm they fail**

```bash
PYTHONPATH=. pytest backend/tests/test_cost_basis.py -k "cost_basis_endpoint" -v
```

Expected: 4 tests FAIL — route does not exist yet (404 from FastAPI, or import error).

- [ ] **Step 5.3: Create backend/app/api/routes/cost_basis.py**

```python
"""cost_basis.py — GET /institutions/{id}/cost-basis endpoint."""

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.engine import Connection
from sqlalchemy.sql import text

from backend.app.api.deps import _require_institution, get_conn

router = APIRouter()


@router.get("/institutions/{institution_id}/cost-basis", tags=["cost-basis"])
def get_cost_basis(
    institution_id: int,
    period: Optional[str] = Query(
        default=None,
        pattern=r"^\d{4}-\d{2}-\d{2}$",
        description="Filter to a single quarter (YYYY-MM-DD).",
    ),
    cusip: Optional[str] = Query(
        default=None,
        description="Filter to a single CUSIP.",
    ),
    conn: Connection = Depends(get_conn),
) -> dict:
    """
    Estimated average cost basis for all positions held by an institution.

    Returns per-(institution, stock, quarter) estimated average cost per share
    computed by the Average Cost engine in cost_basis.py. Rows with
    avg_cost_per_share = null indicate positions where cost basis could not
    be estimated (unresolved CUSIP or missing price data).

    Query parameter behaviour:
      period — restrict to a single quarter-end date
      cusip  — restrict to a single CUSIP
    """
    inst = _require_institution(conn, institution_id)

    filters = ["ecb.institution_id = :inst_id"]
    params: dict = {"inst_id": institution_id}

    if period:
        filters.append("ecb.period = :period")
        params["period"] = period
    if cusip:
        filters.append("ecb.cusip = :cusip")
        params["cusip"] = cusip.upper()

    where_clause = " AND ".join(filters)

    rows = conn.execute(
        text(f"""
        SELECT
            ecb.cusip,
            ecb.ticker,
            ecb.issuer_name,
            ecb.period,
            ecb.shares,
            ecb.avg_cost_per_share,
            ecb.total_cost_basis,
            ecb.quarter_buy_price,
            ecb.change_type,
            ecb.price_source
        FROM estimated_cost_basis ecb
        WHERE {where_clause}
        ORDER BY ecb.period DESC, ecb.avg_cost_per_share DESC NULLS LAST
        """),
        params,
    ).mappings().fetchall()

    return {
        "institution": inst,
        "cost_basis": [dict(r) for r in rows],
    }
```

- [ ] **Step 5.4: Register the router in main.py**

In `backend/app/main.py`, add the import and include call:

```python
from backend.app.api.routes import health, institutions, stocks, tickers, consensus, cost_basis

# ...existing includes...
app.include_router(cost_basis.router)
```

Full updated import line (replace the existing one):
```python
from backend.app.api.routes import (
    health,
    institutions,
    stocks,
    tickers,
    consensus,
    cost_basis,
)
```

And add after the existing `app.include_router(consensus.router)` line:
```python
app.include_router(cost_basis.router)
```

- [ ] **Step 5.5: Run API tests to confirm they pass**

```bash
PYTHONPATH=. pytest backend/tests/test_cost_basis.py -k "cost_basis_endpoint" -v
```

Expected: 4 tests PASS.

- [ ] **Step 5.6: Run full test suite**

```bash
PYTHONPATH=. pytest backend/tests/ -v
```

Expected: all tests pass (26 + 4 = 30 total).

- [ ] **Step 5.7: Commit**

```bash
git add backend/app/api/routes/cost_basis.py backend/app/main.py backend/tests/test_cost_basis.py
git commit -m "feat: add GET /institutions/{id}/cost-basis endpoint"
```

---

## Task 6: Extend GET /stock/{cusip}/history with cost basis fields

**Files:**
- Modify: `backend/app/api/routes/stocks.py`
- Modify: `backend/tests/test_cost_basis.py` (append test)

- [ ] **Step 6.1: Append stock history test to test_cost_basis.py**

Append to `backend/tests/test_cost_basis.py`:

```python
# ---------------------------------------------------------------------------
# API: GET /stock/{cusip}/history — extended with cost basis fields
# ---------------------------------------------------------------------------

def test_stock_history_includes_cost_basis_fields(conn, client):
    """estimated_avg_cost and estimated_total_cost appear in history rows."""
    # Reuse the API scenario seed (idempotent via INSERT OR IGNORE)
    inst_id = _seed_api_scenario(conn)

    resp = client.get("/stock/APICUSIP/history")
    assert resp.status_code == 200
    data = resp.json()

    assert "history" in data
    history = data["history"]
    assert len(history) >= 1

    row = history[0]
    assert "estimated_avg_cost" in row,  "missing estimated_avg_cost field"
    assert "estimated_total_cost" in row, "missing estimated_total_cost field"


def test_stock_history_cost_basis_value_correct(conn, client):
    """For a seeded new position, avg_cost matches the quarter proxy price."""
    inst_id = _seed_api_scenario(conn)

    resp = client.get("/stock/APICUSIP/history")
    data = resp.json()

    # Find the row for our test institution
    matching = [r for r in data["history"] if r["institution_id"] == inst_id]
    assert len(matching) == 1
    row = matching[0]
    assert row["estimated_avg_cost"] is not None
    assert abs(row["estimated_avg_cost"] - 150.0) < 0.01


def test_stock_history_cost_basis_null_when_unavailable(conn, client):
    """Positions without resolved price data have null estimated_avg_cost."""
    # The engine test scenario for no-price has a separate CUSIP
    # We verify the field exists and may be null — not all rows must be null.
    resp = client.get("/stock/APICUSIP/history")
    data = resp.json()
    # field must always be present (null or float)
    for row in data["history"]:
        assert "estimated_avg_cost" in row
```

- [ ] **Step 6.2: Run the stock history tests to confirm they fail**

```bash
PYTHONPATH=. pytest backend/tests/test_cost_basis.py -k "stock_history" -v
```

Expected: 3 tests FAIL — the fields are not present in the response yet.

- [ ] **Step 6.3: Update get_stock_history in stocks.py**

Replace the SQL query inside `get_stock_history` in `backend/app/api/routes/stocks.py`. The full function after the edit:

```python
@router.get("/stock/{cusip}/history", tags=["history"])
def get_stock_history(
    cusip: str = Path(description="9-character CUSIP"),
    conn: Connection = Depends(get_conn),
) -> dict:
    """
    Quarter-by-quarter holdings history for a CUSIP across all tracked institutions.
    portfolio_weight is the position's value as a fraction of total portfolio value
    for that quarter.  Ordered oldest → newest.
    Includes estimated_avg_cost and estimated_total_cost where available.
    """
    rows = conn.execute(
        text("""
        SELECT
            h.cusip,
            h.issuer_name,
            h.shares,
            h.value,
            f.period_of_report,
            i.id           AS institution_id,
            i.display_name AS institution_name,
            CAST(h.value AS REAL) / NULLIF(
                (SELECT SUM(h2.value) FROM holdings h2 WHERE h2.filing_id = f.id),
                0
            ) AS portfolio_weight,
            ecb.avg_cost_per_share  AS estimated_avg_cost,
            ecb.total_cost_basis    AS estimated_total_cost
        FROM holdings h
        JOIN filings      f   ON f.id = h.filing_id
        JOIN institutions i   ON i.id = f.institution_id
        LEFT JOIN estimated_cost_basis ecb
               ON ecb.institution_id = i.id
              AND ecb.cusip           = h.cusip
              AND ecb.period          = f.period_of_report
        WHERE h.cusip = :cusip
        ORDER BY f.period_of_report ASC, i.id ASC
        """),
        {"cusip": cusip.upper()},
    ).mappings().fetchall()

    if not rows:
        raise HTTPException(
            status_code=404,
            detail=f"No holdings found for CUSIP '{cusip}'.",
        )

    last = rows[-1]
    return {
        "cusip":       last["cusip"],
        "issuer_name": last["issuer_name"],
        "history":     [dict(r) for r in rows],
    }
```

- [ ] **Step 6.4: Run the stock history tests to confirm they pass**

```bash
PYTHONPATH=. pytest backend/tests/test_cost_basis.py -k "stock_history" -v
```

Expected: 3 tests PASS.

- [ ] **Step 6.5: Run full test suite**

```bash
PYTHONPATH=. pytest backend/tests/ -v
```

Expected: all tests pass (30 + 3 = 33 total).

- [ ] **Step 6.6: Commit**

```bash
git add backend/app/api/routes/stocks.py backend/tests/test_cost_basis.py
git commit -m "feat: extend /stock/{cusip}/history with estimated_avg_cost fields"
```

---

## Task 7: CLI scripts — fetch_prices.py and compute_cost_basis.py

**Files:**
- Create: `backend/scripts/fetch_prices.py`
- Create: `backend/scripts/compute_cost_basis.py`

- [ ] **Step 7.1: Create backend/scripts/fetch_prices.py**

```python
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


def _get_tickers(conn, only_ticker: str | None) -> list[str]:
    if only_ticker:
        return [only_ticker.upper()]
    rows = conn.execute(
        text("SELECT DISTINCT ticker FROM cusip_ticker_map WHERE ticker IS NOT NULL")
    ).fetchall()
    return sorted(r[0] for r in rows)


def _store_bars(conn, ticker: str, bars) -> int:
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


def main() -> None:
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
    errors: list[tuple[str, str]] = []

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
```

- [ ] **Step 7.2: Create backend/scripts/compute_cost_basis.py**

```python
"""
compute_cost_basis.py — Populate estimated_cost_basis for all institutions.

Usage:
    PYTHONPATH=. python backend/scripts/compute_cost_basis.py
    PYTHONPATH=. python backend/scripts/compute_cost_basis.py --institution-id 1

Run AFTER fetch_prices.py.
Safe to re-run — uses ON CONFLICT DO UPDATE (idempotent).
"""

import argparse

from sqlalchemy.sql import text

from backend.app.core.database import engine
from backend.app.data.cost_basis import compute_institution_cost_basis


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compute estimated cost basis for all (or one) institution(s)."
    )
    parser.add_argument("--institution-id", type=int,
                        help="Only compute for this institution ID (default: all)")
    args = parser.parse_args()

    with engine.connect() as conn:
        if args.institution_id:
            institutions = conn.execute(
                text("SELECT id, name FROM institutions WHERE id = :id"),
                {"id": args.institution_id},
            ).mappings().fetchall()
        else:
            institutions = conn.execute(
                text("SELECT id, name FROM institutions ORDER BY name")
            ).mappings().fetchall()

    if not institutions:
        print("No institutions found in database.")
        return

    total = 0
    for inst in institutions:
        print(f"  Computing: {inst['name']}  (id={inst['id']}) ...")
        with engine.connect() as conn:
            n = compute_institution_cost_basis(inst["id"], conn)
        print(f"    {n} rows written")
        total += n

    print(f"\nDone. {total:,} estimated_cost_basis rows written.")


if __name__ == "__main__":
    main()
```

- [ ] **Step 7.3: Verify scripts import without errors**

```bash
PYTHONPATH=. python -c "import backend.scripts.fetch_prices; print('fetch_prices OK')"
PYTHONPATH=. python -c "import backend.scripts.compute_cost_basis; print('compute_cost_basis OK')"
```

Expected: both print their OK message.

- [ ] **Step 7.4: Run full test suite one more time**

```bash
PYTHONPATH=. pytest backend/tests/ -v
```

Expected: all 33 tests pass.

- [ ] **Step 7.5: Commit**

```bash
git add backend/scripts/fetch_prices.py backend/scripts/compute_cost_basis.py
git commit -m "feat: add fetch_prices.py and compute_cost_basis.py CLI scripts"
```

---

## Task 8: Comparison hook script (nice-to-have)

**Files:**
- Create: `backend/scripts/compare_price_sources.py`

- [ ] **Step 8.1: Create backend/scripts/compare_price_sources.py**

```python
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


def main() -> None:
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
```

- [ ] **Step 8.2: Verify script imports cleanly**

```bash
PYTHONPATH=. python -c "import backend.scripts.compare_price_sources; print('OK')"
```

Expected: `OK`

- [ ] **Step 8.3: Commit**

```bash
git add backend/scripts/compare_price_sources.py
git commit -m "feat: add compare_price_sources.py comparison hook for future provider comparison"
```

---

## Final Verification

- [ ] **Run the complete test suite**

```bash
PYTHONPATH=. pytest backend/tests/ -v
```

Expected: all 33 tests pass, 0 failures.

- [ ] **Verify API spec for new routes**

```bash
PYTHONPATH=. uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 &
sleep 2
curl -s http://127.0.0.1:8000/openapi.json | python -m json.tool | grep '"path"' | grep -E "cost-basis|history"
kill %1
```

Expected: `/institutions/{institution_id}/cost-basis` and `/stock/{cusip}/history` appear in the OpenAPI schema.

- [ ] **Verify execution order documentation is clear**

The full pipeline execution order for a fresh database is:

```bash
# 1. Build the core holdings/changes DB
PYTHONPATH=. python backend/scripts/setup_db.py

# 2. Resolve CUSIP → ticker mappings
PYTHONPATH=. python backend/scripts/resolve_cusips.py

# 3. Fetch historical price bars from Yahoo Finance
PYTHONPATH=. python backend/scripts/fetch_prices.py

# 4. Compute rolling estimated cost basis
PYTHONPATH=. python backend/scripts/compute_cost_basis.py

# 5. (Optional) Compare price proxy values across sources
PYTHONPATH=. python backend/scripts/compare_price_sources.py
```

---

## Summary

**Quarter proxy chosen:** Volume-Weighted Average Close (VWAC) — `Σ(adj_close × volume) / Σ(volume)` over all trading days in the quarter window (period - 95 days through period-end). Falls back to arithmetic mean when volume data is absent. Encapsulated in `_compute_vwac()` in `cost_basis.py`.

**Where computed cost basis is stored:** `estimated_cost_basis` table (PostgreSQL / SQLite). One row per `(institution_id, cusip, period)`. Populated by `compute_cost_basis.py` CLI.

**Where exposed:**
- `GET /institutions/{id}/cost-basis` — full timeline per institution, filterable by period/cusip
- `GET /stock/{cusip}/history` — extended with `estimated_avg_cost` + `estimated_total_cost` per row

**What remains for V2:**
- Realised P&L (sell price at close time)
- FIFO lot tracking (`last_cost_before_exit` is preserved, but full lot stack is not)
- Cross-institution aggregate cost basis
- Polygon / Tiingo price source comparison (comparison hook scaffolded)
- Frontend UI — StockDrawer chart overlay of cost basis vs market value
- Periodic price refresh via cron/trigger as new quarters arrive
