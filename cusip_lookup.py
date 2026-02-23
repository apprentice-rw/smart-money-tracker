"""
CUSIP → ticker resolver using OpenFIGI API + name-based fallback.

Usage:
    python3 cusip_lookup.py            # resolve only CUSIPs not yet cached
    python3 cusip_lookup.py --all      # re-resolve everything (overwrites)
    python3 cusip_lookup.py --report   # show current coverage stats, no fetching

Set OPENFIGI_API_KEY in .env for 250 req/min (vs 25 req/min without key).
Without a key, ~4 700 CUSIPs takes ~20 min. With a key, ~2 min.
"""

import argparse
import json
import os
import re
import time
import urllib.request
from typing import Optional

import requests
from dotenv import load_dotenv
from sqlalchemy import text

load_dotenv()

from db import engine

OPENFIGI_URL     = "https://api.openfigi.com/v3/mapping"
OPENFIGI_API_KEY = os.environ.get("OPENFIGI_API_KEY", "")
BATCH_SIZE       = 10
# 250 req/min with key → 0.25 s gap; 25 req/min without → 2.5 s gap
DELAY            = 0.25 if OPENFIGI_API_KEY else 2.5

# US exchange codes we prefer when multiple instruments match a CUSIP
_US_EXCHANGES = {"US", "UN", "UW", "UQ", "UA"}


# ---------------------------------------------------------------------------
# Name normalisation (mirrors improved frontend normalizeName)
# ---------------------------------------------------------------------------

_SUFFIX_RE = re.compile(
    r"\b(inc|corp|co|ltd|llc|plc|holdings|group|class [a-c]|cl [a-c]"
    r"|del|com|adr|ads|ord|the|new)\b\.?",
    re.IGNORECASE,
)
_ABBREV_MAP = [
    (re.compile(r"\bfinl\b",    re.I), "financial"),
    (re.compile(r"\bpete\b",    re.I), "petroleum"),
    (re.compile(r"\bmfg\b",     re.I), "manufacturing"),
    (re.compile(r"\bcommuns?\b",re.I), "communications"),
    (re.compile(r"\bsvcs\b",    re.I), "services"),
]


def _norm(s: str) -> str:
    s = s.lower()
    for pat, full in _ABBREV_MAP:
        s = pat.sub(full, s)
    s = _SUFFIX_RE.sub("", s)
    s = re.sub(r"[^a-z0-9]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


# ---------------------------------------------------------------------------
# SEC name map (name-based fallback for CUSIPs OpenFIGI can't match)
# ---------------------------------------------------------------------------

def _load_sec_name_map() -> dict[str, str]:
    """Fetch SEC exchange ticker file → normalised_name → ticker map."""
    url = "https://www.sec.gov/files/company_tickers_exchange.json"
    req = urllib.request.Request(
        url, headers={"User-Agent": "SmartMoneyTracker research@example.com"}
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read())
    result: dict[str, str] = {}
    for row in data.get("data", []):
        _, name, ticker, _ = row
        if name and ticker:
            k = _norm(name)
            if k and k not in result:
                result[k] = ticker
    return result


# ---------------------------------------------------------------------------
# OpenFIGI helpers
# ---------------------------------------------------------------------------

def _pick_best(instruments: list[dict]) -> Optional[dict]:
    """
    From a list of OpenFIGI instruments for one CUSIP, return the best match.
    Preference: US equity common stock > US equity > any equity > first result.
    """
    equities   = [d for d in instruments if d.get("marketSector") == "Equity"]
    us_eq      = [d for d in equities    if d.get("exchCode") in _US_EXCHANGES]
    us_common  = [d for d in us_eq       if "Common Stock" in (d.get("securityType") or "")]
    for pool in (us_common, us_eq, equities, instruments):
        if pool:
            return pool[0]
    return None


def _query_openfigi(cusips: list[str]) -> list[Optional[dict]]:
    """
    POST up to BATCH_SIZE CUSIPs to OpenFIGI /v3/mapping.
    Returns a list aligned with input; None = no match found.
    Handles rate-limit (429) with a 60-second back-off, retries up to 3 times.
    """
    payload = [{"idType": "ID_CUSIP", "idValue": c} for c in cusips]
    headers = {"Content-Type": "application/json"}
    if OPENFIGI_API_KEY:
        headers["X-OPENFIGI-APIKEY"] = OPENFIGI_API_KEY

    for attempt in range(3):
        try:
            resp = requests.post(
                OPENFIGI_URL, json=payload, headers=headers, timeout=30
            )
            if resp.status_code == 429:
                print("    Rate-limited — waiting 60 s …")
                time.sleep(60)
                continue
            resp.raise_for_status()
            items = resp.json()
            break
        except requests.RequestException as exc:
            if attempt == 2:
                print(f"    OpenFIGI request failed (giving up): {exc}")
                return [None] * len(cusips)
            time.sleep(5)
    else:
        return [None] * len(cusips)

    out: list[Optional[dict]] = []
    for item in items:
        if "error" in item or not item.get("data"):
            out.append(None)
        else:
            out.append(_pick_best(item["data"]))
    return out


# ---------------------------------------------------------------------------
# Main resolution logic
# ---------------------------------------------------------------------------

def build_cusip_ticker_map(resolve_all: bool = False) -> None:
    """
    Resolve holdings CUSIPs to tickers and persist in cusip_ticker_map.

    resolve_all=False  Only processes CUSIPs not yet in the table (default).
    resolve_all=True   Re-resolves everything, overwriting existing rows.
    """
    with engine.connect() as conn:
        if resolve_all:
            rows = conn.execute(text("""
                SELECT h.cusip, MAX(h.issuer_name) AS name
                FROM holdings h
                GROUP BY h.cusip
            """)).fetchall()
        else:
            rows = conn.execute(text("""
                SELECT h.cusip, MAX(h.issuer_name) AS name
                FROM holdings h
                LEFT JOIN cusip_ticker_map m ON m.cusip = h.cusip
                WHERE m.cusip IS NULL
                GROUP BY h.cusip
            """)).fetchall()

    if not rows:
        print("No new CUSIPs to resolve — all already cached.")
        return

    cusips        = [r[0] for r in rows]
    name_by_cusip = {r[0]: r[1] for r in rows}
    total         = len(cusips)

    key_info = (
        f"key: {OPENFIGI_API_KEY[:8]}… (250 req/min)"
        if OPENFIGI_API_KEY
        else "no key (25 req/min — ~20 min for full DB)"
    )
    est = total / BATCH_SIZE * DELAY
    print(f"Resolving {total} CUSIPs via OpenFIGI  [{key_info}]")
    print(f"Estimated time: {est:.0f} s  ({est / 60:.1f} min)\n")

    # ── Pass 1: OpenFIGI ──────────────────────────────────────────────
    figi_results: dict[str, Optional[dict]] = {}
    t0 = time.time()

    for i in range(0, total, BATCH_SIZE):
        batch   = cusips[i : i + BATCH_SIZE]
        results = _query_openfigi(batch)
        for cusip, result in zip(batch, results):
            figi_results[cusip] = result
        time.sleep(DELAY)

        done = min(i + BATCH_SIZE, total)
        if done % 200 == 0 or done == total:
            matched_so_far = sum(1 for v in figi_results.values() if v)
            elapsed = time.time() - t0
            print(f"  {done:>5}/{total}  ({matched_so_far} matched)  [{elapsed:.0f} s elapsed]")

    figi_matched          = sum(1 for v in figi_results.values() if v is not None)
    figi_unmatched_cusips = [c for c, v in figi_results.items() if v is None]
    print(f"\nOpenFIGI:  {figi_matched}/{total} matched")

    # ── Pass 2: name-based fallback for OpenFIGI misses ───────────────
    print(f"Name fallback for {len(figi_unmatched_cusips)} unmatched CUSIPs …")
    try:
        sec_map = _load_sec_name_map()
    except Exception as exc:
        print(f"  WARNING: Could not load SEC name map ({exc}), skipping fallback.")
        sec_map = {}

    name_results: dict[str, Optional[str]] = {}
    for cusip in figi_unmatched_cusips:
        name = name_by_cusip.get(cusip, "")
        name_results[cusip] = sec_map.get(_norm(name)) if name else None

    name_matched = sum(1 for v in name_results.values() if v is not None)
    print(f"Name fallback: {name_matched}/{len(figi_unmatched_cusips)} matched")

    # ── Persist all results ───────────────────────────────────────────
    insert_rows = []
    for cusip in cusips:
        result = figi_results.get(cusip)
        if result is not None:
            insert_rows.append({
                "cusip":        cusip,
                "ticker":       result.get("ticker"),
                "company_name": result.get("name"),
                "source":       "openfigi",
            })
        else:
            fb = name_results.get(cusip)
            insert_rows.append({
                "cusip":        cusip,
                "ticker":       fb,
                "company_name": name_by_cusip.get(cusip, ""),
                "source":       "name_match" if fb else "unmatched",
            })

    upsert_sql = (
        """
        INSERT INTO cusip_ticker_map (cusip, ticker, company_name, source)
        VALUES (:cusip, :ticker, :company_name, :source)
        ON CONFLICT (cusip) DO UPDATE SET
            ticker       = excluded.ticker,
            company_name = excluded.company_name,
            source       = excluded.source,
            fetched_at   = CURRENT_TIMESTAMP
        """
        if resolve_all else
        """
        INSERT INTO cusip_ticker_map (cusip, ticker, company_name, source)
        VALUES (:cusip, :ticker, :company_name, :source)
        ON CONFLICT (cusip) DO NOTHING
        """
    )

    with engine.connect() as conn:
        conn.execute(text(upsert_sql), insert_rows)
        conn.commit()

    # ── Summary ───────────────────────────────────────────────────────
    total_matched = figi_matched + name_matched
    unmatched     = total - total_matched
    elapsed_total = time.time() - t0

    print(f"\n{'=' * 52}")
    print(f"  CUSIP resolution complete  ({elapsed_total:.0f} s)")
    print(f"{'=' * 52}")
    print(f"  Total CUSIPs:        {total:>6}")
    print(f"  OpenFIGI matched:    {figi_matched:>6}  ({figi_matched / total * 100:.1f}%)")
    print(f"  Name fallback:       {name_matched:>6}  ({name_matched / total * 100:.1f}%)")
    print(f"  Unmatched (NULL):    {unmatched:>6}  ({unmatched / total * 100:.1f}%)")
    print(f"  ─────────────────────────────")
    print(f"  Total coverage:      {total_matched:>6}  ({total_matched / total * 100:.1f}%)")

    if unmatched:
        sample = [(c, name_by_cusip[c]) for c in cusips
                  if figi_results.get(c) is None and name_results.get(c) is None][:10]
        print(f"\n  Sample unmatched (stored as NULL ticker):")
        for cusip, name in sample:
            print(f"    {cusip}  {name}")


# ---------------------------------------------------------------------------
# Coverage report (no network calls)
# ---------------------------------------------------------------------------

def print_coverage_report() -> None:
    """Print current coverage stats from the DB without hitting any APIs."""
    with engine.connect() as conn:
        total_cusips = conn.execute(
            text("SELECT COUNT(DISTINCT cusip) FROM holdings")
        ).fetchone()[0]

        cached = conn.execute(
            text("SELECT COUNT(*) FROM cusip_ticker_map")
        ).fetchone()[0]

        by_source = conn.execute(text("""
            SELECT source, COUNT(*) AS n
            FROM cusip_ticker_map
            GROUP BY source
            ORDER BY n DESC
        """)).fetchall()

        total_matched = conn.execute(
            text("SELECT COUNT(*) FROM cusip_ticker_map WHERE ticker IS NOT NULL")
        ).fetchone()[0]

    print(f"\n{'=' * 52}")
    print(f"  CUSIP Ticker Coverage Report")
    print(f"{'=' * 52}")
    print(f"  Total distinct CUSIPs in holdings:  {total_cusips:>6}")
    print(f"  Cached in cusip_ticker_map:         {cached:>6}")
    print(f"  With a ticker:                      {total_matched:>6}  "
          f"({total_matched / total_cusips * 100:.1f}% of all holdings CUSIPs)")
    print(f"\n  Breakdown by source:")
    for source, n in by_source:
        pct = n / total_cusips * 100
        print(f"    {source or 'NULL':<15}  {n:>6}  ({pct:.1f}%)")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Resolve holdings CUSIPs to tickers via OpenFIGI + name fallback"
    )
    parser.add_argument(
        "--all", action="store_true",
        help="Re-resolve all CUSIPs (default: only new ones not yet in the table)",
    )
    parser.add_argument(
        "--report", action="store_true",
        help="Show current coverage stats without making any API calls",
    )
    args = parser.parse_args()

    if args.report:
        print_coverage_report()
    else:
        build_cusip_ticker_map(resolve_all=args.all)
