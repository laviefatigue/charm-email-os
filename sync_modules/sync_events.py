"""
Event & Response Sync Module

Synchronizes reply and bounce events from EmailBison campaigns.
Stores full message content in response_messages table.
"""
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
from uuid import UUID
import asyncpg

from .emailbison_client import EmailBisonClient, EmailBisonAPIError
from .audit_logger import AuditLogger, AuditContext, SyncResult
from .slack_alerter import SlackAlerter


class EventSyncModule:
    """Synchronizes events and response messages from EmailBison."""

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

    async def sync_all_active_campaigns(self) -> SyncResult:
        """Sync events for all active campaigns."""
        audit = await self.audit_logger.start_audit(
            sync_type='events',
            metadata={'scope': 'all_active_campaigns'}
        )

        try:
            # Get all active campaigns
            campaigns = await self.db.fetch("""
                SELECT
                    ec.id as local_id,
                    ec.emailbison_campaign_id,
                    ec.campaign_name,
                    ec.workspace_id,
                    w.emailbison_workspace_id,
                    w.workspace_name
                FROM emailbison_campaigns ec
                JOIN workspaces w ON ec.workspace_id = w.id
                WHERE ec.status IN ('active', 'running', 'sending', 'paused')
                AND w.emailbison_workspace_id IS NOT NULL
                AND w.is_active = TRUE
            """)

            print(f"[EventSync] Syncing events for {len(campaigns)} campaigns")

            for campaign in campaigns:
                audit.increment_processed()

                try:
                    # CRITICAL: Switch workspace before each campaign
                    await self.client.switch_workspace(int(campaign['emailbison_workspace_id']))

                    # Sync inbox replies
                    inbox_count = await self.sync_campaign_replies(
                        local_campaign_id=campaign['local_id'],
                        eb_campaign_id=int(campaign['emailbison_campaign_id']),
                        workspace_id=campaign['workspace_id'],
                        folder='inbox'
                    )

                    # Sync bounced messages
                    bounce_count = await self.sync_campaign_replies(
                        local_campaign_id=campaign['local_id'],
                        eb_campaign_id=int(campaign['emailbison_campaign_id']),
                        workspace_id=campaign['workspace_id'],
                        folder='bounced'
                    )

                    if inbox_count > 0 or bounce_count > 0:
                        audit.increment_updated()
                        print(f"    [{campaign['campaign_name']}] {inbox_count} replies, {bounce_count} bounces")

                except EmailBisonAPIError as e:
                    audit.add_error(
                        record_id=campaign['campaign_name'],
                        error=str(e),
                        details={'campaign_id': campaign['emailbison_campaign_id']}
                    )
                except Exception as e:
                    audit.add_error(
                        record_id=campaign['campaign_name'],
                        error=str(e)
                    )

            return await audit.complete()

        except Exception as e:
            return await audit.fail(e)

    async def sync_campaign_replies(
        self,
        local_campaign_id: UUID,
        eb_campaign_id: int,
        workspace_id: UUID,
        folder: str
    ) -> int:
        """
        Sync replies for a specific campaign folder.

        Args:
            local_campaign_id: Our campaign UUID
            eb_campaign_id: EmailBison campaign ID
            workspace_id: Workspace UUID
            folder: 'inbox' or 'bounced'

        Returns:
            Number of new events synced
        """
        new_count = 0

        try:
            replies = await self.client.get_all_campaign_replies(
                campaign_id=eb_campaign_id,
                folder=folder
            )

            for reply in replies:
                try:
                    created = await self.process_reply(
                        reply=reply,
                        local_campaign_id=local_campaign_id,
                        workspace_id=workspace_id,
                        folder=folder
                    )
                    if created:
                        new_count += 1

                except Exception as e:
                    print(f"      Error processing reply {reply.get('id')}: {e}")

        except Exception as e:
            print(f"    Error fetching {folder} for campaign {eb_campaign_id}: {e}")

        return new_count

    async def process_reply(
        self,
        reply: Dict,
        local_campaign_id: UUID,
        workspace_id: UUID,
        folder: str
    ) -> bool:
        """
        Process a single reply/bounce and store in database.

        Returns:
            True if new record created, False if already existed
        """
        eb_reply_id = reply.get('id')
        if not eb_reply_id:
            return False

        # Check if already processed
        existing = await self.db.fetchval("""
            SELECT id FROM response_messages
            WHERE emailbison_reply_id = $1 AND campaign_id = $2
        """, eb_reply_id, local_campaign_id)

        if existing:
            return False

        # Extract fields (handle field name variations)
        from_email = (
            reply.get('from_email_address') or
            reply.get('lead_email') or
            reply.get('email', '')
        ).lower()

        from_name = reply.get('from_name') or reply.get('lead_name') or reply.get('name', '')
        to_inbox = reply.get('primary_to_email_address', '').lower()
        subject = reply.get('subject', '')
        body = reply.get('body', '')

        # Timestamp parsing
        received_at = None
        received_str = reply.get('received_at')
        if received_str:
            try:
                received_at = datetime.fromisoformat(received_str.replace('Z', '+00:00'))
            except (ValueError, TypeError):
                received_at = datetime.now(timezone.utc)

        # Classification
        is_interested = reply.get('interested', False)
        is_automated = reply.get('automated_reply', False)

        # Bounce classification (only for bounced folder)
        bounce_type = None
        bounce_reason = None
        if folder == 'bounced':
            bounce_reason = reply.get('bounce_reason', '')
            bounce_type = self.classify_bounce(bounce_reason)

        # Determine sentiment for non-bounce messages
        sentiment = None
        if folder == 'inbox':
            sentiment = self.classify_sentiment(body, is_interested, is_automated)

        # Lookup sender account
        sender_account_id = None
        if to_inbox:
            sender_account_id = await self.db.fetchval("""
                SELECT id FROM sender_accounts
                WHERE LOWER(email_address) = $1 AND workspace_id = $2
            """, to_inbox, workspace_id)

        # Determine event type for campaign_events
        event_type = self.get_event_type(folder, is_interested, is_automated)

        # Insert response message
        response_id = await self.db.fetchval("""
            INSERT INTO response_messages (
                campaign_id,
                workspace_id,
                emailbison_reply_id,
                folder,
                from_email,
                from_name,
                to_inbox_email,
                sender_account_id,
                subject,
                body_preview,
                body_full,
                received_at,
                is_interested,
                is_automated,
                bounce_type,
                bounce_reason,
                sentiment
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17)
            ON CONFLICT (emailbison_reply_id, campaign_id) DO NOTHING
            RETURNING id
        """,
            local_campaign_id,
            workspace_id,
            eb_reply_id,
            folder,
            from_email,
            from_name,
            to_inbox,
            sender_account_id,
            subject,
            body[:500] if body else None,  # Preview
            body,  # Full body
            received_at,
            is_interested,
            is_automated,
            bounce_type,
            bounce_reason,
            sentiment
        )

        if not response_id:
            return False  # Already existed (conflict)

        # Also create campaign_event record
        await self.create_campaign_event(
            campaign_id=local_campaign_id,
            response_id=response_id,
            event_type=event_type,
            lead_email=from_email,
            lead_name=from_name,
            sender_account_id=sender_account_id,
            reply=reply
        )

        # If bounce on sender inbox, update sender_accounts metrics
        if folder == 'bounced' and sender_account_id and bounce_type and bounce_type.startswith('hard'):
            await self.increment_inbox_bounces(sender_account_id)

        return True

    def classify_bounce(self, reason: str) -> str:
        """
        Classify bounce type from bounce reason.

        Returns:
            'hard_unknown' - Bad email address
            'hard_blocked' - Reputation/spam block
            'soft_full' - Mailbox full
            'soft_temp' - Temporary failure
        """
        if not reason:
            return 'hard_unknown'

        reason_lower = reason.lower()

        # Hard bounces - permanent failures
        if any(kw in reason_lower for kw in ['user', 'unknown', 'not exist', 'invalid', 'no such']):
            return 'hard_unknown'

        if any(kw in reason_lower for kw in ['block', 'spam', 'reject', 'blacklist', 'denied', 'policy']):
            return 'hard_blocked'

        # Soft bounces - temporary failures
        if any(kw in reason_lower for kw in ['full', 'quota', 'storage', 'over quota']):
            return 'soft_full'

        if any(kw in reason_lower for kw in ['timeout', 'temporary', 'try again', 'unavailable', 'busy']):
            return 'soft_temp'

        # Default to hard unknown for safety
        return 'hard_unknown'

    def classify_sentiment(self, body: str, is_interested: bool, is_automated: bool) -> str:
        """Classify reply sentiment."""
        if is_automated:
            return 'out_of_office'
        if is_interested:
            return 'positive'

        if not body:
            return 'neutral'

        body_lower = body.lower()

        # Simple keyword-based sentiment
        negative_keywords = [
            'unsubscribe', 'remove', 'stop', 'not interested', 'no thank',
            'don\'t contact', 'spam', 'take me off', 'opt out'
        ]
        if any(kw in body_lower for kw in negative_keywords):
            return 'negative'

        positive_keywords = [
            'interested', 'tell me more', 'schedule', 'call', 'demo',
            'meeting', 'yes', 'sounds good', 'let\'s talk'
        ]
        if any(kw in body_lower for kw in positive_keywords):
            return 'positive'

        return 'neutral'

    def get_event_type(self, folder: str, is_interested: bool, is_automated: bool) -> str:
        """Determine event type for campaign_events table."""
        if folder == 'bounced':
            return 'bounce'
        if is_interested:
            return 'interested_reply'
        if is_automated:
            return 'automated_reply'
        return 'reply'

    async def create_campaign_event(
        self,
        campaign_id: UUID,
        response_id: UUID,
        event_type: str,
        lead_email: str,
        lead_name: str,
        sender_account_id: UUID,
        reply: Dict
    ):
        """Create campaign_events record linked to response_message."""
        await self.db.execute("""
            INSERT INTO campaign_events (
                campaign_id,
                event_type,
                lead_email,
                lead_name,
                sender_account_id,
                event_data
            ) VALUES ($1, $2, $3, $4, $5, $6)
        """,
            campaign_id,
            event_type,
            lead_email,
            lead_name,
            sender_account_id,
            {
                'response_message_id': str(response_id),
                'emailbison_reply_id': reply.get('id'),
                'subject': reply.get('subject'),
                'folder': reply.get('folder'),
                'interested': reply.get('interested', False),
                'automated_reply': reply.get('automated_reply', False),
                'received_at': reply.get('received_at')
            }
        )

    async def increment_inbox_bounces(self, sender_account_id: UUID):
        """Increment bounce counters for sender inbox (for health checks)."""
        await self.db.execute("""
            UPDATE sender_accounts
            SET
                hard_bounces_24h = COALESCE(hard_bounces_24h, 0) + 1,
                hard_bounces_7d = COALESCE(hard_bounces_7d, 0) + 1,
                updated_at = NOW()
            WHERE id = $1
        """, sender_account_id)
