#!/usr/bin/env python3
"""
Analyze Reserve Capacity for All Workspaces

Queries v_client_capacity to determine:
1. Which workspaces have surplus capacity (can afford reserve)
2. Which workspaces are at or below threshold (all live)
3. Recommended reserve pool sizes

Run in production container:
    docker exec emailbison-sync python /app/scripts/analyze_reserve_capacity.py

Or locally with production DB credentials.

Usage:
    python scripts/analyze_reserve_capacity.py
"""
import asyncio
import os
import sys
from typing import Dict, List

import asyncpg

# Database connection
POSTGRES_HOST = os.getenv('POSTGRES_HOST', 'localhost')
POSTGRES_PORT = int(os.getenv('POSTGRES_PORT', 5432))
POSTGRES_USER = os.getenv('POSTGRES_USER', 'postgres')
POSTGRES_PASSWORD = os.getenv('POSTGRES_PASSWORD', 'localdevpassword')
POSTGRES_DB = os.getenv('POSTGRES_DB', 'postgres')


async def analyze_capacity():
    """Query v_client_capacity and analyze reserve potential."""

    conn = await asyncpg.connect(
        host=POSTGRES_HOST,
        port=POSTGRES_PORT,
        user=POSTGRES_USER,
        password=POSTGRES_PASSWORD,
        database=POSTGRES_DB
    )

    try:
        # Query the capacity view
        rows = await conn.fetch("""
            SELECT
                client_name,
                workspace_id,

                -- Entra
                entra_inboxes_target,
                entra_inboxes_live,
                entra_inboxes_reserve,
                entra_inboxes_incubating,
                entra_inbox_gap,
                entra_buffer_ratio,

                -- Google
                google_inboxes_target,
                google_inboxes_live,
                google_inboxes_reserve,
                google_inboxes_incubating,
                google_inbox_gap,
                google_buffer_ratio,

                target_buffer_ratio
            FROM v_client_capacity
            WHERE client_name IS NOT NULL
            ORDER BY client_name
        """)

        print("="*100)
        print("RESERVE CAPACITY ANALYSIS - ALL WORKSPACES")
        print("="*100)
        print()

        total_can_reserve = 0
        total_no_reserve = 0

        for row in rows:
            client = row['client_name']
            target_ratio = row['target_buffer_ratio'] or 0.15

            # Entra analysis
            entra_target = row['entra_inboxes_target'] or 0
            entra_live = row['entra_inboxes_live'] or 0
            entra_reserve = row['entra_inboxes_reserve'] or 0
            entra_incubating = row['entra_inboxes_incubating'] or 0
            entra_gap = row['entra_inbox_gap'] or 0

            # Google analysis
            google_target = row['google_inboxes_target'] or 0
            google_live = row['google_inboxes_live'] or 0
            google_reserve = row['google_inboxes_reserve'] or 0
            google_incubating = row['google_inboxes_incubating'] or 0
            google_gap = row['google_inbox_gap'] or 0

            # Calculate surplus
            entra_surplus = entra_live - entra_target
            google_surplus = google_live - google_target

            # Recommended reserve (target_ratio of target, capped by surplus)
            entra_reserve_recommended = min(
                int(entra_target * target_ratio),  # Ideal: 15% of target
                max(0, entra_surplus)  # Can't reserve more than surplus
            )
            google_reserve_recommended = min(
                int(google_target * target_ratio),
                max(0, google_surplus)
            )

            can_reserve = (entra_reserve_recommended > 0 or google_reserve_recommended > 0)

            if can_reserve:
                total_can_reserve += 1
            else:
                total_no_reserve += 1

            # Print analysis
            print(f"## {client}")
            print(f"   Target Buffer Ratio: {target_ratio*100:.0f}%")
            print()

            if entra_target > 0:
                status = "SURPLUS" if entra_surplus > 0 else "DEFICIT" if entra_surplus < 0 else "AT TARGET"
                print(f"   ENTRA:")
                print(f"     Target: {entra_target:,} | Live: {entra_live:,} | Gap: {entra_gap}")
                print(f"     Surplus/Deficit: {entra_surplus:+,} ({status})")
                print(f"     Current Reserve: {entra_reserve:,} | Incubating: {entra_incubating:,}")
                print(f"     Recommended Reserve: {entra_reserve_recommended:,} inboxes")
                if entra_reserve_recommended == 0 and entra_surplus <= 0:
                    print(f"     → ALL LIVE (no surplus to reserve)")
                print()

            if google_target > 0:
                status = "SURPLUS" if google_surplus > 0 else "DEFICIT" if google_surplus < 0 else "AT TARGET"
                print(f"   GOOGLE:")
                print(f"     Target: {google_target:,} | Live: {google_live:,} | Gap: {google_gap}")
                print(f"     Surplus/Deficit: {google_surplus:+,} ({status})")
                print(f"     Current Reserve: {google_reserve:,} | Incubating: {google_incubating:,}")
                print(f"     Recommended Reserve: {google_reserve_recommended:,} inboxes")
                if google_reserve_recommended == 0 and google_surplus <= 0:
                    print(f"     → ALL LIVE (no surplus to reserve)")
                print()

            print("-"*100)

        print()
        print("="*100)
        print("SUMMARY")
        print("="*100)
        print(f"Workspaces that CAN have reserve pool: {total_can_reserve}")
        print(f"Workspaces with NO reserve capacity: {total_no_reserve}")
        print()
        print("LOGIC:")
        print("  - If live > target → surplus exists → can create reserve")
        print("  - If live <= target → at/below threshold → ALL LIVE (no reserve)")
        print("  - Reserve size = min(target * buffer_ratio, surplus)")
        print()

    finally:
        await conn.close()


async def main():
    await analyze_capacity()


if __name__ == '__main__':
    asyncio.run(main())
