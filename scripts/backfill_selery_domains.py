#!/usr/bin/env python3
"""
One-time backfill: Create domain records for Selery's EmailBison domains.

These domains were provisioned manually through Hypertide before the system
came online. The inboxes already exist in sender_accounts (synced from
EmailBison) but domain records are missing or have incorrect statuses.

This script:
  1. Finds all unique domains from Selery's sender_accounts
  2. Infers provider (entra/google) from inbox count per domain
  3. Creates missing domain records with approval_status='legacy'
  4. Updates existing domain records that overlap
  5. Sets esp_type on sender_accounts

Usage:
    py scripts/backfill_selery_domains.py              # Dry run (no changes)
    py scripts/backfill_selery_domains.py --execute     # Write to DB
"""

import psycopg2
from psycopg2.extras import RealDictCursor
import argparse
import os
import sys

SELERY_CLIENT_ID = "e5988a33-ec6c-4b5a-be85-25b8bd0678bb"
SELERY_WORKSPACE_ID = "3fabfb3c-80d1-4991-8834-70cfbe0c97b9"

# Domains with >= this many inboxes are Entra (Microsoft), below are Google
ENTRA_INBOX_THRESHOLD = 10


def main():
    parser = argparse.ArgumentParser(description="Backfill Selery domain records from sender_accounts")
    parser.add_argument("--execute", action="store_true", help="Actually write to DB (default is dry run)")
    args = parser.parse_args()

    password = os.getenv("POSTGRES_PASSWORD")
    if not password:
        print("ERROR: POSTGRES_PASSWORD environment variable required")
        print("  export POSTGRES_PASSWORD=<your_password>")
        sys.exit(1)

    conn = psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "31.97.142.123"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        database=os.getenv("POSTGRES_DB", "postgres"),
        user=os.getenv("POSTGRES_USER", "postgres"),
        password=password,
    )
    cur = conn.cursor(cursor_factory=RealDictCursor)

    print("=" * 60)
    print("Selery Domain Backfill")
    print("=" * 60)
    print(f"Client:    {SELERY_CLIENT_ID}")
    print(f"Workspace: {SELERY_WORKSPACE_ID}")
    print(f"Mode:      {'EXECUTE' if args.execute else 'DRY RUN'}")
    print()

    # Step 1: Get unique domains from sender_accounts with inbox counts
    cur.execute("""
        SELECT
            SPLIT_PART(email_address, '@', 2) as domain_name,
            COUNT(*) as inbox_count
        FROM sender_accounts
        WHERE workspace_id = %s
        GROUP BY SPLIT_PART(email_address, '@', 2)
        ORDER BY domain_name
    """, (SELERY_WORKSPACE_ID,))
    inbox_domains = cur.fetchall()

    print(f"Domains from sender_accounts: {len(inbox_domains)}")

    # Step 2: Infer provider from inbox count
    domain_providers = {}
    entra_count = 0
    google_count = 0
    for row in inbox_domains:
        name = row["domain_name"]
        count = row["inbox_count"]
        provider = "entra" if count >= ENTRA_INBOX_THRESHOLD else "google"
        domain_providers[name] = {"provider": provider, "inbox_count": count}
        if provider == "entra":
            entra_count += 1
        else:
            google_count += 1

    print(f"  Entra domains:  {entra_count}")
    print(f"  Google domains: {google_count}")
    print()

    # Step 3: Get existing domain records for this workspace
    cur.execute("""
        SELECT id, domain_name, approval_status, infrastructure_type
        FROM domains
        WHERE workspace_id = %s
    """, (SELERY_WORKSPACE_ID,))
    existing_domains = {row["domain_name"]: row for row in cur.fetchall()}

    print(f"Existing domain records: {len(existing_domains)}")
    print()

    # Step 4: Process each EmailBison domain
    inserted = []
    updated = []
    skipped = []

    for domain_name, info in sorted(domain_providers.items()):
        provider = info["provider"]
        inbox_count = info["inbox_count"]

        if domain_name in existing_domains:
            existing = existing_domains[domain_name]
            current_status = existing["approval_status"]
            current_infra = existing["infrastructure_type"]

            # Skip if already correctly set
            if current_status == "legacy" and current_infra == provider:
                skipped.append(domain_name)
                continue

            # Update existing record
            cur.execute("""
                UPDATE domains
                SET approval_status = 'legacy',
                    infrastructure_type = %s,
                    infrastructure_set_at = NOW(),
                    updated_at = NOW()
                WHERE id = %s
            """, (provider, existing["id"]))
            updated.append({
                "domain": domain_name,
                "old_status": current_status,
                "old_infra": current_infra,
                "new_infra": provider,
                "inboxes": inbox_count,
            })
        else:
            # Insert new domain record
            cur.execute("""
                INSERT INTO domains (workspace_id, domain_name, approval_status, infrastructure_type, infrastructure_set_at)
                VALUES (%s, %s, 'legacy', %s, NOW())
            """, (SELERY_WORKSPACE_ID, domain_name, provider))
            inserted.append({
                "domain": domain_name,
                "infra": provider,
                "inboxes": inbox_count,
            })

    # Step 5: Update sender_accounts esp column
    # esp enum: 'gmail', 'microsoft', 'yahoo', 'other'
    # Currently all Selery inboxes have esp='other' — set real values
    entra_domains = [name for name, info in domain_providers.items() if info["provider"] == "entra"]
    google_domains = [name for name, info in domain_providers.items() if info["provider"] == "google"]

    # Update Entra inboxes -> esp='microsoft'
    if entra_domains:
        cur.execute("""
            UPDATE sender_accounts
            SET esp = 'microsoft'
            WHERE workspace_id = %s
              AND COALESCE(esp::text, 'other') = 'other'
              AND SPLIT_PART(email_address, '@', 2) = ANY(%s)
        """, (SELERY_WORKSPACE_ID, entra_domains))
        entra_updated = cur.rowcount
    else:
        entra_updated = 0

    # Update Google inboxes -> esp='gmail'
    if google_domains:
        cur.execute("""
            UPDATE sender_accounts
            SET esp = 'gmail'
            WHERE workspace_id = %s
              AND COALESCE(esp::text, 'other') = 'other'
              AND SPLIT_PART(email_address, '@', 2) = ANY(%s)
        """, (SELERY_WORKSPACE_ID, google_domains))
        google_updated = cur.rowcount
    else:
        google_updated = 0

    # Print summary
    print("-" * 60)
    print("SUMMARY")
    print("-" * 60)

    if inserted:
        print(f"\nDomains to INSERT ({len(inserted)}):")
        for d in inserted:
            print(f"  + {d['domain']:30s}  infra={d['infra']:6s}  inboxes={d['inboxes']}")

    if updated:
        print(f"\nDomains to UPDATE ({len(updated)}):")
        for d in updated:
            print(f"  ~ {d['domain']:30s}  {d['old_status']}->legacy  infra={d['old_infra']}->{d['new_infra']}  inboxes={d['inboxes']}")

    if skipped:
        print(f"\nDomains already correct ({len(skipped)}):")
        for name in skipped:
            print(f"  = {name}")

    print(f"\nSender accounts esp updates:")
    print(f"  -> microsoft (Entra inboxes): {entra_updated}")
    print(f"  -> gmail (Google inboxes):    {google_updated}")

    print()
    print("-" * 60)

    if args.execute:
        conn.commit()
        print("COMMITTED — changes written to database.")
    else:
        conn.rollback()
        print("DRY RUN — no changes written. Use --execute to apply.")

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
