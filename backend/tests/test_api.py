"""
API route tests.

Uses FastAPI's TestClient with an in-memory SQLite database so tests run
without a real Supabase connection. The get_conn dependency is overridden
for each test via app.dependency_overrides.

Run:
    PYTHONPATH=. pytest
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
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def test_engine():
    """Session-scoped SQLite engine with minimal fixture data."""
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

        # Two institutions
        conn.execute(text(
            "INSERT INTO institutions (id, cik, name, display_name) VALUES "
            "(1, '0001067983', 'Berkshire Hathaway', 'Berkshire Hathaway'), "
            "(2, '0001697748', 'ARK Investment Management', 'ARK Investment Management')"
        ))

        # Three filings: two for Berkshire (two quarters), one for ARK
        conn.execute(text(
            "INSERT INTO filings (id, institution_id, period_of_report, filing_date, accession_number) VALUES "
            "(1, 1, '2025-12-31', '2026-02-11', '0000001067983-26-000001'), "
            "(2, 1, '2025-09-30', '2025-11-12', '0000001067983-25-000002'), "
            "(3, 2, '2025-12-31', '2026-02-12', '0000001697748-26-000001')"
        ))

        # Holdings
        conn.execute(text(
            "INSERT INTO holdings (filing_id, cusip, issuer_name, shares, value) VALUES "
            "(1, '037833100', 'Apple Inc',       1000000, 170000000), "
            "(1, '30303M102', 'Meta Platforms',   500000,  60000000), "
            "(2, '037833100', 'Apple Inc',        1100000, 165000000), "
            "(3, '037833100', 'Apple Inc',         200000,  34000000)"
        ))

        # Position changes for Berkshire Q4 vs Q3
        conn.execute(text(
            "INSERT INTO position_changes "
            "(institution_id, prev_filing_id, curr_filing_id, cusip, issuer_name, "
            " change_type, prev_shares, curr_shares, prev_value, curr_value, shares_delta, shares_pct) VALUES "
            "(1, 2, 1, '037833100', 'Apple Inc',      'decreased', 1100000, 1000000, 165000000, 170000000, -100000, -9.09), "
            "(1, 2, 1, '30303M102', 'Meta Platforms', 'new',       NULL,     500000,  NULL,       60000000,  NULL,    NULL)"
        ))

        # Ticker map
        conn.execute(text(
            "INSERT INTO cusip_ticker_map (cusip, ticker, company_name, source) VALUES "
            "('037833100', 'AAPL', 'Apple Inc', 'openfigi'), "
            "('30303M102', 'META', 'Meta Platforms', 'openfigi')"
        ))

    yield engine

    engine.dispose()
    os.unlink(db_path)


@pytest.fixture()
def client(test_engine):
    """Test client with get_conn overridden to use the test SQLite engine."""
    def override_get_conn():
        with test_engine.connect() as conn:
            yield conn

    app.dependency_overrides[get_conn] = override_get_conn
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert data["row_counts"]["institutions"] == 2
    assert data["row_counts"]["filings"] == 3
    assert data["row_counts"]["holdings"] == 4
    assert data["row_counts"]["position_changes"] == 2


# ---------------------------------------------------------------------------
# Institutions
# ---------------------------------------------------------------------------

def test_list_institutions(client):
    r = client.get("/institutions")
    assert r.status_code == 200
    data = r.json()
    assert "institutions" in data
    assert len(data["institutions"]) == 2
    names = {i["name"] for i in data["institutions"]}
    assert "Berkshire Hathaway" in names
    assert "ARK Investment Management" in names


def test_institution_filings(client):
    r = client.get("/institutions/1/filings")
    assert r.status_code == 200
    data = r.json()
    assert "filings" in data
    assert len(data["filings"]) == 2
    # newest first
    assert data["filings"][0]["period_of_report"] == "2025-12-31"


def test_institution_holdings(client):
    r = client.get("/institutions/1/holdings")
    assert r.status_code == 200
    data = r.json()
    assert data["total_positions"] == 2
    assert data["holdings"][0]["cusip"] == "037833100"  # Apple largest by value


def test_institution_changes(client):
    r = client.get("/institutions/1/changes")
    assert r.status_code == 200
    data = r.json()
    assert data["prev_period"] == "2025-09-30"
    assert data["curr_period"] == "2025-12-31"
    assert len(data["changes"]["new"]) == 1
    assert len(data["changes"]["decreased"]) == 1
    assert data["changes"]["new"][0]["cusip"] == "30303M102"


def test_institution_not_found(client):
    assert client.get("/institutions/999/filings").status_code == 404
    assert client.get("/institutions/999/holdings").status_code == 404


# ---------------------------------------------------------------------------
# Consensus
# ---------------------------------------------------------------------------

def test_consensus_quarters(client):
    r = client.get("/consensus/quarters")
    assert r.status_code == 200
    data = r.json()
    assert "quarters" in data
    periods = [q["period"] for q in data["quarters"]]
    assert "2025-12-31" in periods
    assert "2025-09-30" in periods


def test_consensus_holdings_multi_holder(client):
    """Apple is held by both institutions in Q4 — should appear in results."""
    r = client.get("/consensus/holdings?min_holders=2")
    assert r.status_code == 200
    data = r.json()
    cusips = [item["cusip"] for item in data["results"]]
    assert "037833100" in cusips
    apple = next(i for i in data["results"] if i["cusip"] == "037833100")
    assert apple["holder_count"] == 2


def test_consensus_holdings_single_holder(client):
    """With min_holders=1, Meta (held by 1) should also appear."""
    r = client.get("/consensus/holdings?min_holders=1")
    assert r.status_code == 200
    cusips = [i["cusip"] for i in r.json()["results"]]
    assert "30303M102" in cusips


def test_consensus_buying(client):
    r = client.get("/consensus/buying?min_buyers=1")
    assert r.status_code == 200
    data = r.json()
    assert "results" in data
    # Meta was a 'new' buy for Berkshire
    cusips = [i["cusip"] for i in data["results"]]
    assert "30303M102" in cusips


def test_consensus_selling(client):
    r = client.get("/consensus/selling?min_sellers=1")
    assert r.status_code == 200
    data = r.json()
    assert "results" in data
    # Apple was 'decreased' by Berkshire
    cusips = [i["cusip"] for i in data["results"]]
    assert "037833100" in cusips


def test_consensus_emerging(client):
    r = client.get("/consensus/emerging")
    assert r.status_code == 200
    data = r.json()
    assert "results" in data


def test_consensus_persistent(client):
    r = client.get("/consensus/persistent?min_quarters=1&min_holders=1")
    assert r.status_code == 200
    data = r.json()
    assert "results" in data
    # Apple appears in all 3 filings — should be persistent
    cusips = [i["cusip"] for i in data["results"]]
    assert "037833100" in cusips


def test_consensus_period_not_found(client):
    r = client.get("/consensus/holdings?period=1999-12-31")
    assert r.status_code == 404
