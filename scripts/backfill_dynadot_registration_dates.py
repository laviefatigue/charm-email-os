#!/usr/bin/env python3
"""
Backfill registration_date for Dynadot domains from the Dynadot API.

This updates the registration_date field in the domains table with the actual
purchase/registration date from Dynadot, which is used for domain age calculations.

Usage:
    python scripts/backfill_dynadot_registration_dates.py [--dry-run]
"""
import argparse
import asyncio
import os
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.services.dynadot import DynadotService
from api.db import fetch_all, execute


async def main():
    parser = argparse.ArgumentParser(description="Backfill Dynadot registration dates")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be updated without making changes")
    args = parser.parse_args()

    print("Fetching domains from Dynadot API...")

    async with DynadotService() as dynadot:
        domains = await dynadot.list_domains()

    print(f"Found {len(domains)} domains in Dynadot account")

    # Build a lookup of domain -> registration_date
    dynadot_dates = {}
    for d in domains:
        if d.registration_date:
            dynadot_dates[d.domain.lower()] = d.registration_date
            print(f"  {d.domain}: registered {d.registration_date.strftime('%Y-%m-%d')}")

    print(f"\n{len(dynadot_dates)} domains have registration dates")

    # Get all domains in our database that are from Dynadot
    db_domains = await fetch_all("""
        SELECT id, domain_name, registration_date, created_at
        FROM domains
        WHERE selected_provider = 'dynadot'
        OR domain_name IN (SELECT UNNEST($1::text[]))
    """, list(dynadot_dates.keys()))

    print(f"\nFound {len(db_domains)} domains in database to check")

    updates = []
    for db_domain in db_domains:
        domain_name = db_domain["domain_name"].lower()
        if domain_name in dynadot_dates:
            dynadot_date = dynadot_dates[domain_name]
            current_date = db_domain["registration_date"]

            if current_date != dynadot_date:
                updates.append({
                    "id": db_domain["id"],
                    "domain_name": db_domain["domain_name"],
                    "old_date": current_date,
                    "new_date": dynadot_date,
                })

    if not updates:
        print("\nNo updates needed - all registration dates are already correct")
        return

    print(f"\n{len(updates)} domains need registration_date updates:")
    for u in updates:
        old = u["old_date"].strftime('%Y-%m-%d') if u["old_date"] else "NULL"
        new = u["new_date"].strftime('%Y-%m-%d')
        print(f"  {u['domain_name']}: {old} -> {new}")

    if args.dry_run:
        print("\n[DRY RUN] No changes made")
        return

    # Apply updates
    print("\nApplying updates...")
    for u in updates:
        await execute("""
            UPDATE domains
            SET registration_date = $2, updated_at = NOW()
            WHERE id = $1
        """, u["id"], u["new_date"])
        print(f"  Updated {u['domain_name']}")

    print(f"\nDone! Updated {len(updates)} domains with Dynadot registration dates")


if __name__ == "__main__":
    asyncio.run(main())
