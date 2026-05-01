"""
Event & Response Sync Module

Synchronizes reply and bounce events from EmailBison campaigns.
Stores full message content in response_messages table.

Architecture (workspace-concurrent model):
    This module is designed for per-workspace parallel execution.
    It is called by WorkspaceSyncQueue._dispatch() with a workspace-scoped
    EmailBisonClient already initialised with the per-workspace API key.

    Contract:
        - Caller passes a client already scoped to the target workspace.
        - NO switch_workspace() calls in sync_workspace().
        - sync_workspace(workspace_id, workspace_name) queries campaigns in that
          workspace and processes all three folders (inbox, bounced, spam) per
          campaign without any client context switching.
        - No inter_batch_delay() between campaigns — each workspace has its own
          client instance, so there is no shared rate-limit state.

    Removed from sync_workspace() (old sequential model):
        - switch_workspace() call per campaign  — eliminated by workspace-scoped API keys
        - inter_batch_delay() between campaigns — no shared client = no shared rate limit

    Retained (legacy / non-parallel path):
        - sync_all_active_campaigns() — DEPRECATED. Retained for manual/backfill use only.
          Uses switch_workspace() internally and must NOT be called from the concurrent
          worker.  Will be removed in a future cleanup pass.
"""
import json
import re
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
from uuid import UUID
import asyncpg

from .emailbison_client import EmailBisonClient, EmailBisonAPIError
from .audit_logger import AuditLogger, AuditContext, SyncResult
from .slack_alerter import SlackAlerter


# Plan D Pass 3 (2026-05-01) — Microsoft sender-ban SMTP codes.
# These codes are direct accusations from Microsoft that OUR sending
# account / IP / tenant has been banned for outbound abuse. They are NOT
# recipient-side rejections. Per Microsoft Learn 2026 NDR catalog:
#   5.7.501  Access denied, spam abuse detected (sending account banned)
#   5.7.502  Banned sender
#   5.7.503  Banned sender
#   5.7.508  IPv6 send-rate exceeded
#   5.7.511  IP on Microsoft blocklist (delist@microsoft.com)
#   5.7.606..5.7.649  Banned sending IP range
#   5.7.703  Recipient Tenant Allow/Block List blocked us
#   5.7.705  Tenant exceeded outbound abuse threshold
#   5.7.708  Tenant traffic not accepted from this IP
#   5.7.750  Unregistered domain block
#   5.7.800  EHLO/P1/P2 sender domain banned
SENDER_BAN_CODES_EXACT = {
    '5.7.501', '5.7.502', '5.7.503', '5.7.508', '5.7.511',
    '5.7.703', '5.7.705', '5.7.708', '5.7.750', '5.7.800',
    # NOTE: 5.7.509 (DMARC reject) was considered for inclusion but
    # excluded after a 2026-05-01 production sanity check showed 11
    # hits in 30 days — that's a DMARC ALIGNMENT issue (fixable via
    # SPF/DKIM/DMARC config), not a Microsoft "we banned you" verdict.
    # Treating it as a ban would generate alert noise. Handled by the
    # existing hard_blocked_24h count rule instead.
}
# 5.7.606..5.7.649 — banned sending IP range (regex check)
_SENDER_BAN_IP_RANGE = re.compile(r'\b5\.7\.(6[0-4]\d)\b')


def is_sender_ban_code(reason: str) -> Optional[str]:
    """Return the specific sender-ban code if reason matches, else None.

    Used by Plan D Pass 3 (2026-05-01) — sender-ban detection in alert-first
    mode. When this returns a non-None code, process_reply fires a critical
    Slack alert telling the operator that Microsoft has banned our sending.

    Pass 3 currently does NOT auto-kill on detection. After 7 days of
    alert-only observation to confirm real production hits, the kill
    behavior will be enabled (separate ship).

    Pure function — no I/O, no DB. See tests/test_bounce_parsing.py for
    coverage.
    """
    if not reason:
        return None
    for code in SENDER_BAN_CODES_EXACT:
        if code in reason:
            return code
    m = _SENDER_BAN_IP_RANGE.search(reason)
    if m:
        digits = int(m.group(1))
        if 606 <= digits <= 649:
            return f'5.7.{digits}'
    return None


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

    async def sync_workspace(
        self,
        workspace_id: UUID,
        workspace_name: str,
    ) -> SyncResult:
        """
        Sync events for all active campaigns in a single workspace.

        The EmailBisonClient (self.client) must already be scoped to this
        workspace via its API key.  No switch_workspace() calls are made.
        Called by WorkspaceSyncQueue._dispatch() with a per-workspace client.

        Processes three folders per campaign: inbox (replies), bounced, spam.
        No inter_batch_delay() between campaigns — each workspace has its own
        isolated client instance with independent rate-limit state.
        """
        audit = await self.audit_logger.start_audit(
            sync_type='events',
            workspace_id=workspace_id,
            metadata={'workspace_name': workspace_name}
        )

        try:
            # Get all active campaigns for THIS workspace
            campaigns = await self.db.fetch("""
                SELECT
                    ec.id as local_id,
                    ec.emailbison_campaign_id,
                    ec.campaign_name,
                    ec.workspace_id
                FROM emailbison_campaigns ec
                JOIN workspaces w ON ec.workspace_id = w.id
                WHERE ec.workspace_id = $1
                AND ec.campaign_status IN ('active', 'running', 'sending', 'paused')
                AND w.is_active = TRUE
            """, workspace_id)

            print(f"[EventSync] [{workspace_name}] Syncing events for {len(campaigns)} campaigns")

            for campaign in campaigns:
                audit.increment_processed()

                try:
                    # Sync all three folders — no workspace switch needed, client is pre-scoped.
                    # `audit` is passed down so per-reply errors increment records_failed
                    # and surface in error_log instead of being printed and forgotten.
                    # Plan D Pass 4 silent-error fix (2026-05-01).
                    inbox_count = await self.sync_campaign_replies(
                        local_campaign_id=campaign['local_id'],
                        eb_campaign_id=int(campaign['emailbison_campaign_id']),
                        workspace_id=campaign['workspace_id'],
                        folder='inbox',
                        audit=audit,
                    )
                    bounce_count = await self.sync_campaign_replies(
                        local_campaign_id=campaign['local_id'],
                        eb_campaign_id=int(campaign['emailbison_campaign_id']),
                        workspace_id=campaign['workspace_id'],
                        folder='bounced',
                        audit=audit,
                    )
                    spam_count = await self.sync_campaign_replies(
                        local_campaign_id=campaign['local_id'],
                        eb_campaign_id=int(campaign['emailbison_campaign_id']),
                        workspace_id=campaign['workspace_id'],
                        folder='spam',
                        audit=audit,
                    )

                    if inbox_count > 0 or bounce_count > 0 or spam_count > 0:
                        audit.increment_updated()
                        print(f"    [{campaign['campaign_name']}] {inbox_count} replies, {bounce_count} bounces, {spam_count} spam")

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

            await self.audit_logger.update_sync_status(
                sync_type='events',
                workspace_id=workspace_id,
                record_count=len(campaigns)
            )

            return await audit.complete()

        except Exception as e:
            return await audit.fail(e)

    async def sync_all_active_campaigns(self) -> SyncResult:
        """
        DEPRECATED — retained for manual/backfill use only.

        This method uses switch_workspace() internally and processes all
        workspaces sequentially.  It must NOT be called from the concurrent
        WorkspaceSyncQueue worker.  Use sync_workspace() instead.

        Will be removed in a future cleanup pass once confirmed unused.
        """
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
                WHERE ec.campaign_status IN ('active', 'running', 'sending', 'paused')
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

                    # Sync spam folder - leads who reported us as spam
                    # CRITICAL: These are spam complaints that should trigger kills
                    spam_count = await self.sync_campaign_replies(
                        local_campaign_id=campaign['local_id'],
                        eb_campaign_id=int(campaign['emailbison_campaign_id']),
                        workspace_id=campaign['workspace_id'],
                        folder='spam'
                    )

                    if inbox_count > 0 or bounce_count > 0 or spam_count > 0:
                        audit.increment_updated()
                        print(f"    [{campaign['campaign_name']}] {inbox_count} replies, {bounce_count} bounces, {spam_count} spam")

                    # Add delay between campaigns to avoid rate limiting
                    await self.client.inter_batch_delay(1.0)

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
        folder: str,
        audit: Optional['AuditContext'] = None,
    ) -> int:
        """
        Sync replies for a specific campaign folder.

        Args:
            local_campaign_id: Our campaign UUID
            eb_campaign_id: EmailBison campaign ID
            workspace_id: Workspace UUID
            folder: 'inbox' or 'bounced' or 'spam'
            audit: Optional AuditContext from the caller's sync_workspace audit.
                   When provided, per-reply and per-folder errors are recorded
                   to records_failed + error_log via add_error() instead of
                   being printed and forgotten. Pre-2026-05-01 callers may not
                   pass audit; in that case errors fall back to print() with
                   a `[silent-error-fallback]` marker so they're greppable.
                   Plan D Pass 4 silent-error fix.

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
                    # Per-reply error: record to audit so records_failed reflects
                    # reality and error_log preserves the per-row detail. Without
                    # this, a malformed bounce body that breaks INSERT would be
                    # silently lost and the workspace audit would still report OK.
                    if audit is not None:
                        audit.add_error(
                            record_id=str(reply.get('id') or 'unknown'),
                            error=f"process_reply failed: {e!r}",
                            details={
                                'campaign_id': eb_campaign_id,
                                'folder': folder,
                                'eb_reply_id': reply.get('id'),
                            },
                        )
                    else:
                        print(f"      [silent-error-fallback] reply {reply.get('id')} folder={folder} campaign={eb_campaign_id}: {e!r}")

        except Exception as e:
            # Per-folder fetch error: same treatment. If get_all_campaign_replies
            # raises (e.g. EB API timeout, malformed response), the entire
            # campaign+folder pair is lost — record the loss explicitly.
            if audit is not None:
                audit.add_error(
                    record_id=f'campaign={eb_campaign_id} folder={folder}',
                    error=f"fetch_replies failed: {e!r}",
                    details={'campaign_id': eb_campaign_id, 'folder': folder},
                )
            else:
                print(f"    [silent-error-fallback] fetch {folder} for campaign {eb_campaign_id}: {e!r}")

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

        # Body extraction - EmailBison uses text_body/html_body, not 'body'
        body = reply.get('text_body') or reply.get('html_body') or reply.get('body', '')

        # Timestamp parsing - EmailBison uses date_received, not received_at
        # DB column is 'timestamp without time zone', so we need naive datetimes
        received_at = None
        received_str = reply.get('date_received') or reply.get('received_at')
        if received_str:
            try:
                # Handle Z suffix for ISO parsing
                parsed = datetime.fromisoformat(received_str.replace('Z', '+00:00'))
                # Convert to naive UTC (strip timezone) for DB compatibility
                if parsed.tzinfo is not None:
                    # Convert to UTC then strip timezone
                    parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
                received_at = parsed
            except (ValueError, TypeError):
                received_at = datetime.utcnow()
        else:
            received_at = datetime.utcnow()

        # Classification
        is_interested = reply.get('interested', False)
        is_automated = reply.get('automated_reply', False)

        # Bounce classification (only for bounced folder)
        bounce_type = None
        bounce_reason = None
        if folder == 'bounced':
            # EmailBison doesn't provide bounce_reason - extract from body/subject
            bounce_reason = self.extract_bounce_reason(subject, body)
            bounce_type = self.classify_bounce(bounce_reason)

        # Determine sentiment for non-bounce messages
        sentiment = None
        if folder == 'inbox':
            sentiment = self.classify_sentiment(body, is_interested, is_automated)

        # Lookup sender account
        # Primary: use sender_email_id from EmailBison (maps to our emailbison_account_id)
        # Fallback: match by email address if sender_email_id not available
        eb_sender_id = reply.get('sender_email_id')
        sender_account_id = None

        if eb_sender_id:
            sender_account_id = await self.db.fetchval("""
                SELECT id FROM sender_accounts
                WHERE emailbison_account_id = $1 AND workspace_id = $2
            """, str(eb_sender_id), workspace_id)

        # Fallback to email address lookup if sender_email_id not found
        if not sender_account_id and to_inbox:
            sender_account_id = await self.db.fetchval("""
                SELECT id FROM sender_accounts
                WHERE LOWER(email_address) = $1 AND workspace_id = $2
            """, to_inbox, workspace_id)

        # Determine event type for campaign_events
        event_type = self.get_event_type(folder, is_interested, is_automated)

        # Storage strategy (Plan D Pass 4 — 2026-05-01):
        #   BOUNCES: Keep BOTH preview AND full body for forensic analysis.
        #   Pre-Pass-4, body_full was set to None for bounces. That made
        #   post-hoc verification of spam_complaint kills impossible — we
        #   could not re-run is_spam_complaint() against the full content
        #   the heuristic actually saw at processing time, only the first
        #   500 chars. The forensic gap motivated this change.
        #
        #   Storage cost: ~30KB avg per bounce × 8336 bounces/30d × 90-day
        #   retention (cleanup_bounce_messages in retention.py deletes the
        #   whole row at 90d — body_full goes with it) ≈ 60MB peak.
        #   Negligible vs. the ability to re-analyze any future kill.
        #
        #   REAL REPLIES: Keep full body for copy analysis and lead quality.
        #   Indefinite retention.
        store_body_preview = body[:500] if body else None
        store_body_full = body

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
            store_body_preview,
            store_body_full,
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
        if folder == 'bounced' and sender_account_id and bounce_type and bounce_type != 'unknown':
            await self.increment_inbox_bounces(sender_account_id, bounce_type)

        # Plan D Pass 3 — Microsoft sender-ban SMTP code detection (alert-first).
        # When a sender-ban code (5.7.501-503, .508, .511, .606-649, .703,
        # .705, .708, .750, .800) appears in the bounce reason, fire a
        # critical Slack alert. NO kill behavior change yet — operator
        # reviews ~7 days of real hits before we enable auto-kill.
        # The bounce still counts toward hard_blocked_24h via the increment
        # above; the alert is purely additional observability.
        if folder == 'bounced' and sender_account_id:
            ban_code = is_sender_ban_code(bounce_reason)
            if ban_code and self.alerter:
                try:
                    # Pull workspace + email for the alert message.
                    ws_row = await self.db.fetchrow(
                        "SELECT w.workspace_name FROM workspaces w "
                        "JOIN sender_accounts s ON s.workspace_id=w.id "
                        "WHERE s.id=$1",
                        sender_account_id,
                    )
                    ws_name = ws_row['workspace_name'] if ws_row else 'unknown'
                    await self.alerter.alert_sender_ban(
                        inbox_email=to_inbox or '(unknown)',
                        workspace=ws_name,
                        smtp_code=ban_code,
                        bounce_reason=bounce_reason or '',
                    )
                    print(f"      [SENDER-BAN] {to_inbox} hit code {ban_code} — alerted operator")
                except Exception as ban_err:
                    # Don't let alert failures break the upstream sync flow.
                    print(f"      [SENDER-BAN ALERT FAILED] {to_inbox} {ban_code}: {ban_err!r}")

        # Detect spam complaints - Per v3 spec: 1 spam complaint = death, no exceptions
        # Check in THREE places:
        # 1. SPAM folder: Direct spam report - lead clicked "Report as Spam" in their email client
        # 2. INBOX responses: Lead explicitly says they marked us as spam
        # 3. BOUNCE messages: FBL (Feedback Loop) patterns indicating spam report
        if sender_account_id:
            is_spam = False

            if folder == 'spam':
                # SPAM FOLDER: This is a DIRECT spam complaint - most definitive signal
                # The lead clicked "Report as Spam" in their email client
                is_spam = True
                print(f"      [SPAM FOLDER] Direct spam complaint detected for {to_inbox}")
            elif folder == 'inbox':
                # Analyze lead response text for spam complaint indicators
                is_spam = self.detect_spam_in_response(body, subject)
            elif folder == 'bounced' and bounce_type == 'hard_blocked':
                # Plan D Pass 2 (2026-05-01) — DISABLED.
                #
                # The bounce-body FBL inference was structurally unsound. Audit
                # showed 0/383 historical spam_complaint kills had folder='spam'
                # direct evidence; 5/5 sampled were the heuristic firing on
                # admin-policy NDRs (e.g. SGMC mail-flow rules), Microsoft
                # 5.7.51 partner-connector restrictions, recipient-server spam
                # filters (5.7.350) — none of which are user-initiated spam
                # complaints. Per Microsoft Learn 2026 NDR catalog and Gmail
                # SMTP error reference, NO SMTP code from MS365 or Google
                # Workspace means "user reported as spam." Real complaints
                # route out-of-band: Microsoft JMRP (ARF emails to a registered
                # FBL address) and Gmail Postmaster Tools (dashboard, requires
                # Feedback-ID: header).
                #
                # The is_spam_complaint() function is left in place (not deleted)
                # for forensic re-analysis once Plan D Pass 4 lands (body_full
                # retention) and for the future apps/fbl-consumer/ extraction
                # (Plan D Pass 5). Pinned by tests/test_bounce_parsing.py.
                #
                # Behavior change: bounces still drive hard_blocked_24h via
                # increment_inbox_bounces (above). Same inboxes still die when
                # they should — just via the correct rule. ~24h delay on death
                # for false-positive single-bounce cases (which is the desired
                # behavior — admin policy blocks shouldn't kill a healthy inbox).
                #
                # See docs/plans/kill-trigger-accuracy.md and
                # docs/concepts/kill-triggers.md § "Spam complaint detection".
                is_spam = False

            if is_spam:
                await self.increment_inbox_complaints(sender_account_id, to_inbox)

        return True

    def extract_bounce_reason(self, subject: str, body: str) -> str:
        """
        Extract bounce reason from message subject and body.

        EmailBison doesn't provide a separate bounce_reason field - the SMTP
        error codes and reason text are embedded in the bounce message body.

        Common SMTP codes we extract:
        - 550 5.1.1 = User unknown / mailbox doesn't exist
        - 550 5.1.0 = Address rejected
        - 550 5.7.1 = Message rejected (policy/spam)
        - 550 5.7.51 = User reported spam (Microsoft)
        - 552 5.2.2 = Mailbox full
        - 421 4.7.0 = Temporary failure
        - 452 4.2.2 = Mailbox full (temporary)

        Returns:
            Extracted bounce reason string containing SMTP codes + keywords
        """
        import re

        combined = f"{subject or ''} {body or ''}"

        # Extract SMTP codes (e.g., "550 5.1.1", "421 4.7.0")
        smtp_pattern = r'\b([45]\d{2})\s*([45]\.\d+\.\d+)?\b'
        smtp_matches = re.findall(smtp_pattern, combined)

        # Look for common error phrases
        error_phrases = []

        # User/mailbox doesn't exist
        if re.search(r"user.*(?:unknown|not found|doesn'?t exist)", combined, re.I):
            error_phrases.append('user unknown')
        if re.search(r"(?:mailbox|address|recipient).*(?:not found|doesn'?t exist|invalid)", combined, re.I):
            error_phrases.append('mailbox not found')
        if re.search(r"wasn'?t found at", combined, re.I):
            error_phrases.append('not found')

        # Blocked/rejected
        if re.search(r'(?:blocked|rejected|refused|denied)', combined, re.I):
            error_phrases.append('blocked')
        if re.search(r'(?:spam|junk|blacklist)', combined, re.I):
            error_phrases.append('spam')
        if re.search(r'(?:policy|compliance)', combined, re.I):
            error_phrases.append('policy')

        # Mailbox full
        if re.search(r'(?:mailbox|quota|storage).*(?:full|exceeded|over)', combined, re.I):
            error_phrases.append('mailbox full')
        if re.search(r'over.*quota', combined, re.I):
            error_phrases.append('over quota')

        # Temporary issues
        if re.search(r'(?:temporary|try.*(?:again|later))', combined, re.I):
            error_phrases.append('temporary')
        if re.search(r'(?:timeout|unavailable|busy)', combined, re.I):
            error_phrases.append('timeout')

        # Build reason string
        parts = []
        if smtp_matches:
            # Include first SMTP code found
            code = smtp_matches[0][0]
            extended = smtp_matches[0][1] if smtp_matches[0][1] else ''
            parts.append(f"{code} {extended}".strip())
        if error_phrases:
            parts.append(' '.join(error_phrases[:2]))

        return ' | '.join(parts) if parts else ''

    def classify_bounce(self, reason: str) -> str:
        """
        Classify bounce type from extracted bounce reason.

        Uses SMTP codes (more reliable) with keyword fallback for ambiguous codes.

        Returns:
            'hard_unknown' - Bad email address (550 5.1.1, user unknown)
            'hard_blocked' - Reputation/spam block (550 5.7.x, blocked)
            'soft_full' - Mailbox full (452 4.2.2)
            'soft_temp' - Temporary failure (421, timeout)
            'unknown' - No bounce reason available (not counted as hard)
        """
        import re

        if not reason:
            return 'unknown'

        reason_lower = reason.lower()

        # Check SMTP codes first (more reliable)
        # 5xx = permanent failure, 4xx = temporary
        if '550' in reason or '551' in reason or '553' in reason or '554' in reason:
            # 550 5.1.1 / 5.1.0 = user unknown (bad address)
            if '5.1.1' in reason or '5.1.0' in reason:
                return 'hard_unknown'
            # 550 5.7.x = policy/spam block (reputation damage)
            if '5.7' in reason:
                return 'hard_blocked'
            # Ambiguous 5xx without 5.1.x or 5.7.x extended code:
            # Use keywords to disambiguate before defaulting
            if any(kw in reason_lower for kw in ['blocked', 'spam', 'blacklist', 'denied', 'rejected']):
                return 'hard_blocked'
            if any(kw in reason_lower for kw in ['not found', 'user unknown', 'mailbox not found', 'no such']):
                return 'hard_unknown'
            # True fallback for unrecognized 5xx
            return 'hard_unknown'

        if '552' in reason or '5.2.2' in reason:
            return 'soft_full'

        if '452' in reason or '4.2.2' in reason:
            return 'soft_full'

        if '421' in reason or '4.7' in reason:
            return 'soft_temp'

        # 4xx safety net - any remaining 4xx code is temporary
        if re.search(r'\b4\d{2}\b', reason):
            return 'soft_temp'

        # Keyword fallback (no SMTP code matched)
        if any(kw in reason_lower for kw in ['user', 'unknown', 'not exist', 'invalid', 'no such', 'not found']):
            return 'hard_unknown'

        if any(kw in reason_lower for kw in ['block', 'spam', 'reject', 'blacklist', 'denied', 'policy']):
            return 'hard_blocked'

        if any(kw in reason_lower for kw in ['full', 'quota', 'storage', 'over quota']):
            return 'soft_full'

        if any(kw in reason_lower for kw in ['timeout', 'temporary', 'try again', 'unavailable', 'busy']):
            return 'soft_temp'

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
        if folder == 'spam':
            return 'spam'
        if is_interested:
            return 'interested_reply'
        if is_automated:
            return 'automated_reply'
        return 'reply'

    def detect_spam_in_response(self, body: str, subject: str = '') -> bool:
        """
        Detect if a lead's inbox response indicates they marked us as spam.

        This analyzes the TEXT of the lead's reply to our email. If they
        explicitly say they reported us as spam, we treat this as a spam complaint.

        Per v3 spec: 1 spam complaint = death, no exceptions.

        Args:
            body: The body text of the lead's reply
            subject: The subject line of the reply

        Returns:
            True if the response indicates the lead marked us as spam
        """
        if not body and not subject:
            return False

        combined = f"{subject or ''} {body or ''}".lower()

        # Phrases that indicate the lead explicitly marked us as spam
        # These are things a lead would SAY in their reply
        # Note: Avoid phrases that could be observations (e.g., "emails go to spam")
        spam_report_phrases = [
            # Explicit spam reporting statements (active voice)
            'marked as spam',
            'marked this as spam',
            'marked you as spam',
            'marked it as spam',
            'reported as spam',
            'reported you as spam',
            'reported this as spam',
            'reported it as spam',
            'flagged as spam',
            'flagged you as spam',
            'flagged this as spam',
            'moved to spam',        # Active: "I moved" vs passive observation
            'put in spam',
            'sent to spam folder',
            'moved to my spam',

            # Junk folder references (Microsoft/Outlook)
            'marked as junk',
            'reported as junk',
            'moved to junk',
            'put in junk',
            'sent to junk',
            'to junk folder',       # Catches various "moved/sent to junk folder"
            'in junk folder',       # Catches "put it in junk folder"
            'in my junk',           # Catches "put it in my junk"

            # Explicit blocking statements with spam context
            'blocked you for spam',
            'blocking you for spam',
            'blocked as spam',

            # Complaints with report context
            'spam complaint',
            'filing a spam complaint',
            'filed a spam complaint',
            'reporting you for spam',
            'report you for spam',
            'reporting this as spam',

            # ISP/Provider complaint references
            'reported to google',
            'reported to microsoft',
            'reported to my provider',
            'reported to my email provider',
            'reported to yahoo',
            'reported to outlook',
            'reported to gmail',
        ]

        for phrase in spam_report_phrases:
            if phrase in combined:
                return True

        return False

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
        event_data = json.dumps({
            'response_message_id': str(response_id),
            'emailbison_reply_id': reply.get('id'),
            'subject': reply.get('subject'),
            'folder': reply.get('folder'),
            'interested': reply.get('interested', False),
            'automated_reply': reply.get('automated_reply', False),
            'received_at': reply.get('received_at')
        })

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
            event_data
        )

    async def increment_inbox_bounces(self, sender_account_id: UUID, bounce_type: str = None):
        """Increment bounce counters for sender inbox (for health checks).

        Args:
            sender_account_id: The sender account UUID
            bounce_type: 'hard_unknown', 'hard_blocked', 'soft_full', 'soft_temp', or 'unknown'

        Threshold strategy:
        - hard_blocked_24h >= 1 = instant kill (spam/policy rejection = reputation damage)
        - hard_unknown_24h >= 3 = kill (bad addresses = list quality issue)
        - hard_bounces_24h >= 2 = combined fallback
        - soft bounces tracked for rate calculations but don't trigger kills directly
        """
        if bounce_type == 'hard_blocked':
            await self.db.execute("""
                UPDATE sender_accounts
                SET
                    hard_bounces_24h = COALESCE(hard_bounces_24h, 0) + 1,
                    hard_bounces_7d = COALESCE(hard_bounces_7d, 0) + 1,
                    hard_blocked_24h = COALESCE(hard_blocked_24h, 0) + 1,
                    updated_at = NOW()
                WHERE id = $1
            """, sender_account_id)
        elif bounce_type == 'hard_unknown':
            await self.db.execute("""
                UPDATE sender_accounts
                SET
                    hard_bounces_24h = COALESCE(hard_bounces_24h, 0) + 1,
                    hard_bounces_7d = COALESCE(hard_bounces_7d, 0) + 1,
                    hard_unknown_24h = COALESCE(hard_unknown_24h, 0) + 1,
                    updated_at = NOW()
                WHERE id = $1
            """, sender_account_id)
        elif bounce_type in ('soft_full', 'soft_temp'):
            await self.db.execute("""
                UPDATE sender_accounts
                SET
                    soft_bounces_7d = COALESCE(soft_bounces_7d, 0) + 1,
                    updated_at = NOW()
                WHERE id = $1
            """, sender_account_id)
        elif bounce_type and bounce_type.startswith('hard'):
            # Fallback for any other hard bounce type
            await self.db.execute("""
                UPDATE sender_accounts
                SET
                    hard_bounces_24h = COALESCE(hard_bounces_24h, 0) + 1,
                    hard_bounces_7d = COALESCE(hard_bounces_7d, 0) + 1,
                    updated_at = NOW()
                WHERE id = $1
            """, sender_account_id)

    async def increment_inbox_complaints(self, sender_account_id: UUID, inbox_email: str = None):
        """
        Increment spam complaint counter for sender inbox.

        Per v3 spec: 1 spam complaint = death, no exceptions.
        This will trigger kill on next health check.
        """
        await self.db.execute("""
            UPDATE sender_accounts
            SET
                complaints_lifetime = COALESCE(complaints_lifetime, 0) + 1,
                updated_at = NOW()
            WHERE id = $1
        """, sender_account_id)

        # Log the spam complaint for visibility
        email_str = f" ({inbox_email})" if inbox_email else ""
        print(f"      [SPAM COMPLAINT] Inbox{email_str} - complaints_lifetime incremented")

    def is_spam_complaint(self, body: str, bounce_reason: str) -> bool:
        """
        Detect if a bounce message is actually a spam complaint (FBL).

        Spam complaints come through Feedback Loops (FBL) and contain
        specific patterns that distinguish them from regular spam blocks.

        Returns:
            True if message appears to be a spam complaint (user clicked "Report as Spam")
        """
        if not body and not bounce_reason:
            return False

        combined = f"{body or ''} {bounce_reason or ''}".lower()

        # Feedback Loop / Abuse Report Format indicators
        # These indicate a user actively reported the email as spam
        fbl_patterns = [
            'feedback-type:',       # ARF header
            'abuse report',         # Generic abuse report
            'complaint feedback',   # Feedback loop notification
            'spam report',          # Direct spam report
            'user complaint',       # User-initiated complaint
            'marked as spam',       # User action
            'reported as spam',     # User action
            'reported as junk',     # Microsoft terminology
            'moved to junk',        # Microsoft action
            'report-type: abuse',   # ARF format
            'arf report',           # Abuse Reporting Format
            'x-hmxmroriginalrecipient',  # Microsoft Junk Mail Reporting
            'x-ms-exchange-message-is-junk',  # Exchange junk indicator
            'feedback-id:',         # Google FBL header
            'original-rcpt-to',     # FBL original recipient
            'this is an email abuse report',  # Common FBL intro
        ]

        for pattern in fbl_patterns:
            if pattern in combined:
                return True

        # SMTP codes that indicate spam complaint (not just block)
        # 550 5.7.1 with complaint keywords is more likely FBL
        complaint_smtp_patterns = [
            '550 5.7.1',            # General policy rejection
            '550 5.7.51',           # Microsoft: user reported spam
            '550 5.7.511',          # Microsoft: user blocked sender
        ]

        # Only trigger on SMTP codes if combined with complaint keywords
        complaint_keywords = ['complaint', 'abuse', 'report', 'user']
        for smtp_code in complaint_smtp_patterns:
            if smtp_code in combined:
                if any(kw in combined for kw in complaint_keywords):
                    return True

        return False
