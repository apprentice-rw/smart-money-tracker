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
    Seeds: 1 institution (CIK 0009000001), 3 filings (Q3-2023, Q4-2023, Q1-2024),
    price data for Q4-2023 and Q1-2024, ticker mapping.
    Returns (inst_id, fid_q3, fid_q4, fid_q1).
    All inserts use INSERT OR IGNORE — safe to call multiple times.
    """
    inst_id = _seed_institution(conn, "Engine Test Fund", "0009000001")
    fid_q3  = _seed_filing(conn, inst_id, "2023-09-30", "2023-11-14", "ENG-Q3")
    fid_q4  = _seed_filing(conn, inst_id, "2023-12-31", "2024-02-14", "ENG-Q4")
    fid_q1  = _seed_filing(conn, inst_id, "2024-03-31", "2024-05-15", "ENG-Q1")

    _seed_ticker(conn, _CUSIP, _TICKER, "Test Stock Co")

    # Price data — uniform closes so VWAC == _PRICE_Qn exactly.
    # Q4 bars end on 2023-12-20 (before Q1 window start 2023-12-27)
    # to prevent the last Q4 bar bleeding into the Q1 95-day window.
    _seed_prices(conn, _TICKER, [
        ("2023-10-02", _PRICE_Q1, _PRICE_Q1, 1_000_000),
        ("2023-11-01", _PRICE_Q1, _PRICE_Q1, 1_000_000),
        ("2023-12-20", _PRICE_Q1, _PRICE_Q1, 1_000_000),
        ("2024-01-02", _PRICE_Q2, _PRICE_Q2, 1_000_000),
        ("2024-02-01", _PRICE_Q2, _PRICE_Q2, 1_000_000),
        ("2024-03-28", _PRICE_Q2, _PRICE_Q2, 1_000_000),
    ])

    return inst_id, fid_q3, fid_q4, fid_q1


def _fetch_ecb(conn, inst_id, period, cusip=_CUSIP):
    return conn.execute(text(
        "SELECT * FROM estimated_cost_basis "
        "WHERE institution_id=:i AND cusip=:c AND period=:p"
    ), {"i": inst_id, "c": cusip, "p": period}).mappings().fetchone()


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
    _DCUSIP = _CUSIP + "D"
    _DTICKER = _TICKER + "D"
    _seed_ticker(conn, _DCUSIP, _DTICKER, "Test Decr Co")
    _seed_prices(conn, _DTICKER, [
        ("2023-10-02", _PRICE_Q1, _PRICE_Q1, 1_000_000),
        ("2023-12-20", _PRICE_Q1, _PRICE_Q1, 1_000_000),
    ])
    _seed_holding(conn, fid_q4, _DCUSIP, 100, 15_000, "Test Decr Co")
    _seed_holding(conn, fid_q1, _DCUSIP, 60,  10_800, "Test Decr Co")
    _seed_change(conn, inst_id, fid_q3, fid_q4, _DCUSIP, "new",
                 None, 100, None, 15_000, issuer="Test Decr Co")
    _seed_change(conn, inst_id, fid_q4, fid_q1, _DCUSIP, "decreased",
                 100, 60, 15_000, 10_800, -40, issuer="Test Decr Co")

    compute_institution_cost_basis(inst_id, conn)

    row = _fetch_ecb(conn, inst_id, "2024-03-31", cusip=_DCUSIP)
    assert row is not None
    # Average Cost: cost unchanged on partial sale
    assert abs(row["avg_cost_per_share"] - _PRICE_Q1) < 0.01
    assert row["shares"] == 60


def test_engine_closed_position_nulls_cost(conn):
    from backend.app.data.cost_basis import compute_institution_cost_basis
    inst_id, fid_q3, fid_q4, fid_q1 = _seed_base_scenario(conn)
    _CCUSIP = _CUSIP + "C"
    _CTICKER = _TICKER + "C"
    _seed_ticker(conn, _CCUSIP, _CTICKER)
    _seed_prices(conn, _CTICKER, [
        ("2023-10-02", _PRICE_Q1, _PRICE_Q1, 1_000_000),
        ("2023-12-20", _PRICE_Q1, _PRICE_Q1, 1_000_000),
    ])
    _seed_holding(conn, fid_q4, _CCUSIP, 100, 15_000, "Test Close Co")
    _seed_change(conn, inst_id, fid_q3, fid_q4, _CCUSIP, "new",
                 None, 100, None, 15_000, issuer="Test Close Co")
    _seed_change(conn, inst_id, fid_q4, fid_q1, _CCUSIP, "closed",
                 100, None, 15_000, None, issuer="Test Close Co")

    compute_institution_cost_basis(inst_id, conn)

    row = _fetch_ecb(conn, inst_id, "2024-03-31", cusip=_CCUSIP)
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
        ("2023-12-20", 150.0, 150.0, 1_000_000),
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


# ---------------------------------------------------------------------------
# API: GET /stock/{cusip}/history — extended with cost basis fields
# ---------------------------------------------------------------------------

def test_stock_history_includes_cost_basis_fields(conn, client):
    """estimated_avg_cost and estimated_total_cost appear in history rows."""
    _seed_api_scenario(conn)  # idempotent — seeds APICUSIP / APITK if not already present

    resp = client.get("/stock/APICUSIP/history")
    assert resp.status_code == 200
    data = resp.json()

    assert "history" in data
    history = data["history"]
    assert len(history) >= 1

    row = history[0]
    assert "estimated_avg_cost" in row,   "missing estimated_avg_cost field"
    assert "estimated_total_cost" in row, "missing estimated_total_cost field"


def test_stock_history_cost_basis_value_correct(conn, client):
    """For a seeded new position, avg_cost matches the quarter proxy price."""
    inst_id = _seed_api_scenario(conn)  # idempotent

    resp = client.get("/stock/APICUSIP/history")
    data = resp.json()

    matching = [r for r in data["history"] if r["institution_id"] == inst_id]
    assert len(matching) >= 1
    row = matching[0]
    assert row["estimated_avg_cost"] is not None
    assert abs(row["estimated_avg_cost"] - 150.0) < 0.01


def test_stock_history_cost_basis_field_always_present(conn, client):
    """estimated_avg_cost field is present on every history row (may be null)."""
    _seed_api_scenario(conn)  # idempotent

    resp = client.get("/stock/APICUSIP/history")
    data = resp.json()
    for row in data["history"]:
        assert "estimated_avg_cost" in row
        assert "estimated_total_cost" in row


def test_engine_increased_with_zero_curr_shares_does_not_crash(conn):
    """Malformed data: change_type=increased but curr_shares=0 should not raise."""
    from backend.app.data.cost_basis import compute_institution_cost_basis
    inst_id = _seed_institution(conn, "Zero Shares Fund", "0009000003")
    fid0 = _seed_filing(conn, inst_id, "2023-09-30", "2023-11-14", "ZS-Q3")
    fid1 = _seed_filing(conn, inst_id, "2023-12-31", "2024-02-14", "ZS-Q4")
    _seed_ticker(conn, "ZSCUSIP", "ZSTK")
    _seed_prices(conn, "ZSTK", [
        ("2023-10-02", 100.0, 100.0, 1_000_000),
    ])
    # curr_shares=0 with change_type=increased is malformed but must not crash
    _seed_change(conn, inst_id, fid0, fid1, "ZSCUSIP", "increased",
                 50, 0, 5_000, 0, issuer="Zero Shares Co")

    # Must not raise ZeroDivisionError
    n = compute_institution_cost_basis(inst_id, conn)
    assert n >= 1

    row = conn.execute(text(
        "SELECT avg_cost_per_share, shares FROM estimated_cost_basis "
        "WHERE institution_id=:i AND cusip='ZSCUSIP'"
    ), {"i": inst_id}).mappings().fetchone()
    assert row is not None
    assert row["shares"] == 0  # curr_shares was 0
