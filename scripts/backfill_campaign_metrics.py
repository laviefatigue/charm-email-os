#!/usr/bin/env python3
"""
Backfill campaign metrics from EmailBison (source of truth).

This script reuses the OwnRBL EmailBisonClient and patterns for comprehensive
campaign data extraction. It populates:
1. emailbison_campaigns - Campaign metadata
2. campaign_snapshots - Point-in-time performance metrics
3. campaign_events - Reply/bounce/unsubscribe events

Usage:
    python scripts/backfill_campaign_metrics.py [--dry-run] [--workspace NAME]

Requirements:
    - EMAILBISON_API_KEY environment variable
    - requests: pip install requests
    - asyncpg: pip install asyncpg
"""

import argparse
import asyncio
import os
import sys
import json
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict

# Add OwnRBL clients directory to path for EmailBisonClient reuse
OWNRBL_PATH = os.path.join(os.path.dirname(__file__), '..', '..', 'OwnRBL', 'clients')
sys.path.insert(0, OWNRBL_PATH)

try:
    import asyncpg
    from emailbison_client import EmailBisonClient
except ImportError as e:
    print(f"Missing dependencies: {e}")
    print("Install with: pip install asyncpg requests")
    print(f"Ensure {OWNRBL_PATH}/emailbison_client.py exists")
    sys.exit(1)


# ============================================================================
# Configuration
# ============================================================================

# Local database (Docker) - defaults for local Docker, can be overridden via args
DEFAULT_DB_HOST = "localhost"
DEFAULT_DB_PORT = 5433
DEFAULT_DB_USER = "postgres"
DEFAULT_DB_PASSWORD = "localdevpassword"
DEFAULT_DB_NAME = "postgres"


# ============================================================================
# Database Operations
# ============================================================================

async def get_workspace_mapping(db: asyncpg.Connection) -> Dict[str, str]:
    """Get mapping of EmailBison workspace ID -> local workspace UUID."""
    rows = await db.fetch("""
        SELECT id, workspace_name, emailbison_workspace_id
        FROM workspaces
        WHERE emailbison_workspace_id IS NOT NULL AND is_active = TRUE
    """)

    mapping = {}
    for row in rows:
        eb_id = row["emailbison_workspace_id"]
        if eb_id:
            mapping[str(eb_id)] = str(row["id"])

    return mapping


async def get_campaign_mapping(db: asyncpg.Connection, workspace_id: str) -> Dict[str, str]:
    """Get mapping of EmailBison campaign ID -> local campaign UUID."""
    rows = await db.fetch("""
        SELECT id, emailbison_campaign_id
        FROM emailbison_campaigns
        WHERE workspace_id = $1 AND emailbison_campaign_id IS NOT NULL
    """, workspace_id)

    return {row["emailbison_campaign_id"]: str(row["id"]) for row in rows}


async def get_sender_account_mapping(db: asyncpg.Connection, workspace_id: str) -> Dict[str, str]:
    """Get mapping of EmailBison account ID -> local sender_account UUID."""
    rows = await db.fetch("""
        SELECT id, emailbison_account_id, email_address
        FROM sender_accounts
        WHERE workspace_id = $1
    """, workspace_id)

    mapping = {}
    for row in rows:
        if row["emailbison_account_id"]:
            mapping[str(row["emailbison_account_id"])] = str(row["id"])
        if row["email_address"]:
            mapping[row["email_address"].lower()] = str(row["id"])

    return mapping


async def upsert_campaign(
    db: asyncpg.Connection,
    campaign: dict,
    workspace_id: str,
    dry_run: bool = False
) -> tuple[str, str]:
    """Insert or update emailbison_campaigns. Returns (action, local_id)."""
    eb_id = str(campaign.get("id", ""))
    if not eb_id:
        return "skipped", ""

    if dry_run:
        return "dry_run", ""

    # Check if exists
    existing = await db.fetchrow("""
        SELECT id FROM emailbison_campaigns
        WHERE emailbison_campaign_id = $1
    """, eb_id)

    emails_sent = campaign.get("emails_sent", 0) or 0
    bounced = campaign.get("bounced", 0) or 0
    bounce_rate = (bounced / emails_sent) if emails_sent > 0 else 0

    status = campaign.get("status", "Unknown")
    campaign_name = campaign.get("name", "")
    campaign_type = campaign.get("type", "")
    total_leads = campaign.get("total_leads", 0) or 0
    total_leads_contacted = campaign.get("total_leads_contacted", 0) or 0
    completion_percentage = campaign.get("completion_percentage")

    if existing:
        # Update
        await db.execute("""
            UPDATE emailbison_campaigns SET
                campaign_name = $1,
                campaign_status = $2,
                campaign_type = $3,
                total_leads = $4,
                total_leads_contacted = $5,
                emails_sent = $6,
                total_sends = $6,
                bounces = $7,
                bounce_rate = $8,
                completion_percentage = $9,
                last_seen_at = NOW(),
                updated_at = NOW()
            WHERE id = $10
        """,
            campaign_name,
            status,
            campaign_type,
            total_leads,
            total_leads_contacted,
            emails_sent,
            bounced,
            round(bounce_rate, 4),
            completion_percentage,
            existing["id"]
        )
        return "updated", str(existing["id"])
    else:
        # Insert
        row = await db.fetchrow("""
            INSERT INTO emailbison_campaigns (
                workspace_id, emailbison_campaign_id, campaign_name,
                campaign_status, campaign_type, total_leads, total_leads_contacted,
                emails_sent, total_sends, bounces, bounce_rate, completion_percentage,
                is_active, first_seen_at, last_seen_at
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $8, $9, $10, $11, $12, NOW(), NOW())
            RETURNING id
        """,
            workspace_id,
            eb_id,
            campaign_name,
            status,
            campaign_type,
            total_leads,
            total_leads_contacted,
            emails_sent,
            bounced,
            round(bounce_rate, 4),
            completion_percentage,
            status.lower() in ("active", "running", "paused")
        )
        return "inserted", str(row["id"])


async def insert_campaign_snapshot(
    db: asyncpg.Connection,
    campaign_id: str,
    campaign_details: dict,
    dry_run: bool = False
) -> str:
    """Insert a campaign snapshot using campaign details. Returns action."""
    if not campaign_id:
        return "skipped"

    if dry_run:
        return "dry_run"

    # Check if we already have a recent snapshot (within last hour)
    existing = await db.fetchval("""
        SELECT id FROM campaign_snapshots
        WHERE campaign_id = $1
        AND snapshot_timestamp > NOW() - INTERVAL '1 hour'
    """, campaign_id)

    if existing:
        return "exists"

    now = datetime.now(timezone.utc)

    # Parse campaign lifetime totals from EmailBison
    total_leads = int(campaign_details.get('total_leads', 0) or 0)
    emails_sent = int(campaign_details.get('emails_sent', 0) or 0)
    total_leads_contacted = int(campaign_details.get('total_leads_contacted', 0) or 0)
    total_opens = int(campaign_details.get('opened', 0) or 0)
    unique_opens = int(campaign_details.get('unique_opens', 0) or 0)
    unique_replies = int(campaign_details.get('unique_replies', campaign_details.get('replied', 0)) or 0)
    interested_replies = int(campaign_details.get('interested', 0) or 0)
    bounced = int(campaign_details.get('bounced', 0) or 0)
    unsubscribed = int(campaign_details.get('unsubscribed', 0) or 0)

    # Calculate rates
    open_rate = (unique_opens / total_leads_contacted * 100) if total_leads_contacted > 0 else 0.0
    reply_rate = (unique_replies / total_leads_contacted * 100) if total_leads_contacted > 0 else 0.0
    bounce_rate = (bounced / emails_sent * 100) if emails_sent > 0 else 0.0
    interested_rate = (interested_replies / unique_replies * 100) if unique_replies > 0 else 0.0
    unsubscribe_rate = (unsubscribed / emails_sent * 100) if emails_sent > 0 else 0.0

    try:
        await db.execute("""
            INSERT INTO campaign_snapshots (
                campaign_id, snapshot_timestamp, period_start, period_end,
                emails_sent, total_leads, total_leads_contacted,
                total_opens, unique_opens, unique_replies, interested_replies,
                bounced, unsubscribed, open_rate, reply_rate, bounce_rate,
                interested_rate, unsubscribe_rate, active_senders
            ) VALUES (
                $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13,
                $14, $15, $16, $17, $18, $19
            )
        """,
            campaign_id,
            now,
            now,  # period_start (point-in-time)
            now,  # period_end
            emails_sent,
            total_leads,
            total_leads_contacted,
            total_opens,
            unique_opens,
            unique_replies,
            interested_replies,
            bounced,
            unsubscribed,
            round(open_rate, 2),
            round(reply_rate, 2),
            round(bounce_rate, 2),
            round(interested_rate, 2),
            round(unsubscribe_rate, 2),
            0  # active_senders
        )
        return "inserted"
    except Exception as e:
        print(f"    [ERROR] Failed to insert snapshot: {e}")
        return "error"


async def insert_campaign_event(
    db: asyncpg.Connection,
    campaign_id: str,
    event: dict,
    event_type: str,
    sender_mapping: Dict[str, str],
    dry_run: bool = False
) -> str:
    """Insert a campaign event (reply/bounce/unsubscribe). Returns action."""
    if not campaign_id:
        return "skipped"

    if dry_run:
        return "dry_run"

    event_id = event.get('id')
    lead_id = event.get('lead_id')
    lead_email = event.get('from_email_address') or event.get('email')
    lead_name = event.get('from_name') or event.get('name')
    sender_email_id = event.get('sender_email_id')

    # Check if event already exists
    existing = await db.fetchval("""
        SELECT id FROM campaign_events
        WHERE campaign_id = $1
        AND event_type = $2
        AND (event_data->>'event_id' = $3 OR emailbison_lead_id = $4)
    """, campaign_id, event_type, str(event_id), str(lead_id) if lead_id else None)

    if existing:
        return "exists"

    # Lookup sender_account_id
    sender_account_id = None
    if sender_email_id:
        sender_account_id = sender_mapping.get(str(sender_email_id))

    event_data = {
        "event_id": event_id,
        "subject": event.get('subject'),
        "folder": event.get('folder'),
        "interested": event.get('interested', False),
        "automated_reply": event.get('automated_reply', False),
        "received_at": event.get('received_at'),
        "sender_email_id": sender_email_id,
        "sender_inbox": event.get('primary_to_email_address')
    }

    try:
        await db.execute("""
            INSERT INTO campaign_events (
                campaign_id, event_type, emailbison_lead_id,
                lead_email, lead_name, sender_account_id, event_data
            ) VALUES ($1, $2, $3, $4, $5, $6, $7)
        """,
            campaign_id,
            event_type,
            str(lead_id) if lead_id else None,
            lead_email,
            lead_name,
            sender_account_id,
            json.dumps(event_data)
        )
        return "inserted"
    except Exception as e:
        print(f"    [ERROR] Failed to insert event: {e}")
        return "error"


# ============================================================================
# Main
# ============================================================================

async def main():
    parser = argparse.ArgumentParser(description="Backfill campaign metrics from EmailBison")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without writing")
    parser.add_argument("--workspace", help="Sync specific workspace only (by name)")
    parser.add_argument("--skip-snapshots", action="store_true", help="Skip snapshot creation")
    parser.add_argument("--skip-events", action="store_true", help="Skip event fetching")
    parser.add_argument("--events-limit", type=int, default=100, help="Max events per campaign")
    # Database connection args - default to LOCAL Docker
    parser.add_argument("--db-host", default=DEFAULT_DB_HOST, help=f"Database host (default: {DEFAULT_DB_HOST})")
    parser.add_argument("--db-port", type=int, default=DEFAULT_DB_PORT, help=f"Database port (default: {DEFAULT_DB_PORT})")
    parser.add_argument("--db-user", default=DEFAULT_DB_USER, help=f"Database user (default: {DEFAULT_DB_USER})")
    parser.add_argument("--db-password", default=DEFAULT_DB_PASSWORD, help="Database password")
    parser.add_argument("--db-name", default=DEFAULT_DB_NAME, help=f"Database name (default: {DEFAULT_DB_NAME})")
    args = parser.parse_args()

    print("=" * 60)
    print("EmailBison Campaign Metrics Backfill")
    print("=" * 60)
    print(f"Mode: {'DRY RUN' if args.dry_run else 'LIVE'}")
    print(f"Target: {args.db_host}:{args.db_port}/{args.db_name}")
    print(f"Using: OwnRBL EmailBisonClient")
    print()

    # Initialize EmailBison client (uses EMAILBISON_API_KEY from env)
    try:
        client = EmailBisonClient(
            base_url=os.environ.get("EMAILBISON_BASE_URL", "https://spellcast.hirecharm.com"),
            api_key=os.environ.get("EMAILBISON_API_KEY")
        )
        print("Connected to EmailBison API")
    except ValueError as e:
        print(f"[ERROR] {e}")
        sys.exit(1)

    # Connect to database
    print("Connecting to database...")
    db = await asyncpg.connect(
        host=args.db_host,
        port=args.db_port,
        user=args.db_user,
        password=args.db_password,
        database=args.db_name
    )

    # Get initial counts
    campaigns_count = await db.fetchval("SELECT COUNT(*) FROM emailbison_campaigns")
    snapshots_count = await db.fetchval("SELECT COUNT(*) FROM campaign_snapshots")
    events_count = await db.fetchval("SELECT COUNT(*) FROM campaign_events")
    print(f"Current emailbison_campaigns: {campaigns_count}")
    print(f"Current campaign_snapshots: {snapshots_count}")
    print(f"Current campaign_events: {events_count}")
    print()

    # Get workspace mapping
    print("Loading workspace mapping...")
    workspace_mapping = await get_workspace_mapping(db)
    print(f"Found {len(workspace_mapping)} workspaces with EmailBison IDs")
    print()

    # Get workspaces from EmailBison
    print("Fetching EmailBison workspaces...")
    eb_workspaces = client.list_workspaces()
    print(f"Found {len(eb_workspaces)} workspaces in EmailBison")
    print()

    stats = {
        "workspaces_processed": 0,
        "campaigns_fetched": 0,
        "campaigns_inserted": 0,
        "campaigns_updated": 0,
        "snapshots_inserted": 0,
        "events_inserted": 0,
        "errors": 0,
    }

    # Process each workspace
    for eb_ws in eb_workspaces:
        eb_id = str(eb_ws.get("id"))
        eb_name = eb_ws.get("name", "Unknown")

        # Filter by workspace name if specified
        if args.workspace and eb_name.lower() != args.workspace.lower():
            continue

        # Check if we have a local mapping
        if eb_id not in workspace_mapping:
            print(f"[SKIP] {eb_name} (ID: {eb_id}) - no local workspace mapping")
            continue

        local_ws_id = workspace_mapping[eb_id]
        print(f"[SYNC] {eb_name} (EmailBison ID: {eb_id})")

        # Switch to workspace
        try:
            client.switch_workspace(int(eb_id))
        except Exception as e:
            print(f"       [ERROR] Failed to switch workspace: {e}")
            stats["errors"] += 1
            continue

        # Fetch ALL campaigns with pagination (using OwnRBL pattern)
        campaigns = client.list_all_campaigns()
        print(f"       Found {len(campaigns)} campaigns")
        stats["campaigns_fetched"] += len(campaigns)

        # Get campaign and sender mappings
        campaign_mapping = await get_campaign_mapping(db, local_ws_id)
        sender_mapping = await get_sender_account_mapping(db, local_ws_id)

        # Process each campaign
        for campaign in campaigns:
            campaign_name = campaign.get("name", "Unknown")
            eb_campaign_id = str(campaign.get("id"))

            try:
                # Upsert campaign (using list data, no detail fetch needed)
                action, local_campaign_id = await upsert_campaign(
                    db, campaign, local_ws_id, dry_run=args.dry_run
                )

                if action == "inserted":
                    stats["campaigns_inserted"] += 1
                    campaign_mapping[eb_campaign_id] = local_campaign_id
                elif action == "updated":
                    stats["campaigns_updated"] += 1
                    if eb_campaign_id not in campaign_mapping:
                        campaign_mapping[eb_campaign_id] = local_campaign_id

                # Get local campaign ID
                local_campaign_id = campaign_mapping.get(eb_campaign_id)
                if not local_campaign_id:
                    continue

                # Create snapshot - requires workspace switch before detail fetch
                if not args.skip_snapshots:
                    try:
                        # CRITICAL: Switch workspace before EACH campaign detail fetch
                        # (following OwnRBL pattern from campaign_sync_tasks.py:325-329)
                        client.switch_workspace(int(eb_id))
                        campaign_details = client.get_campaign_details(eb_campaign_id)
                        result = await insert_campaign_snapshot(
                            db, local_campaign_id, campaign_details, dry_run=args.dry_run
                        )
                        if result == "inserted":
                            stats["snapshots_inserted"] += 1
                    except Exception as e:
                        print(f"       [WARN] Snapshot for '{campaign_name}': {e}")

                # Fetch events (replies and bounces) - also requires workspace context
                if not args.skip_events:
                    try:
                        # Switch workspace for event fetching
                        client.switch_workspace(int(eb_id))

                        # Fetch replies
                        reply_response = client.get_campaign_replies(
                            eb_campaign_id, folder='inbox', limit=args.events_limit
                        )
                        replies = reply_response.get('data', [])

                        for reply in replies:
                            event_type = "interested_reply" if reply.get('interested') else (
                                "automated_reply" if reply.get('automated_reply') else "reply"
                            )
                            result = await insert_campaign_event(
                                db, local_campaign_id, reply, event_type,
                                sender_mapping, dry_run=args.dry_run
                            )
                            if result == "inserted":
                                stats["events_inserted"] += 1

                        # Fetch bounces
                        bounce_response = client.get_campaign_replies(
                            eb_campaign_id, folder='bounced', limit=args.events_limit
                        )
                        bounces = bounce_response.get('data', [])

                        for bounce in bounces:
                            result = await insert_campaign_event(
                                db, local_campaign_id, bounce, "bounce",
                                sender_mapping, dry_run=args.dry_run
                            )
                            if result == "inserted":
                                stats["events_inserted"] += 1
                    except Exception as e:
                        print(f"       [WARN] Events for '{campaign_name}': {e}")

            except Exception as e:
                stats["errors"] += 1
                print(f"       [ERROR] Campaign '{campaign_name}': {e}")

        stats["workspaces_processed"] += 1
        print(f"       Processed: +{stats['campaigns_inserted']} new, ~{stats['campaigns_updated']} updated")

    print()

    # Final counts
    final_campaigns = await db.fetchval("SELECT COUNT(*) FROM emailbison_campaigns")
    final_snapshots = await db.fetchval("SELECT COUNT(*) FROM campaign_snapshots")
    final_events = await db.fetchval("SELECT COUNT(*) FROM campaign_events")

    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Workspaces processed: {stats['workspaces_processed']}")
    print(f"Campaigns fetched:    {stats['campaigns_fetched']}")
    print(f"Campaigns inserted:   {stats['campaigns_inserted']}")
    print(f"Campaigns updated:    {stats['campaigns_updated']}")
    print(f"Snapshots created:    {stats['snapshots_inserted']}")
    print(f"Events created:       {stats['events_inserted']}")
    print(f"Errors:               {stats['errors']}")
    print()
    print(f"emailbison_campaigns: {campaigns_count} -> {final_campaigns} ({'+' if final_campaigns >= campaigns_count else ''}{final_campaigns - campaigns_count})")
    print(f"campaign_snapshots:   {snapshots_count} -> {final_snapshots} ({'+' if final_snapshots >= snapshots_count else ''}{final_snapshots - snapshots_count})")
    print(f"campaign_events:      {events_count} -> {final_events} ({'+' if final_events >= events_count else ''}{final_events - events_count})")

    await db.close()


if __name__ == "__main__":
    asyncio.run(main())
