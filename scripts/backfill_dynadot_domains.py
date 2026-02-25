#!/usr/bin/env python3
"""
Backfill: Import domains from Dynadot account and update selected_provider.

This script:
  1. Fetches all domains from the Dynadot account via API
  2. Matches them against existing domain records in the database
  3. Updates matched domains with selected_provider='dynadot'
  4. Updates nameserver_status based on current NS from Dynadot
  5. Optionally creates new domain records for unmatched Dynadot domains

Usage:
    py scripts/backfill_dynadot_domains.py                 # Dry run (no changes)
    py scripts/backfill_dynadot_domains.py --execute       # Write to DB
    py scripts/backfill_dynadot_domains.py --workspace "Charm"  # Filter to workspace
    py scripts/backfill_dynadot_domains.py --create-missing     # Also create new records

Required ENV:
    DYNADOT_API_KEY - Dynadot API key
    POSTGRES_PASSWORD - Database password (or use --local for local dev)
"""

import asyncio
import psycopg2
from psycopg2.extras import RealDictCursor
import argparse
import os
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.services.dynadot import DynadotService

# DNSimple nameservers (Hypertide-ready)
DNSIMPLE_NAMESERVERS = [
    "ns1.dnsimple.com",
    "ns2.dnsimple-edge.net",
    "ns3.dnsimple.com",
    "ns4.dnsimple-edge.org",
]

# Charm workspace (default)
CHARM_CLIENT_ID = "4bd07dc0-059a-448b-b6f4-3275d0c104a9"
CHARM_WORKSPACE_ID = "b9abd34a-f16a-4b92-bda0-5af10f8c44bd"


def determine_ns_status(nameservers: list[str]) -> str:
    """
    Determine nameserver_status based on current nameservers.

    Returns:
        'verified' - DNSimple nameservers configured
        'pending' - No nameservers or non-DNSimple
        'parked' - Domain is parked at registrar
    """
    if not nameservers:
        return "parked"

    # Check if at least 2 DNSimple nameservers are configured
    dnsimple_count = sum(
        1 for ns in nameservers
        if any(dnsimple in ns.lower() for dnsimple in ["dnsimple", "dnsimple-edge"])
    )

    if dnsimple_count >= 2:
        return "verified"

    return "pending"


async def fetch_dynadot_domains():
    """Fetch all domains from Dynadot account."""
    api_key = os.getenv("DYNADOT_API_KEY")
    if not api_key:
        print("ERROR: DYNADOT_API_KEY environment variable required")
        sys.exit(1)

    print("Fetching domains from Dynadot API...")
    async with DynadotService(api_key=api_key) as dynadot:
        domains = await dynadot.list_domains()

    print(f"  Found {len(domains)} domains in Dynadot account")
    return domains


def main():
    parser = argparse.ArgumentParser(description="Backfill domain records from Dynadot API")
    parser.add_argument("--execute", action="store_true", help="Actually write to DB (default is dry run)")
    parser.add_argument("--local", action="store_true", help="Use local database (localhost:5433)")
    parser.add_argument("--workspace", type=str, help="Filter to specific workspace name")
    parser.add_argument("--create-missing", action="store_true", help="Create domain records for Dynadot domains not in DB")
    args = parser.parse_args()

    # Database connection
    if args.local:
        conn = psycopg2.connect(
            host="localhost",
            port=5433,
            database="postgres",
            user="postgres",
            password="localdevpassword",
        )
    else:
        password = os.getenv("POSTGRES_PASSWORD")
        if not password:
            print("ERROR: POSTGRES_PASSWORD environment variable required (or use --local)")
            sys.exit(1)
        conn = psycopg2.connect(
            host=os.getenv("POSTGRES_HOST", "31.97.142.123"),
            port=int(os.getenv("POSTGRES_PORT", "5432")),
            database=os.getenv("POSTGRES_DB", "postgres"),
            user=os.getenv("POSTGRES_USER", "postgres"),
            password=password,
        )

    cur = conn.cursor(cursor_factory=RealDictCursor)

    print("=" * 70)
    print("Dynadot Domain Backfill")
    print("=" * 70)
    print(f"Mode: {'EXECUTE' if args.execute else 'DRY RUN'}")
    print(f"Database: {'LOCAL (localhost:5433)' if args.local else 'PRODUCTION'}")
    if args.workspace:
        print(f"Filter: Workspace '{args.workspace}'")
    print()

    # Step 1: Fetch domains from Dynadot API
    dynadot_domains = asyncio.run(fetch_dynadot_domains())

    if not dynadot_domains:
        print("No domains found in Dynadot account. Check API key.")
        return

    # Build lookup by domain name
    dynadot_lookup = {d.domain.lower(): d for d in dynadot_domains}

    print("\nDynadot domains:")
    for d in sorted(dynadot_domains, key=lambda x: x.domain):
        ns_status = determine_ns_status(d.nameservers)
        ns_list = ", ".join(d.nameservers[:2]) if d.nameservers else "(parked)"
        print(f"  {d.domain:35s}  NS: {ns_status:8s}  {ns_list}")
    print()

    # Step 2: Get workspaces (for workspace filtering)
    workspace_filter = None
    if args.workspace:
        cur.execute("SELECT id, workspace_name FROM workspaces WHERE workspace_name ILIKE %s", (f"%{args.workspace}%",))
        ws_row = cur.fetchone()
        if ws_row:
            workspace_filter = ws_row["id"]
            print(f"Filtering to workspace: {ws_row['workspace_name']} ({workspace_filter})")
        else:
            print(f"ERROR: No workspace matching '{args.workspace}'")
            return
    print()

    # Step 3: Get existing domain records
    if workspace_filter:
        cur.execute("""
            SELECT id, domain_name, workspace_id, selected_provider, nameserver_status, current_nameservers, approval_status
            FROM domains
            WHERE workspace_id = %s
            ORDER BY domain_name
        """, (workspace_filter,))
    else:
        cur.execute("""
            SELECT id, domain_name, workspace_id, selected_provider, nameserver_status, current_nameservers, approval_status
            FROM domains
            ORDER BY domain_name
        """)

    existing_domains = cur.fetchall()
    existing_by_name = {row["domain_name"].lower(): row for row in existing_domains}

    print(f"Existing domain records in DB: {len(existing_domains)}")
    print()

    # Step 4: Process matches
    updated = []
    already_correct = []
    not_in_dynadot = []
    created = []

    for row in existing_domains:
        domain_name = row["domain_name"].lower()

        if domain_name in dynadot_lookup:
            dynadot_info = dynadot_lookup[domain_name]
            ns_status = determine_ns_status(dynadot_info.nameservers)

            # Check if already correctly set
            if row["selected_provider"] == "dynadot" and row["nameserver_status"] == ns_status:
                already_correct.append(domain_name)
                continue

            # Update domain record
            ns_json = dynadot_info.nameservers if dynadot_info.nameservers else None
            cur.execute("""
                UPDATE domains
                SET selected_provider = 'dynadot',
                    nameserver_status = %s,
                    current_nameservers = %s,
                    updated_at = NOW()
                WHERE id = %s
            """, (ns_status, ns_json, row["id"]))

            updated.append({
                "domain": domain_name,
                "old_provider": row["selected_provider"],
                "old_ns_status": row["nameserver_status"],
                "new_ns_status": ns_status,
                "nameservers": dynadot_info.nameservers[:2] if dynadot_info.nameservers else [],
            })
        else:
            not_in_dynadot.append(domain_name)

    # Step 5: Create missing domain records (if requested)
    if args.create_missing:
        for domain_name, dynadot_info in dynadot_lookup.items():
            if domain_name not in existing_by_name:
                # Determine workspace - default to Charm for now
                target_workspace = workspace_filter or CHARM_WORKSPACE_ID
                ns_status = determine_ns_status(dynadot_info.nameservers)

                cur.execute("""
                    INSERT INTO domains (workspace_id, domain_name, approval_status, selected_provider, nameserver_status, current_nameservers, created_at, updated_at)
                    VALUES (%s, %s, 'legacy', 'dynadot', %s, %s, NOW(), NOW())
                    RETURNING id
                """, (target_workspace, domain_name, ns_status, dynadot_info.nameservers or None))

                new_id = cur.fetchone()["id"]
                created.append({
                    "domain": domain_name,
                    "workspace_id": target_workspace,
                    "ns_status": ns_status,
                })

    # Print summary
    print("-" * 70)
    print("SUMMARY")
    print("-" * 70)

    if updated:
        print(f"\nDomains UPDATED ({len(updated)}):")
        for d in updated:
            old_provider = d["old_provider"] or "NULL"
            ns_preview = ", ".join(d["nameservers"]) if d["nameservers"] else "(parked)"
            print(f"  ~ {d['domain']:35s}  provider={old_provider}->dynadot  ns={d['old_ns_status']}->{d['new_ns_status']}  [{ns_preview}]")

    if already_correct:
        print(f"\nDomains already correct ({len(already_correct)}):")
        for name in already_correct:
            print(f"  = {name}")

    if not_in_dynadot:
        print(f"\nDomains NOT in Dynadot account ({len(not_in_dynadot)}):")
        for name in not_in_dynadot:
            print(f"  ? {name}")

    if created:
        print(f"\nDomains CREATED ({len(created)}):")
        for d in created:
            print(f"  + {d['domain']:35s}  ns_status={d['ns_status']}")

    # Dynadot domains not in DB
    in_db = set(existing_by_name.keys())
    not_in_db = [d for d in dynadot_lookup.keys() if d not in in_db]
    if not_in_db and not args.create_missing:
        print(f"\nDynadot domains NOT in database ({len(not_in_db)}):")
        for name in sorted(not_in_db):
            print(f"  ! {name} (use --create-missing to add)")

    print()
    print("-" * 70)

    if args.execute:
        conn.commit()
        print("COMMITTED - changes written to database.")
    else:
        conn.rollback()
        print("DRY RUN - no changes written. Use --execute to apply.")

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
