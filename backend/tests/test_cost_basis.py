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
    # (100*1000 + 110*2000 + 120*1000) / 4000 = 440000 / 4000 = 110.0
    assert abs(_compute_vwac(bars) - 110.0) < 0.001


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
