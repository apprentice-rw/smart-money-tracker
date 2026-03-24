"""
validate_data.py — SEC EDGAR 13F data validation entry point.

Thin wrapper around backend.app.data.sec_edgar.
Terminal output helpers and main() live here; core logic is in sec_edgar.py.

Usage:
    PYTHONPATH=. python backend/scripts/validate_data.py
"""

import sys
import os

# Ensure project root is in sys.path when run directly
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backend.app.data.sec_edgar import (
    INSTITUTIONS,
    compare_quarters,
    fetch_xml,
    get_infotable_xml_url,
    get_recent_13f_filings,
    parse_holdings,
)


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
