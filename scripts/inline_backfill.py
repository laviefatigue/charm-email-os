#!/usr/bin/env python3
"""
Self-contained EmailBison Campaign Backfill Script.
Runs inside Docker container with no external dependencies.
"""
import os
import asyncio
import json
from datetime import datetime, timezone

import asyncpg
import httpx

# Configuration
EMAILBISON_API_KEY = os.environ.get("EMAILBISON_API_KEY", "")
EMAILBISON_BASE_URL = "https://spellcast.hirecharm.com"

class EmailBisonClient:
    def __init__(self, api_key, base_url):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.session = httpx.Client(
            timeout=60.0,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Accept": "application/json",
                "Content-Type": "application/json"
            }
        )

    def switch_workspace(self, workspace_id):
        resp = self.session.post(
            f"{self.base_url}/api/workspaces/v1.1/switch-workspace",
            json={"team_id": workspace_id}
        )
        resp.raise_for_status()
        return resp.json()

    def list_workspaces(self):
        resp = self.session.get(f"{self.base_url}/api/workspaces/v1.1")
        resp.raise_for_status()
        return resp.json().get("data", [])

    def list_campaigns(self, page=1):
        resp = self.session.get(
            f"{self.base_url}/api/campaigns",
            params={"page": page, "limit": 100}
        )
        resp.raise_for_status()
        return resp.json()

    def get_campaign_details(self, campaign_id):
        resp = self.session.get(f"{self.base_url}/api/campaigns/{campaign_id}")
        resp.raise_for_status()
        return resp.json().get("data", resp.json())

    def get_campaign_replies(self, campaign_id, folder="inbox", limit=100):
        resp = self.session.get(
            f"{self.base_url}/api/campaigns/{campaign_id}/replies",
            params={"folder": folder, "limit": limit}
        )
        resp.raise_for_status()
        return resp.json()


async def main():
    print("=" * 60)
    print("EmailBison Campaign Metrics Backfill")
    print("=" * 60)

    if not EMAILBISON_API_KEY:
        print("ERROR: EMAILBISON_API_KEY not set")
        return

    client = EmailBisonClient(EMAILBISON_API_KEY, EMAILBISON_BASE_URL)
    print("Connected to EmailBison API")

    db = await asyncpg.connect(
        host="postgres", port=5432, user="postgres",
        password="localdevpassword", database="postgres"
    )
    print("Connected to database")

    # Get current counts
    campaigns_count = await db.fetchval("SELECT COUNT(*) FROM emailbison_campaigns")
    snapshots_count = await db.fetchval("SELECT COUNT(*) FROM campaign_snapshots")
    events_count = await db.fetchval("SELECT COUNT(*) FROM campaign_events")
    print(f"Current: campaigns={campaigns_count}, snapshots={snapshots_count}, events={events_count}")

    # Get workspace mapping
    ws_rows = await db.fetch("""
        SELECT id, workspace_name, emailbison_workspace_id
        FROM workspaces WHERE emailbison_workspace_id IS NOT NULL AND is_active = TRUE
    """)
    ws_map = {str(r["emailbison_workspace_id"]): str(r["id"]) for r in ws_rows}
    print(f"Found {len(ws_map)} workspaces with EmailBison IDs")

    # Get EmailBison workspaces
    eb_workspaces = client.list_workspaces()
    print(f"Found {len(eb_workspaces)} workspaces in EmailBison")

    stats = {"campaigns": 0, "snapshots": 0, "events": 0, "errors": 0}

    for eb_ws in eb_workspaces:
        eb_id = str(eb_ws.get("id"))
        eb_name = eb_ws.get("name", "Unknown")

        if eb_id not in ws_map:
            continue

        local_ws_id = ws_map[eb_id]
        print(f"\n[SYNC] {eb_name}")

        try:
            client.switch_workspace(int(eb_id))
        except Exception as e:
            print(f"  [ERROR] Switch workspace: {e}")
            continue

        # Fetch campaigns with pagination
        all_campaigns = []
        page = 1
        while True:
            data = client.list_campaigns(page)
            campaigns = data.get("data", [])
            if not campaigns:
                break
            all_campaigns.extend(campaigns)
            meta = data.get("meta", {})
            if page >= meta.get("last_page", 1):
                break
            page += 1

        print(f"  Found {len(all_campaigns)} campaigns")

        for campaign in all_campaigns:
            eb_cid = str(campaign.get("id"))
            cname = campaign.get("name", "Unknown")

            # Get or create campaign record
            local_cid = await db.fetchval(
                "SELECT id FROM emailbison_campaigns WHERE emailbison_campaign_id = $1",
                eb_cid
            )

            if not local_cid:
                # Insert new campaign
                local_cid = await db.fetchval("""
                    INSERT INTO emailbison_campaigns (
                        workspace_id, emailbison_campaign_id, campaign_name,
                        campaign_status, emails_sent, total_sends, bounces,
                        is_active, first_seen_at, last_seen_at
                    ) VALUES ($1, $2, $3, $4, $5, $5, $6, $7, NOW(), NOW())
                    RETURNING id
                """,
                    local_ws_id, eb_cid, cname,
                    campaign.get("status", "Unknown"),
                    campaign.get("emails_sent", 0) or 0,
                    campaign.get("bounced", 0) or 0,
                    True
                )
                stats["campaigns"] += 1

            # Fetch campaign details for snapshot
            try:
                # CRITICAL: Switch workspace before each campaign detail fetch
                client.switch_workspace(int(eb_id))
                details = client.get_campaign_details(eb_cid)

                # Check for recent snapshot (avoid duplicates)
                existing = await db.fetchval("""
                    SELECT id FROM campaign_snapshots
                    WHERE campaign_id = $1 AND snapshot_timestamp > NOW() - INTERVAL '1 hour'
                """, local_cid)

                if not existing:
                    emails_sent = int(details.get("emails_sent", 0) or 0)
                    total_leads = int(details.get("total_leads", 0) or 0)
                    contacted = int(details.get("total_leads_contacted", 0) or 0)
                    opens = int(details.get("unique_opens", 0) or 0)
                    replies = int(details.get("unique_replies", details.get("replied", 0)) or 0)
                    bounced = int(details.get("bounced", 0) or 0)
                    interested = int(details.get("interested", 0) or 0)

                    open_rate = (opens / contacted * 100) if contacted > 0 else 0
                    reply_rate = (replies / contacted * 100) if contacted > 0 else 0
                    bounce_rate = (bounced / emails_sent * 100) if emails_sent > 0 else 0

                    from datetime import timedelta
                    now = datetime.now(timezone.utc)
                    period_start = now - timedelta(days=1)  # Yesterday
                    period_end = now  # period_end > period_start required by constraint
                    await db.execute("""
                        INSERT INTO campaign_snapshots (
                            campaign_id, snapshot_timestamp, period_start, period_end,
                            emails_sent, total_leads, total_leads_contacted,
                            unique_opens, unique_replies, interested_replies, bounced,
                            open_rate, reply_rate, bounce_rate, active_senders
                        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, 0)
                    """,
                        local_cid, now, period_start, period_end,
                        emails_sent, total_leads, contacted,
                        opens, replies, interested, bounced,
                        round(open_rate, 2), round(reply_rate, 2), round(bounce_rate, 2)
                    )
                    stats["snapshots"] += 1

                # Fetch replies and bounces
                for folder in ["inbox", "bounced"]:
                    try:
                        reply_data = client.get_campaign_replies(eb_cid, folder=folder, limit=50)
                        events = reply_data.get("data", [])
                        for event in events:
                            event_id = event.get("id")
                            lead_id = event.get("lead_id")

                            existing = await db.fetchval("""
                                SELECT id FROM campaign_events
                                WHERE campaign_id = $1 AND emailbison_lead_id = $2
                            """, local_cid, str(lead_id) if lead_id else None)

                            if not existing and lead_id:
                                event_type = "bounce" if folder == "bounced" else (
                                    "interested_reply" if event.get("interested") else "reply"
                                )
                                await db.execute("""
                                    INSERT INTO campaign_events (
                                        campaign_id, event_type, emailbison_lead_id,
                                        lead_email, lead_name, event_data
                                    ) VALUES ($1, $2, $3, $4, $5, $6)
                                """,
                                    local_cid, event_type, str(lead_id),
                                    event.get("from_email_address"),
                                    event.get("from_name"),
                                    json.dumps({"event_id": event_id, "folder": folder})
                                )
                                stats["events"] += 1
                    except Exception as e:
                        pass  # Continue on event fetch errors

            except Exception as e:
                stats["errors"] += 1
                print(f"  [WARN] {cname}: {e}")

    # Final counts
    final_campaigns = await db.fetchval("SELECT COUNT(*) FROM emailbison_campaigns")
    final_snapshots = await db.fetchval("SELECT COUNT(*) FROM campaign_snapshots")
    final_events = await db.fetchval("SELECT COUNT(*) FROM campaign_events")

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Campaigns: {campaigns_count} -> {final_campaigns} (+{stats['campaigns']})")
    print(f"Snapshots: {snapshots_count} -> {final_snapshots} (+{stats['snapshots']})")
    print(f"Events: {events_count} -> {final_events} (+{stats['events']})")
    print(f"Errors: {stats['errors']}")

    await db.close()


if __name__ == "__main__":
    asyncio.run(main())
