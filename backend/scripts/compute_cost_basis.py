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


def main():
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
