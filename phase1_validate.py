"""
Phase 1 — SEC EDGAR 13F Data Validation Script
Validates that SEC EDGAR's free API returns usable, parseable 13F holdings data.
No frameworks, no database — raw API calls, XML parsing, terminal output.
"""

import time
import xml.etree.ElementTree as ET
import requests

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

INSTITUTIONS = {
    "Berkshire Hathaway": "0001067983",
    "ARK Investment Management": "0001697748",
    "Bridgewater Associates": "0001350694",
    "Soros Fund Management": "0001029160",
    "Pershing Square Capital Management": "0001336528",
    "Renaissance Technologies": "0001037389",
    "Duquesne Family Office": "0001536411",
    "Tiger Global Management": "0001167483",
    "Third Point": "0001040273",
    "Baupost Group": "0001061768",
    "Lone Pine Capital": "0001061165",
}

USER_AGENT = "SmartMoneyTracker research@example.com"
RATE_LIMIT_DELAY = 0.15  # seconds between requests (SEC limit: 10 req/s)


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def fetch_json(url: str) -> dict:
    """Fetch a URL and return parsed JSON. Respects SEC rate limit."""
    time.sleep(RATE_LIMIT_DELAY)
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    resp = requests.get(url, headers=headers, timeout=30)
    resp.raise_for_status()
    return resp.json()


def fetch_xml(url: str) -> str:
    """Fetch a URL and return raw text (XML). Respects SEC rate limit."""
    time.sleep(RATE_LIMIT_DELAY)
    headers = {"User-Agent": USER_AGENT, "Accept": "*/*"}
    resp = requests.get(url, headers=headers, timeout=30)
    resp.raise_for_status()
    return resp.text


# ---------------------------------------------------------------------------
# Filing discovery
# ---------------------------------------------------------------------------

def get_recent_13f_filings(cik: str, n: int = 3) -> list[dict]:
    """
    Fetch the most recent n 13F-HR filings for a given CIK.
    Returns list of {accession_number, period_of_report, filing_date} dicts.
    """
    url = f"https://data.sec.gov/submissions/CIK{cik}.json"
    data = fetch_json(url)

    recent = data.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    accessions = recent.get("accessionNumber", [])
    periods = recent.get("reportDate", [])
    dates = recent.get("filingDate", [])

    filings = []
    for form, acc, period, filed in zip(forms, accessions, periods, dates):
        if form == "13F-HR":
            filings.append(
                {
                    "accession_number": acc,
                    "period_of_report": period,
                    "filing_date": filed,
                }
            )
        if len(filings) >= n:
            break

    return filings


# ---------------------------------------------------------------------------
# Infotable URL discovery
# ---------------------------------------------------------------------------

def get_infotable_xml_url(cik: str, accession_number: str) -> str:
    """
    Given a CIK and accession number, return the URL of the 13F infotable XML.
    Searches the filing index for a document whose type is the information table
    or whose filename ends in .xml and is not the primary cover doc.
    """
    accession_clean = accession_number.replace("-", "")
    index_url = (
        f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/"
        f"{accession_clean}/index.json"
    )
    data = fetch_json(index_url)

    items = data.get("directory", {}).get("item", [])

    # First pass: look for document whose type/description says INFORMATION TABLE
    for item in items:
        doc_type = item.get("type", "").upper()
        name = item.get("name", "")
        if "INFORMATION TABLE" in doc_type and name.lower().endswith(".xml"):
            return (
                f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/"
                f"{accession_clean}/{name}"
            )

    # Second pass: any .xml that is not the primary document
    for item in items:
        name = item.get("name", "")
        if name.lower().endswith(".xml") and name.lower() != "primary_doc.xml":
            return (
                f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/"
                f"{accession_clean}/{name}"
            )

    raise ValueError(
        f"Could not locate infotable XML for CIK {cik} accession {accession_number}"
    )


# ---------------------------------------------------------------------------
# Holdings parsing
# ---------------------------------------------------------------------------

def _extract_ns(root: ET.Element) -> str:
    """Extract the XML namespace URI from the root element tag, e.g. '{http://...}'."""
    tag = root.tag
    if tag.startswith("{"):
        return tag[: tag.index("}") + 1]
    return ""


def _detect_value_multiplier(holdings: list[dict]) -> int:
    """
    Detect whether a filing's values are in raw USD (return 1) or thousands
    of dollars (return 1000).

    The SEC 13F instructions allow filers to report in thousands, but since
    2024 raw USD is required. Some filers still use thousands.  There is no
    explicit <multiplier> tag, so we infer the unit from the median implied
    per-share price across all holdings:
      - If median(value / shares) < $1.00  → values are in thousands (×1000)
      - Otherwise                          → values are already in raw USD
    """
    prices = [
        h["value"] / h["shares"]
        for h in holdings
        if h["shares"] > 0 and h["value"] > 0
    ]
    if not prices:
        return 1
    median_price = sorted(prices)[len(prices) // 2]
    return 1000 if median_price < 1.0 else 1


def parse_holdings(xml_text: str, period: str) -> list[dict]:
    """
    Parse a 13F infotable XML and return a list of holding dicts.
    Extracts the namespace from the root element for robust cross-filing matching.
    Values are always normalised to raw USD before returning.

    Each dict contains:
        name_of_issuer, cusip, value (raw USD), shares, share_type, period
    """
    root = ET.fromstring(xml_text)
    ns = _extract_ns(root)
    holdings = []

    # Use findall with explicit namespace prefix so it works on Python 3.8/3.9
    for info in root.findall(f".//{ns}infoTable"):
        def _text(tag: str, _info: ET.Element = info, _ns: str = ns) -> str:
            el = _info.find(f"{_ns}{tag}")
            return el.text.strip() if el is not None and el.text else ""

        name = _text("nameOfIssuer")
        cusip = _text("cusip")
        value_str = _text("value")
        share_el = info.find(f"{ns}shrsOrPrnAmt")
        shares_str = ""
        share_type = ""
        if share_el is not None:
            s = share_el.find(f"{ns}sshPrnamt")
            shares_str = s.text.strip() if s is not None and s.text else ""
            t = share_el.find(f"{ns}sshPrnamtType")
            share_type = t.text.strip() if t is not None and t.text else ""

        try:
            value = int(value_str)
        except (ValueError, TypeError):
            value = 0
        try:
            shares = int(shares_str)
        except (ValueError, TypeError):
            shares = 0

        if cusip:
            holdings.append(
                {
                    "name_of_issuer": name,
                    "cusip": cusip,
                    "value": value,       # may be thousands — normalised below
                    "shares": shares,
                    "share_type": share_type,
                    "period": period,
                }
            )

    # Normalise values to raw USD if filer reported in thousands
    multiplier = _detect_value_multiplier(holdings)
    if multiplier != 1:
        for h in holdings:
            h["value"] = h["value"] * multiplier

    return holdings


# ---------------------------------------------------------------------------
# Quarter-over-quarter comparison
# ---------------------------------------------------------------------------

def compare_quarters(
    prev_holdings: list[dict], curr_holdings: list[dict]
) -> dict:
    """
    Compare two lists of holdings (keyed by CUSIP) and categorise changes.
    Returns dict with keys: new, closed, increased, decreased, unchanged.
    """
    prev_map = {h["cusip"]: h for h in prev_holdings}
    curr_map = {h["cusip"]: h for h in curr_holdings}

    prev_cusips = set(prev_map)
    curr_cusips = set(curr_map)

    new_cusips = curr_cusips - prev_cusips
    closed_cusips = prev_cusips - curr_cusips
    both_cusips = prev_cusips & curr_cusips

    increased = []
    decreased = []
    unchanged = []

    for cusip in both_cusips:
        prev_shares = prev_map[cusip]["shares"]
        curr_shares = curr_map[cusip]["shares"]
        if curr_shares > prev_shares:
            increased.append(
                {
                    "prev": prev_map[cusip],
                    "curr": curr_map[cusip],
                    "delta": curr_shares - prev_shares,
                    "pct": (
                        (curr_shares - prev_shares) / prev_shares * 100
                        if prev_shares > 0
                        else float("inf")
                    ),
                }
            )
        elif curr_shares < prev_shares:
            decreased.append(
                {
                    "prev": prev_map[cusip],
                    "curr": curr_map[cusip],
                    "delta": curr_shares - prev_shares,
                    "pct": (
                        (curr_shares - prev_shares) / prev_shares * 100
                        if prev_shares > 0
                        else float("-inf")
                    ),
                }
            )
        else:
            unchanged.append(curr_map[cusip])

    # Sort for deterministic output
    increased.sort(key=lambda x: x["pct"], reverse=True)
    decreased.sort(key=lambda x: x["pct"])

    return {
        "new": [curr_map[c] for c in new_cusips],
        "closed": [prev_map[c] for c in closed_cusips],
        "increased": increased,
        "decreased": decreased,
        "unchanged": unchanged,
    }


# ---------------------------------------------------------------------------
# Terminal output
# ---------------------------------------------------------------------------

def _fmt_value(v: int) -> str:
    """Format a raw-USD value for display."""
    if v >= 1_000_000_000:
        return f"${v / 1_000_000_000:.1f}B"
    if v >= 1_000_000:
        return f"${v / 1_000_000:.1f}M"
    if v >= 1_000:
        return f"${v / 1_000:.1f}K"
    return f"${v}"


def print_summary(
    institution_name: str,
    prev_filing: dict,
    curr_filing: dict,
    prev_holdings: list[dict],
    curr_holdings: list[dict],
    comparison: dict,
) -> None:
    width = 60
    print("\n" + "=" * width)
    print(f"  {institution_name.upper()}  |  13F Analysis")
    print("=" * width)

    prev_period = prev_filing["period_of_report"]
    curr_period = curr_filing["period_of_report"]
    print(f"Comparing {prev_period} → {curr_period}\n")

    prev_total = sum(h["value"] for h in prev_holdings)
    curr_total = sum(h["value"] for h in curr_holdings)

    print("Portfolio Size:")
    print(
        f"  {prev_period}: {len(prev_holdings):>3} positions  |  "
        f"Total Value: {_fmt_value(prev_total)}"
    )
    print(
        f"  {curr_period}: {len(curr_holdings):>3} positions  |  "
        f"Total Value: {_fmt_value(curr_total)}"
    )

    # Top 10 current holdings
    top10 = sorted(curr_holdings, key=lambda h: h["value"], reverse=True)[:10]
    print(f"\nTop 10 Holdings ({curr_period}):")
    print(f"  {'#':<3} {'Name':<30} {'CUSIP':<12} {'Shares':>15} {'Value (USD)':>15}")
    print("  " + "-" * 78)
    for i, h in enumerate(top10, 1):
        print(
            f"  {i:<3} {h['name_of_issuer'][:30]:<30} {h['cusip']:<12} "
            f"{h['shares']:>15,} {_fmt_value(h['value']):>15}"
        )

    # New positions
    new = comparison["new"]
    print(f"\nNEW POSITIONS ({len(new)}):")
    if new:
        for h in sorted(new, key=lambda x: x["value"], reverse=True):
            print(
                f"  - {h['name_of_issuer']} (CUSIP: {h['cusip']}) — "
                f"{h['shares']:,} shares | {_fmt_value(h['value'])}"
            )
    else:
        print("  (none)")

    # Closed positions
    closed = comparison["closed"]
    print(f"\nCLOSED POSITIONS ({len(closed)}):")
    if closed:
        for h in sorted(closed, key=lambda x: x["value"], reverse=True):
            print(f"  - {h['name_of_issuer']} (CUSIP: {h['cusip']})")
    else:
        print("  (none)")

    # Increased positions — top 5
    increased = comparison["increased"]
    print(f"\nINCREASED (\u2191) {len(increased)} positions:")
    for item in increased[:5]:
        p, c = item["prev"], item["curr"]
        print(
            f"  - {c['name_of_issuer']}: {p['shares']:,} → {c['shares']:,} shares "
            f"({item['pct']:+.1f}%)"
        )
    if len(increased) > 5:
        print(f"  ... and {len(increased) - 5} more")

    # Decreased positions — top 5 (largest drops)
    decreased = comparison["decreased"]
    print(f"\nDECREASED (\u2193) {len(decreased)} positions:")
    for item in decreased[:5]:
        p, c = item["prev"], item["curr"]
        print(
            f"  - {c['name_of_issuer']}: {p['shares']:,} → {c['shares']:,} shares "
            f"({item['pct']:+.1f}%)"
        )
    if len(decreased) > 5:
        print(f"  ... and {len(decreased) - 5} more")

    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    for name, cik in INSTITUTIONS.items():
        print(f"\nFetching 13F filings for {name} (CIK: {cik}) ...")

        try:
            filings = get_recent_13f_filings(cik, n=2)
        except Exception as exc:
            print(f"  ERROR fetching filings: {exc}")
            continue

        if len(filings) < 2:
            print(f"  Not enough 13F filings found (got {len(filings)}, need 2).")
            continue

        # filings[0] is most recent; filings[1] is the one before
        curr_filing = filings[0]
        prev_filing = filings[1]

        print(
            f"  Found: {curr_filing['period_of_report']} (filed {curr_filing['filing_date']}) "
            f"and {prev_filing['period_of_report']} (filed {prev_filing['filing_date']})"
        )

        holdings_by_filing = {}
        for filing in [prev_filing, curr_filing]:
            acc = filing["accession_number"]
            period = filing["period_of_report"]
            print(f"  Fetching holdings for {period} ...")
            try:
                xml_url = get_infotable_xml_url(cik, acc)
                xml_text = fetch_xml(xml_url)
                holdings = parse_holdings(xml_text, period)
                holdings_by_filing[period] = holdings
                print(f"    -> {len(holdings)} holdings parsed from {xml_url}")
            except Exception as exc:
                print(f"  ERROR processing {period}: {exc}")
                holdings_by_filing[period] = []

        prev_holdings = holdings_by_filing.get(prev_filing["period_of_report"], [])
        curr_holdings = holdings_by_filing.get(curr_filing["period_of_report"], [])

        if not curr_holdings:
            print("  Skipping comparison — no current holdings.")
            continue

        comparison = compare_quarters(prev_holdings, curr_holdings)

        print_summary(
            name,
            prev_filing,
            curr_filing,
            prev_holdings,
            curr_holdings,
            comparison,
        )


if __name__ == "__main__":
    main()
