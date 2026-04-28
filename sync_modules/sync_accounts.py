"""
Account & Domain Sync Module

Synchronizes sender accounts and domains from EmailBison.

Architecture (workspace-concurrent model):
    This module is designed for per-workspace parallel execution.
    It is called by WorkspaceSyncQueue._dispatch() with a workspace-scoped
    EmailBisonClient already initialised with the per-workspace API key.

    Contract:
        - Caller is responsible for passing a client scoped to the correct workspace.
        - NO switch_workspace() call is made here.  The workspace-scoped API key
          (stored in workspace_api_keys, migration 089) is context-bound at creation
          time — every request it makes is already scoped to one workspace.
        - sync_workspace(workspace_id, workspace_name) operates on one workspace only.
        - sync_all_domains() is a pure-SQL global operation with no API calls;
          it is safe to call concurrently from multiple workspace tasks and is
          invoked as a post-hook by WorkspaceSyncQueue after each accounts sync.

    Removed (old sequential model):
        - sync_all_workspaces()   — replaced by WorkspaceSyncQueue scheduler
        - emailbison_workspace_id param — no longer needed; client is pre-scoped
        - switch_workspace() call  — eliminated by workspace-scoped API keys
        - inter_batch_delay()      — no shared client = no shared rate limit
"""
from datetime import datetime
from typing import Dict, Optional
from uuid import UUID
import asyncpg

from .emailbison_client import EmailBisonClient, EmailBisonAPIError
from .audit_logger import AuditLogger, AuditContext, SyncResult
from .slack_alerter import SlackAlerter


# ESP mapping from EmailBison provider names to our enum
ESP_MAP = {
    'Google': 'gmail',
    'Microsoft': 'microsoft',
    'Yahoo': 'yahoo',
    'SMTP': 'other',
    'Other': 'other'
}


def calculate_health_score(account: Dict) -> int:
    """
    Calculate a 0-100 health score for an inbox.

    Factors:
    - Connection status (40 points)
    - Bounce rate (20 points)
    - Spam rate (20 points)
    - Reply rate (10 points)
    - Daily limit usage (10 points)

    Matches the calculation used by EmailBison MCP analytics.
    """
    score = 0

    # Connection status (40 points)
    # Microsoft IMAP disconnects are transient (~10 min auto-reconnect per EmailBison support)
    # Don't penalize Microsoft as heavily - likely reconnecting already
    # Gmail/other disconnects are almost always expired OAuth requiring manual reconnection
    status = account.get("status", "")
    if status == "Connected":
        score += 40
    elif status == "Not connected":
        provider = (account.get("type") or "").lower()
        if "microsoft" in provider:
            score += 25  # Transient IMAP blip, partial credit
        else:
            score += 0   # Gmail/other: likely real OAuth expiry
    else:
        score += 20  # Unknown/other status

    # Get email stats (flat fields from EmailBison API)
    sent = account.get("emails_sent_count", 0) or 1  # Avoid division by zero
    bounced = account.get("bounced_count", 0)
    replied = account.get("total_replied_count", 0)

    # Bounce rate (20 points) - lower is better
    bounce_rate = bounced / max(sent, 1)
    if bounce_rate < 0.02:  # < 2%
        score += 20
    elif bounce_rate < 0.05:  # 2-5%
        score += 15
    elif bounce_rate < 0.10:  # 5-10%
        score += 10
    # else: > 10% = 0 points

    # Spam rate (20 points) - assume low spam if not tracking
    warmup_spam = account.get("warmup_spam_count", 0)
    spam_rate = warmup_spam / max(sent, 1) if warmup_spam else 0
    if spam_rate < 0.01:  # < 1%
        score += 20
    elif spam_rate < 0.03:  # 1-3%
        score += 15
    elif spam_rate < 0.05:  # 3-5%
        score += 10
    # else: > 5% = 0 points

    # Reply rate (10 points) - higher is better
    reply_rate = replied / max(sent, 1)
    if reply_rate > 0.10:  # > 10%
        score += 10
    elif reply_rate > 0.05:  # 5-10%
        score += 7
    elif reply_rate > 0.02:  # 2-5%
        score += 5
    else:  # < 2%
        score += 3

    # Daily limit usage (10 points) - warmup inboxes get bonus
    warmup_enabled = account.get("warmup_enabled", False)
    if warmup_enabled:
        # Warmup inboxes get full points (they're being managed)
        score += 10
    else:
        # Non-warmup: give partial points based on activity
        daily_limit = account.get("daily_limit", 0)
        if daily_limit > 0:
            score += 7
        else:
            score += 5

    return min(100, max(0, score))


class AccountSyncModule:
    """Synchronizes sender accounts and domains from EmailBison."""

    def __init__(
        self,
        db: asyncpg.Pool,
        client: EmailBisonClient,
        audit_logger: AuditLogger,
        alerter: SlackAlerter = None
    ):
        self.db = db
        self.client = client
        self.audit_logger = audit_logger
        self.alerter = alerter or SlackAlerter()

    async def sync_workspace(
        self,
        workspace_id: UUID,
        workspace_name: str,
    ) -> SyncResult:
        """
        Sync accounts for a single workspace.

        The EmailBisonClient (self.client) must already be scoped to this
        workspace via its API key.  No switch_workspace() call is made here.
        Called by WorkspaceSyncQueue._dispatch() with a per-workspace client.
        """
        audit = await self.audit_logger.start_audit(
            sync_type='accounts',
            workspace_id=workspace_id,
            metadata={'workspace_name': workspace_name}
        )

        try:
            # Fetch all accounts from EmailBison
            accounts = await self.client.get_all_sender_accounts()
            print(f"  [{workspace_name}] Found {len(accounts)} accounts in EmailBison")

            # Track existing accounts for stale detection
            existing_eb_ids = set()

            # Upsert each account
            for account in accounts:
                audit.increment_processed()

                try:
                    created = await self.upsert_account(workspace_id, account)
                    if created:
                        audit.increment_created()
                    else:
                        audit.increment_updated()

                    eb_id = account.get('id')
                    if eb_id:
                        existing_eb_ids.add(str(eb_id))

                except Exception as e:
                    audit.add_error(
                        record_id=account.get('email'),
                        error=str(e),
                        details={'emailbison_id': account.get('id')}
                    )

            # Mark stale accounts (in our DB but not in EmailBison)
            await self.mark_stale_accounts(workspace_id, existing_eb_ids)

            # Update sync status for incremental syncing
            await self.audit_logger.update_sync_status(
                sync_type='accounts',
                workspace_id=workspace_id,
                record_count=len(accounts)
            )

            return await audit.complete()

        except Exception as e:
            return await audit.fail(e)

    async def upsert_account(self, workspace_id: UUID, account: Dict) -> bool:
        """
        Upsert a sender account from EmailBison data.

        Returns:
            True if created, False if updated
        """
        email = account.get('email', '').lower().strip()
        if not email:
            raise ValueError("Account missing email address")

        # Check if this email already exists in a DIFFERENT workspace (data isolation check)
        # Each email should only exist once globally
        existing = await self.db.fetchrow("""
            SELECT workspace_id, email_address FROM sender_accounts WHERE email_address = $1
        """, email)

        if existing and existing['workspace_id'] != workspace_id:
            # Email exists in different workspace - skip to prevent cross-workspace pollution
            print(f"    [SKIP] {email} already exists in workspace {existing['workspace_id']}, skipping")
            return False

        # Map EmailBison fields to our schema
        eb_id = str(account.get('id', ''))
        status = account.get('status') or account.get('connection_status') or 'Unknown'
        provider = account.get('provider') or ''

        # Determine inbox state
        # IMPORTANT: Disconnected != Dead
        # - 'dead' = killed by trigger for bad behavior (bounces, spam complaints)
        # - 'live' = available for campaigns (even if currently disconnected)
        # - Disconnected inboxes stay 'live' but have status='Not connected' for tracking
        # Only 'Disabled' (explicit user action in EmailBison) marks as dead
        inbox_state = 'dead' if status == 'Disabled' else 'live'

        # Get ESP
        esp = ESP_MAP.get(provider, 'other')

        # Get tags for provider detection if no provider
        if not provider:
            tags = account.get('tags', [])
            for tag in tags:
                tag_name = tag.get('name', '').lower()
                if 'google' in tag_name or 'gmail' in tag_name:
                    esp = 'gmail'
                    break
                elif 'microsoft' in tag_name or 'outlook' in tag_name:
                    esp = 'microsoft'
                    break

        # Extract metrics
        # Calculate health score from account data (EmailBison API doesn't return health_score directly)
        health_score = calculate_health_score(account)
        bounce_rate = account.get('bounce_rate', 0) or 0

        # Extract all-time metrics from EmailBison (matches EmailBison UI)
        emails_sent_all_time = account.get('emails_sent_count', 0) or 0
        replies_all_time = account.get('total_replied_count', 0) or 0
        bounces_all_time = account.get('bounced_count', 0) or 0
        daily_limit = account.get('daily_limit', 0) or 0

        # Extract warmup data (for monitoring only, NOT kill triggers)
        warmup_enabled = account.get('warmup_enabled', False)
        warmup_score = account.get('warmup_score')  # 0-100 or None
        warmup_spam_count = account.get('warmup_spam_count', 0) or 0  # Emails landing in spam during warmup
        warmup_bounces_received = account.get('warmup_bounces_received_count', 0) or 0
        warmup_bounces_caused = account.get('warmup_bounces_caused_count', 0) or 0

        # Extract EB created_at — the true date the inbox was uploaded to EmailBison.
        # This is more accurate than NOW() for warmup_started_at because workspace access
        # via invites may occur after inboxes are already running/warmed.
        eb_created_at = None
        eb_created_str = account.get('created_at')
        if eb_created_str:
            try:
                # EB format: "2026-01-25T02:15:44.000000Z"
                eb_created_at = datetime.fromisoformat(eb_created_str.replace('Z', '+00:00'))
            except (ValueError, AttributeError):
                pass  # Fall back to NOW() in SQL if parsing fails

        # Calculate initial inventory status for new inboxes
        # inventory_pool_status = NULL means "dead or not yet assigned" (per migration 074)
        # Incubating inboxes haven't been assigned to a pool yet, so they stay NULL
        initial_lifecycle = 'dead' if inbox_state == 'dead' else 'incubating'
        initial_pool = None  # Always NULL for new inboxes - pool assignment happens later

        result = await self.db.fetchrow("""
            INSERT INTO sender_accounts (
                workspace_id,
                email_address,
                emailbison_account_id,
                display_name,
                status,
                inbox_state,
                esp,
                health_score,
                bounce_rate_7d,
                complaints_lifetime,
                warmup_enabled,
                emails_sent_all_time,
                replies_all_time,
                bounces_all_time,
                daily_limit,
                is_active,
                inventory_lifecycle_status,
                inventory_pool_status,
                disconnected_at,
                warmup_score,
                warmup_spam_count,
                warmup_bounces_received,
                warmup_bounces_caused,
                first_seen_at,
                last_seen_at,
                last_synced_at,
                warmup_started_at
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19, $20, $21, $22, $23, COALESCE($24, NOW()), NOW(), NOW(), CASE WHEN $11 = TRUE THEN $24 ELSE NULL END)
            ON CONFLICT (email_address) DO UPDATE SET
                emailbison_account_id = EXCLUDED.emailbison_account_id,
                display_name = COALESCE(EXCLUDED.display_name, sender_accounts.display_name),
                status = EXCLUDED.status,
                inbox_state = CASE
                    WHEN sender_accounts.killed_at IS NOT NULL THEN 'dead'
                    ELSE EXCLUDED.inbox_state
                END,
                esp = COALESCE(EXCLUDED.esp, sender_accounts.esp),
                health_score = EXCLUDED.health_score,
                bounce_rate_7d = EXCLUDED.bounce_rate_7d,
                complaints_lifetime = GREATEST(
                    COALESCE(EXCLUDED.complaints_lifetime, 0),
                    COALESCE(sender_accounts.complaints_lifetime, 0)
                ),
                warmup_enabled = EXCLUDED.warmup_enabled,
                warmup_started_at = CASE
                    -- Use EB created_at as warmup start (accurate even for pre-warmed workspaces)
                    -- Falls back to NOW() only if EB created_at wasn't available
                    WHEN EXCLUDED.warmup_enabled = TRUE AND sender_accounts.warmup_started_at IS NULL
                    THEN COALESCE(EXCLUDED.warmup_started_at, NOW())
                    ELSE sender_accounts.warmup_started_at
                END,
                warmup_stopped_at = CASE
                    -- Set warmup_stopped_at when warmup is disabled
                    WHEN EXCLUDED.warmup_enabled = FALSE AND sender_accounts.warmup_enabled = TRUE
                    THEN NOW()
                    ELSE sender_accounts.warmup_stopped_at
                END,
                emails_sent_all_time = EXCLUDED.emails_sent_all_time,
                replies_all_time = EXCLUDED.replies_all_time,
                bounces_all_time = EXCLUDED.bounces_all_time,
                daily_limit = EXCLUDED.daily_limit,
                is_active = EXCLUDED.is_active,
                -- Update inventory lifecycle status based on warmup_started_at
                -- Incubation = 21 days from EB created_at (when inbox was uploaded to EmailBison)
                --
                -- IMPORTANT: never revert 'active' → 'incubating'. Graduations
                -- are sticky: once an inbox graduates (via lifecycle_tag_sync OR
                -- a clerical bypass UPDATE), it stays graduated until killed.
                -- Without this guard, the calendar-day rule below would flip
                -- recently-graduated inboxes (warmup_started_at < 21d) back to
                -- 'incubating' on every hourly sync. Same bug class as the
                -- lifecycle_tag_sync._tag_new_warmup_inboxes fix (commit 7e79c0e).
                inventory_lifecycle_status = CASE
                    WHEN sender_accounts.killed_at IS NOT NULL THEN 'dead'
                    WHEN EXCLUDED.inbox_state = 'dead' THEN 'dead'
                    WHEN sender_accounts.inventory_lifecycle_status IN ('active', 'dead')
                         THEN sender_accounts.inventory_lifecycle_status
                    WHEN sender_accounts.warmup_started_at IS NULL THEN 'incubating'
                    WHEN sender_accounts.warmup_started_at > NOW() - INTERVAL '21 days' THEN 'incubating'
                    ELSE 'active'
                END,
                -- Update inventory pool status
                -- Preserve deployed/reserve/warning set by set_tag_sync; only override for death or bounces
                inventory_pool_status = CASE
                    WHEN sender_accounts.killed_at IS NOT NULL THEN NULL
                    WHEN EXCLUDED.inbox_state = 'dead' THEN NULL
                    -- Burned/cancelled domain inboxes never carry a pool tag.
                    -- Without this gate, the bounce-threshold branch below would
                    -- keep flipping pool back to 'warning' on every sync, fighting
                    -- the burned-domain handler in set_tag_sync that NULLs them.
                    WHEN (SELECT pool_status FROM domains WHERE id = sender_accounts.domain_id)
                         IN ('burned', 'cancelled') THEN NULL
                    WHEN COALESCE(sender_accounts.hard_bounces_24h, 0) >= 1
                         OR COALESCE(sender_accounts.hard_bounces_7d, 0) >= 3 THEN 'warning'
                    -- Auto-clear warning when bounces subside: restore pool from domain
                    WHEN sender_accounts.inventory_pool_status = 'warning'
                         AND COALESCE(sender_accounts.hard_bounces_24h, 0) < 1
                         AND COALESCE(sender_accounts.hard_bounces_7d, 0) < 3
                    THEN COALESCE(
                        (SELECT CASE d.pool_status
                            WHEN 'live' THEN 'deployed'
                            WHEN 'reserve' THEN 'reserve'
                            ELSE NULL
                         END FROM domains d WHERE d.id = sender_accounts.domain_id),
                        sender_accounts.inventory_pool_status
                    )
                    WHEN sender_accounts.inventory_pool_status IN ('deployed', 'reserve', 'warning')
                         THEN sender_accounts.inventory_pool_status
                    WHEN sender_accounts.warmup_started_at IS NOT NULL
                         AND sender_accounts.warmup_started_at <= NOW() - INTERVAL '21 days'
                         AND COALESCE(EXCLUDED.warmup_enabled, TRUE) = TRUE THEN 'reserve'
                    ELSE NULL
                END,
                last_seen_at = NOW(),
                last_synced_at = NOW(),
                updated_at = NOW(),
                -- Track disconnection timestamp
                disconnected_at = CASE
                    -- Set disconnected_at when status changes TO 'Not connected'
                    WHEN EXCLUDED.status = 'Not connected'
                         AND sender_accounts.status != 'Not connected'
                         AND sender_accounts.disconnected_at IS NULL
                    THEN NOW()
                    -- Keep existing disconnected_at if still disconnected
                    WHEN EXCLUDED.status = 'Not connected'
                    THEN sender_accounts.disconnected_at
                    -- Clear disconnected_at when reconnected
                    ELSE NULL
                END,
                -- Warmup monitoring fields (NOT used for kill triggers)
                warmup_score = EXCLUDED.warmup_score,
                warmup_spam_count = EXCLUDED.warmup_spam_count,
                warmup_bounces_received = EXCLUDED.warmup_bounces_received,
                warmup_bounces_caused = EXCLUDED.warmup_bounces_caused
            RETURNING (xmax = 0) as created, emails_sent_all_time as prev_sends
        """,
            workspace_id,                              # $1
            email,                                     # $2
            eb_id,                                     # $3
            account.get('name'),                       # $4
            status,                                    # $5
            inbox_state,                               # $6
            esp,                                       # $7
            health_score,                              # $8
            bounce_rate,                               # $9
            0,  # $10 complaints_lifetime - NOT seeded from API. Only incremented by sync_events.py on actual FBL/spam reports
            warmup_enabled,                            # $11
            emails_sent_all_time,                      # $12
            replies_all_time,                          # $13
            bounces_all_time,                          # $14
            daily_limit,                               # $15
            inbox_state == 'live',                     # $16 is_active
            initial_lifecycle,                         # $17 inventory_lifecycle_status
            initial_pool,                              # $18 inventory_pool_status
            datetime.now() if status == 'Not connected' else None,  # $19 disconnected_at
            warmup_score,                              # $20 warmup_score (monitoring only)
            warmup_spam_count,                         # $21 warmup_spam_count (NOT complaints)
            warmup_bounces_received,                   # $22 warmup_bounces_received
            warmup_bounces_caused,                     # $23 warmup_bounces_caused
            eb_created_at                              # $24 eb_created_at (EB's real upload date)
        )

        if not result:
            return False

        created = result['created']

        # Track send delta to populate total_sends_7d AND total_sends_24h.
        # Both feed kill-trigger floors:
        #   total_sends_7d  → rate-based triggers (hard_bounce_rate_7d, bounce_rate_all_7d)
        #   total_sends_24h → count-based trigger floor (hard_bounces_24h floor, migration 095)
        #
        # KEY DIFFERENCE FROM BOUNCES:
        # - Bounces: We DON'T track delta here (warmup bounces shouldn't trigger kills)
        # - Sends: We DO track delta (ALL sends matter for rate calculations)
        #
        # The 7d counter decays 14% daily in health_checks.decay_weekly_counters.
        # The 24h counter resets to 0 at midnight in reset_daily_counters; the
        # delta accumulated between midnight and the next sync is what
        # health_checks.evaluate_inbox_health reads as "did this inbox send today?"
        if not created and result['prev_sends'] is not None:
            prev_sends = result['prev_sends'] or 0
            send_delta = max(0, emails_sent_all_time - prev_sends)

            if send_delta > 0:
                await self.db.execute("""
                    UPDATE sender_accounts
                    SET
                        total_sends_7d = COALESCE(total_sends_7d, 0) + $2,
                        total_sends_24h = COALESCE(total_sends_24h, 0) + $2,
                        updated_at = NOW()
                    WHERE email_address = $1
                """, email, send_delta)

        return created

    async def mark_stale_accounts(self, workspace_id: UUID, active_eb_ids: set):
        """
        Mark accounts that are no longer in EmailBison as DEAD.

        Per the operator decision rule (2026-04-28): if an inbox is no longer
        returned by EmailBison's sender-emails endpoint, it has been removed
        from EB — meaning the workspace stopped paying for it via Hypertide
        OR the inbox was manually deleted. Either way, treat it as terminally
        dead, not just "inactive."

        Previous behavior set is_active=FALSE only, leaving inbox_state='live'.
        That left thousands of stale rows that looked alive but were actually
        gone — surfaced during the 2026-04-28 audit as 793+ cancelled-domain
        inboxes that should have been killed weeks ago.

        Setting inbox_state='dead' + kill_trigger='disconnected_timeout' aligns
        DB to operational reality and lets the daily audit + downstream
        analytics treat them correctly.
        """
        if not active_eb_ids:
            return

        stale = await self.db.fetch("""
            UPDATE sender_accounts
            SET
                is_active = FALSE,
                inbox_state = 'dead',
                inventory_lifecycle_status = 'dead',
                inventory_pool_status = NULL,
                kill_trigger = COALESCE(kill_trigger, 'disconnected_timeout'::kill_trigger_type),
                killed_at = COALESCE(killed_at, NOW()),
                updated_at = NOW()
            WHERE workspace_id = $1
            AND emailbison_account_id IS NOT NULL
            AND emailbison_account_id != ALL($2::text[])
            AND is_active = TRUE
            RETURNING email_address
        """, workspace_id, list(active_eb_ids))

        if stale:
            print(f"    Marked {len(stale)} stale accounts as dead (removed from EmailBison)")

    async def sync_all_domains(self):
        """
        Sync domains by creating missing ones from sender_accounts.
        Domains are derived from email addresses, not fetched from EmailBison.

        Note: Domains now have a global unique constraint on domain_name (not workspace-scoped).
        Each domain can only exist once across all workspaces.
        """
        print("[AccountSync] Syncing domains...")

        # Create missing domains (global unique on domain_name)
        # For new domains, use the workspace_id from the first sender_account found
        # domain_source='legacy' marks these as pre-existing/discovered (not purchased via system)
        created = await self.db.execute("""
            INSERT INTO domains (workspace_id, domain_name, approval_status, domain_source, created_at, updated_at)
            SELECT DISTINCT ON (SPLIT_PART(sa.email_address, '@', 2))
                sa.workspace_id,
                SPLIT_PART(sa.email_address, '@', 2),
                'legacy',
                'legacy',
                NOW(),
                NOW()
            FROM sender_accounts sa
            WHERE SPLIT_PART(sa.email_address, '@', 2) != ''
            AND NOT EXISTS (
                SELECT 1 FROM domains d
                WHERE d.domain_name = SPLIT_PART(sa.email_address, '@', 2)
            )
            ORDER BY SPLIT_PART(sa.email_address, '@', 2), sa.first_seen_at ASC
        """)
        print(f"  Created domains: {created}")

        # Link sender_accounts to domains (domain_name is globally unique now)
        linked = await self.db.execute("""
            UPDATE sender_accounts sa
            SET domain_id = d.id, updated_at = NOW()
            FROM domains d
            WHERE SPLIT_PART(sa.email_address, '@', 2) = d.domain_name
            AND sa.domain_id IS NULL
        """)
        print(f"  Linked accounts to domains: {linked}")

        # Set expected_inbox_count for domains that don't have it yet
        # Based on detected provider from sender_accounts ESP
        # Entra (microsoft) = 50 inboxes, Google (gmail) = 3 inboxes
        await self.db.execute("""
            UPDATE domains d
            SET
                expected_inbox_count = CASE
                    WHEN detected.provider = 'entra' THEN 50
                    WHEN detected.provider = 'google' THEN 3
                    ELSE NULL
                END,
                updated_at = NOW()
            FROM (
                SELECT
                    sa.domain_id,
                    CASE
                        WHEN COUNT(*) FILTER (WHERE sa.esp = 'microsoft') > 0 THEN 'entra'
                        WHEN COUNT(*) FILTER (WHERE sa.esp = 'gmail') > 0 THEN 'google'
                        ELSE NULL
                    END as provider
                FROM sender_accounts sa
                WHERE sa.domain_id IS NOT NULL
                GROUP BY sa.domain_id
            ) detected
            WHERE d.id = detected.domain_id
            AND d.expected_inbox_count IS NULL
            AND detected.provider IS NOT NULL
        """)

        # Update domain health scores (average of inbox health scores)
        await self.db.execute("""
            UPDATE domains d
            SET
                latest_health_score = sub.avg_score,
                updated_at = NOW()
            FROM (
                SELECT
                    domain_id,
                    AVG(health_score)::INTEGER as avg_score
                FROM sender_accounts
                WHERE domain_id IS NOT NULL
                AND health_score IS NOT NULL
                GROUP BY domain_id
            ) sub
            WHERE d.id = sub.domain_id
        """)

        # Update max_inboxes_seen and fulfillment_status for capacity tracking
        # max_inboxes_seen = highest inbox count ever observed (for fulfillment verification)
        # fulfillment_status = under_delivered if < 90% of expected
        await self.db.execute("""
            UPDATE domains d
            SET
                max_inboxes_seen = GREATEST(
                    COALESCE(d.max_inboxes_seen, 0),
                    COALESCE(sub.current_count, 0)
                ),
                fulfillment_status = CASE
                    WHEN d.expected_inbox_count IS NULL THEN 'pending'
                    WHEN GREATEST(COALESCE(d.max_inboxes_seen, 0), COALESCE(sub.current_count, 0))
                        < d.expected_inbox_count * 0.9 THEN 'under_delivered'
                    WHEN GREATEST(COALESCE(d.max_inboxes_seen, 0), COALESCE(sub.current_count, 0))
                        > d.expected_inbox_count THEN 'over_delivered'
                    ELSE 'fulfilled'
                END,
                updated_at = NOW()
            FROM (
                SELECT
                    domain_id,
                    COUNT(*) AS current_count
                FROM sender_accounts
                WHERE domain_id IS NOT NULL
                AND is_active = TRUE
                GROUP BY domain_id
            ) sub
            WHERE d.id = sub.domain_id
        """)
