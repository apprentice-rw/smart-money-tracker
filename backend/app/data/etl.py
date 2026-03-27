"""
etl.py — Database schema DDL and ETL pipeline.

Core logic from phase2_setup_db.py without the entry-point main().
The entry point lives in backend/scripts/setup_db.py.
"""

import os
import sys
from pathlib import Path

from sqlalchemy.engine import Connection
from sqlalchemy.sql import text

from backend.app.core.database import IS_SQLITE, engine

# Reuse all fetch/parse logic from sec_edgar — no duplication
from backend.app.data.sec_edgar import (
    INSTITUTIONS,
    compare_quarters,
    fetch_xml,
    get_infotable_xml_url,
    get_recent_13f_filings,
    parse_holdings,
)

NUM_QUARTERS = 8  # how many quarters to backfill (2 years)


# ---------------------------------------------------------------------------
# Schema  (dual DDL: SQLite vs PostgreSQL differ only in primary-key syntax)
# ---------------------------------------------------------------------------

_PK_SQLITE   = "INTEGER PRIMARY KEY AUTOINCREMENT"
_PK_POSTGRES = "BIGSERIAL PRIMARY KEY"
_PK = _PK_SQLITE if IS_SQLITE else _PK_POSTGRES

SCHEMA_STATEMENTS = [
    # institutions
    f"""
    CREATE TABLE IF NOT EXISTS institutions (
        id           {_PK},
        cik          TEXT    NOT NULL UNIQUE,
        name         TEXT    NOT NULL,
        display_name TEXT    NOT NULL
    )
    """,

    # filings
    f"""
    CREATE TABLE IF NOT EXISTS filings (
        id                 {_PK},
        institution_id     INTEGER NOT NULL REFERENCES institutions(id),
        period_of_report   TEXT    NOT NULL,
        filing_date        TEXT    NOT NULL,
        accession_number   TEXT    NOT NULL UNIQUE,
        UNIQUE (institution_id, period_of_report)
    )
    """,

    # holdings (shares/value summed across sub-managers by CUSIP)
    f"""
    CREATE TABLE IF NOT EXISTS holdings (
        id          {_PK},
        filing_id   INTEGER NOT NULL REFERENCES filings(id),
        cusip       TEXT    NOT NULL,
        issuer_name TEXT    NOT NULL,
        shares      BIGINT  NOT NULL DEFAULT 0,
        value       BIGINT  NOT NULL DEFAULT 0,
        share_type  TEXT    NOT NULL DEFAULT '',
        UNIQUE (filing_id, cusip)
    )
    """,

    # position_changes (precomputed quarter-over-quarter)
    f"""
    CREATE TABLE IF NOT EXISTS position_changes (
        id             {_PK},
        institution_id INTEGER NOT NULL REFERENCES institutions(id),
        prev_filing_id INTEGER NOT NULL REFERENCES filings(id),
        curr_filing_id INTEGER NOT NULL REFERENCES filings(id),
        cusip          TEXT    NOT NULL,
        issuer_name    TEXT    NOT NULL,
        change_type    TEXT    NOT NULL CHECK(change_type IN
                           ('new', 'closed', 'increased', 'decreased', 'unchanged')),
        prev_shares    BIGINT,
        curr_shares    BIGINT,
        prev_value     BIGINT,
        curr_value     BIGINT,
        shares_delta   BIGINT,
        shares_pct     REAL,
        UNIQUE (prev_filing_id, curr_filing_id, cusip)
    )
    """,

    # cusip_ticker_map — permanent CUSIP→ticker cache (populated by resolve_cusips.py)
    """
    CREATE TABLE IF NOT EXISTS cusip_ticker_map (
        cusip        TEXT PRIMARY KEY,
        ticker       TEXT,
        company_name TEXT,
        source       TEXT,
        fetched_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,

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

    # stock_splits — corporate split events used by the cost-basis engine
    # ratio = post_shares / pre_shares  (e.g. 2.0 for 2:1, 0.5 for 1:2 reverse)
    """
    CREATE TABLE IF NOT EXISTS stock_splits (
        ticker      TEXT    NOT NULL,
        date        TEXT    NOT NULL,
        ratio       REAL    NOT NULL,
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

    # indexes
    "CREATE INDEX IF NOT EXISTS idx_holdings_cusip    ON holdings (cusip)",
    "CREATE INDEX IF NOT EXISTS idx_holdings_filing   ON holdings (filing_id)",
    "CREATE INDEX IF NOT EXISTS idx_holdings_value    ON holdings (value DESC)",
    "CREATE INDEX IF NOT EXISTS idx_filings_inst      ON filings (institution_id)",
    "CREATE INDEX IF NOT EXISTS idx_filings_period    ON filings (period_of_report)",
    "CREATE INDEX IF NOT EXISTS idx_changes_inst      ON position_changes (institution_id)",
    "CREATE INDEX IF NOT EXISTS idx_changes_cusip     ON position_changes (cusip)",
    "CREATE INDEX IF NOT EXISTS idx_changes_curr      ON position_changes (curr_filing_id)",
    "CREATE INDEX IF NOT EXISTS idx_changes_prev      ON position_changes (prev_filing_id)",
    "CREATE INDEX IF NOT EXISTS idx_price_history_ticker ON price_history (ticker)",
    "CREATE INDEX IF NOT EXISTS idx_ecb_inst_period ON estimated_cost_basis (institution_id, period)",
    "CREATE INDEX IF NOT EXISTS idx_ecb_cusip        ON estimated_cost_basis (cusip)",
    "CREATE INDEX IF NOT EXISTS idx_stock_splits_ticker ON stock_splits (ticker, date)",
]


# ---------------------------------------------------------------------------
# Schema application
# ---------------------------------------------------------------------------

def apply_schema(conn: Connection) -> None:
    for stmt in SCHEMA_STATEMENTS:
        conn.execute(text(stmt))
    conn.commit()
    print(f"Schema applied  →  {engine.url}")


# ---------------------------------------------------------------------------
# DB wipe (called before a clean rebuild)
# ---------------------------------------------------------------------------

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
                        "price_history", "stock_splits"):
                conn.execute(text(f"DROP TABLE IF EXISTS {tbl} CASCADE"))
            conn.commit()
        print("  Dropped all PostgreSQL tables for clean rebuild.")


# ---------------------------------------------------------------------------
# Aggregation helper
# ---------------------------------------------------------------------------

def aggregate_holdings(raw_holdings: list[dict]) -> list[dict]:
    """
    Collapse duplicate CUSIPs (e.g. Berkshire sub-managers) into one row
    by summing shares and value.  Returns one dict per unique CUSIP.
    """
    agg: dict[str, dict] = {}
    for h in raw_holdings:
        c = h["cusip"]
        if c not in agg:
            agg[c] = {
                "cusip": c,
                "issuer_name": h["name_of_issuer"],
                "shares": h["shares"],
                "value": h["value"],
                "share_type": h["share_type"],
                "period": h["period"],
            }
        else:
            agg[c]["shares"] += h["shares"]
            agg[c]["value"] += h["value"]
    return list(agg.values())


# ---------------------------------------------------------------------------
# Upsert helpers
# ---------------------------------------------------------------------------

def upsert_institution(conn: Connection, name: str, cik: str) -> int:
    conn.execute(
        text("""
        INSERT INTO institutions (cik, name, display_name)
        VALUES (:cik, :name, :display_name)
        ON CONFLICT(cik) DO UPDATE SET
            name         = excluded.name,
            display_name = excluded.display_name
        """),
        {"cik": cik, "name": name, "display_name": name},
    )
    row = conn.execute(
        text("SELECT id FROM institutions WHERE cik = :cik"),
        {"cik": cik},
    ).fetchone()
    return row[0]


def upsert_filing(conn: Connection, institution_id: int, filing: dict) -> int:
    conn.execute(
        text("""
        INSERT INTO filings (institution_id, period_of_report, filing_date, accession_number)
        VALUES (:inst_id, :period, :filing_date, :accession)
        ON CONFLICT(accession_number) DO NOTHING
        """),
        {
            "inst_id":      institution_id,
            "period":       filing["period_of_report"],
            "filing_date":  filing["filing_date"],
            "accession":    filing["accession_number"],
        },
    )
    row = conn.execute(
        text("SELECT id FROM filings WHERE accession_number = :accession"),
        {"accession": filing["accession_number"]},
    ).fetchone()
    return row[0]


def upsert_holdings(conn: Connection, filing_id: int, aggregated: list[dict]) -> int:
    """Insert or replace all holdings for a filing. Returns row count written."""
    conn.execute(
        text("""
        INSERT INTO holdings (filing_id, cusip, issuer_name, shares, value, share_type)
        VALUES (:filing_id, :cusip, :issuer_name, :shares, :value, :share_type)
        ON CONFLICT(filing_id, cusip) DO UPDATE SET
            issuer_name = excluded.issuer_name,
            shares      = excluded.shares,
            value       = excluded.value,
            share_type  = excluded.share_type
        """),
        [
            {
                "filing_id":   filing_id,
                "cusip":       h["cusip"],
                "issuer_name": h["issuer_name"],
                "shares":      h["shares"],
                "value":       h["value"],
                "share_type":  h["share_type"],
            }
            for h in aggregated
        ],
    )
    return len(aggregated)


def upsert_position_changes(
    conn: Connection,
    institution_id: int,
    prev_filing_id: int,
    curr_filing_id: int,
    prev_agg: list[dict],
    curr_agg: list[dict],
) -> int:
    """
    Compute and store position_changes between two consecutive quarters.
    Returns number of rows written.
    """
    prev_adapted = [
        {"cusip": h["cusip"], "name_of_issuer": h["issuer_name"],
         "shares": h["shares"], "value": h["value"]}
        for h in prev_agg
    ]
    curr_adapted = [
        {"cusip": h["cusip"], "name_of_issuer": h["issuer_name"],
         "shares": h["shares"], "value": h["value"]}
        for h in curr_agg
    ]

    comparison = compare_quarters(prev_adapted, curr_adapted)

    rows = []

    for h in comparison["new"]:
        rows.append({
            "inst_id": institution_id, "prev_id": prev_filing_id, "curr_id": curr_filing_id,
            "cusip": h["cusip"], "issuer": h["name_of_issuer"], "ctype": "new",
            "prev_sh": None, "curr_sh": h["shares"],
            "prev_v": None,  "curr_v": h["value"],
            "delta": None,   "pct": None,
        })

    for h in comparison["closed"]:
        rows.append({
            "inst_id": institution_id, "prev_id": prev_filing_id, "curr_id": curr_filing_id,
            "cusip": h["cusip"], "issuer": h["name_of_issuer"], "ctype": "closed",
            "prev_sh": h["shares"], "curr_sh": None,
            "prev_v": h["value"],   "curr_v": None,
            "delta": None,          "pct": None,
        })

    for item in comparison["increased"]:
        p, c = item["prev"], item["curr"]
        rows.append({
            "inst_id": institution_id, "prev_id": prev_filing_id, "curr_id": curr_filing_id,
            "cusip": c["cusip"], "issuer": c["name_of_issuer"], "ctype": "increased",
            "prev_sh": p["shares"], "curr_sh": c["shares"],
            "prev_v": p["value"],   "curr_v": c["value"],
            "delta": item["delta"], "pct": round(item["pct"], 4),
        })

    for item in comparison["decreased"]:
        p, c = item["prev"], item["curr"]
        rows.append({
            "inst_id": institution_id, "prev_id": prev_filing_id, "curr_id": curr_filing_id,
            "cusip": c["cusip"], "issuer": c["name_of_issuer"], "ctype": "decreased",
            "prev_sh": p["shares"], "curr_sh": c["shares"],
            "prev_v": p["value"],   "curr_v": c["value"],
            "delta": item["delta"], "pct": round(item["pct"], 4),
        })

    prev_map = {x["cusip"]: x for x in prev_adapted}
    for h in comparison["unchanged"]:
        rows.append({
            "inst_id": institution_id, "prev_id": prev_filing_id, "curr_id": curr_filing_id,
            "cusip": h["cusip"], "issuer": h["name_of_issuer"], "ctype": "unchanged",
            "prev_sh": prev_map[h["cusip"]]["shares"], "curr_sh": h["shares"],
            "prev_v": prev_map[h["cusip"]]["value"],   "curr_v": h["value"],
            "delta": 0, "pct": 0.0,
        })

    conn.execute(
        text("""
        INSERT INTO position_changes (
            institution_id, prev_filing_id, curr_filing_id,
            cusip, issuer_name, change_type,
            prev_shares, curr_shares, prev_value, curr_value,
            shares_delta, shares_pct
        ) VALUES (
            :inst_id, :prev_id, :curr_id,
            :cusip, :issuer, :ctype,
            :prev_sh, :curr_sh, :prev_v, :curr_v,
            :delta, :pct
        )
        ON CONFLICT(prev_filing_id, curr_filing_id, cusip) DO UPDATE SET
            change_type  = excluded.change_type,
            prev_shares  = excluded.prev_shares,
            curr_shares  = excluded.curr_shares,
            prev_value   = excluded.prev_value,
            curr_value   = excluded.curr_value,
            shares_delta = excluded.shares_delta,
            shares_pct   = excluded.shares_pct
        """),
        rows,
    )
    return len(rows)


# ---------------------------------------------------------------------------
# Main ETL
# ---------------------------------------------------------------------------

def run_etl(conn: Connection = None) -> None:
    """Run the full ETL pipeline.

    Accepts an optional *conn* for backward-compatibility, but opens a fresh
    engine connection per institution so long-running jobs don't time out on
    managed databases (e.g. Supabase session-pooler).
    """
    for inst_name, cik in INSTITUTIONS.items():
        print(f"\n{'─' * 55}")
        print(f"  Processing: {inst_name}  (CIK {cik})")
        print(f"{'─' * 55}")

        with engine.connect() as inst_conn:
            inst_id = upsert_institution(inst_conn, inst_name, cik)
            inst_conn.commit()

            print(f"  Fetching last {NUM_QUARTERS} 13F-HR filings ...")
            try:
                filings = get_recent_13f_filings(cik, n=NUM_QUARTERS)
            except Exception as exc:
                print(f"  ERROR: {exc}")
                continue

            if not filings:
                print("  No filings found — skipping.")
                continue

            print(f"  Found {len(filings)} filing(s):")
            for f in filings:
                print(f"    {f['period_of_report']}  (filed {f['filing_date']})")

            filing_records: list[dict] = []

            for filing in reversed(filings):
                period = filing["period_of_report"]
                acc = filing["accession_number"]

                print(f"\n  [{period}]  Fetching holdings ...")
                try:
                    xml_url = get_infotable_xml_url(cik, acc)
                    xml_text = fetch_xml(xml_url)
                    raw = parse_holdings(xml_text, period)
                except Exception as exc:
                    print(f"    ERROR fetching/parsing: {exc}")
                    continue

                aggregated = aggregate_holdings(raw)
                print(
                    f"    Raw rows: {len(raw):>4}  →  "
                    f"Unique CUSIPs: {len(aggregated):>4}  "
                    f"(collapsed {len(raw) - len(aggregated)} duplicates)"
                )

                filing_id = upsert_filing(inst_conn, inst_id, filing)
                n_written = upsert_holdings(inst_conn, filing_id, aggregated)
                inst_conn.commit()
                print(f"    Stored {n_written} holdings rows  (filing_id={filing_id})")

                filing_records.append({
                    "meta":       filing,
                    "filing_id":  filing_id,
                    "aggregated": aggregated,
                })

            for i in range(len(filing_records) - 1):
                prev_rec = filing_records[i]
                curr_rec = filing_records[i + 1]
                prev_period = prev_rec["meta"]["period_of_report"]
                curr_period = curr_rec["meta"]["period_of_report"]

                print(f"\n  Computing changes: {prev_period} → {curr_period} ...")
                n_changes = upsert_position_changes(
                    inst_conn,
                    inst_id,
                    prev_rec["filing_id"],
                    curr_rec["filing_id"],
                    prev_rec["aggregated"],
                    curr_rec["aggregated"],
                )
                inst_conn.commit()
                print(f"    Stored {n_changes} position_change rows")


# ---------------------------------------------------------------------------
# Verification summary
# ---------------------------------------------------------------------------

def print_verification(conn: Connection) -> None:
    print(f"\n{'=' * 55}")
    print("  VERIFICATION SUMMARY")
    print(f"{'=' * 55}")

    tables = ["institutions", "filings", "holdings", "position_changes"]
    for tbl in tables:
        n = conn.execute(text(f"SELECT COUNT(*) FROM {tbl}")).fetchone()[0]
        print(f"  {tbl:<22}  {n:>6} rows")

    print(f"\n  {'─' * 51}")
    print("  institutions:")
    for row in conn.execute(text("SELECT id, cik, name FROM institutions")).mappings():
        print(f"    id={row['id']}  cik={row['cik']}  name={row['name']}")

    print(f"\n  filings (all):")
    for row in conn.execute(text("""
        SELECT f.id, i.name, f.period_of_report, f.filing_date
        FROM filings f
        JOIN institutions i ON i.id = f.institution_id
        ORDER BY i.name, f.period_of_report
    """)).mappings():
        print(
            f"    id={row['id']}  [{row['period_of_report']}]  "
            f"filed={row['filing_date']}  inst={row['name']}"
        )

    print(f"\n  holdings — top 5 by value (most recent filing, each institution):")
    for inst_row in conn.execute(text("SELECT id, name FROM institutions")).mappings():
        latest = conn.execute(text("""
            SELECT id, period_of_report FROM filings
            WHERE institution_id = :inst_id
            ORDER BY period_of_report DESC
            LIMIT 1
        """), {"inst_id": inst_row["id"]}).mappings().fetchone()
        if not latest:
            continue
        print(f"\n    {inst_row['name']}  ({latest['period_of_report']}):")
        for h in conn.execute(text("""
            SELECT cusip, issuer_name, shares, value
            FROM holdings
            WHERE filing_id = :fid
            ORDER BY value DESC
            LIMIT 5
        """), {"fid": latest["id"]}).mappings():
            print(
                f"      {h['cusip']}  {h['issuer_name'][:30]:<30}"
                f"  {h['shares']:>15,}  ${h['value']:>15,}"
            )

    print(f"\n  position_changes — counts by institution + quarter pair + type:")
    for row in conn.execute(text("""
        SELECT
            i.name                      AS inst,
            pf.period_of_report         AS prev_period,
            cf.period_of_report         AS curr_period,
            pc.change_type,
            COUNT(*)                    AS cnt
        FROM position_changes pc
        JOIN institutions i  ON i.id  = pc.institution_id
        JOIN filings pf      ON pf.id = pc.prev_filing_id
        JOIN filings cf      ON cf.id = pc.curr_filing_id
        GROUP BY i.name, prev_period, curr_period, pc.change_type
        ORDER BY i.name, prev_period, pc.change_type
    """)).mappings():
        print(
            f"    {row['inst'][:28]:<28}  "
            f"{row['prev_period']} → {row['curr_period']}  "
            f"{row['change_type']:<12}  {row['cnt']:>4}"
        )

    print(f"\n  position_changes — sample NEW positions (most recent pair):")
    for inst_row in conn.execute(text("SELECT id, name FROM institutions")).mappings():
        rows = conn.execute(text("""
            SELECT pc.cusip, pc.issuer_name, pc.curr_shares, pc.curr_value,
                   pf.period_of_report AS prev_p, cf.period_of_report AS curr_p
            FROM position_changes pc
            JOIN filings pf ON pf.id = pc.prev_filing_id
            JOIN filings cf ON cf.id = pc.curr_filing_id
            WHERE pc.institution_id = :inst_id
              AND pc.change_type = 'new'
              AND cf.period_of_report = (
                    SELECT MAX(period_of_report) FROM filings
                    WHERE institution_id = :inst_id
              )
            ORDER BY pc.curr_value DESC NULLS LAST
            LIMIT 3
        """), {"inst_id": inst_row["id"]}).mappings().fetchall()
        if rows:
            print(f"\n    {inst_row['name']}  ({rows[0]['prev_p']} → {rows[0]['curr_p']}):")
            for r in rows:
                print(
                    f"      NEW  {r['cusip']}  {r['issuer_name'][:30]:<30}"
                    f"  {r['curr_shares']:>12,} shares"
                    f"  ${r['curr_value']:>14,}"
                )

    print(f"\n  Database: {engine.url}")
    print()
