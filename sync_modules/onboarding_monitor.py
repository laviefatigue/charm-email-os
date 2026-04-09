"""
Onboarding Form Monitor Module

Daily check for new client onboarding form submissions.
Transitions submitted forms to 'processing' status and will trigger
downstream domain generation (future: wired in domain-generation engine doc).

Also checks for stale clients who haven't submitted a form after a
configurable number of days and sends reminders via Slack.

Usage:
    from sync_modules.onboarding_monitor import OnboardingMonitorModule

    monitor = OnboardingMonitorModule(db, alerter, audit_logger)
    results = await monitor.run()
"""

import os
import logging
import httpx
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

ONBOARDING_REMINDER_DAYS = int(os.getenv("ONBOARDING_REMINDER_DAYS", "7"))
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN", "")
ONBOARDING_FORM_BASE_URL = os.getenv(
    "ONBOARDING_FORM_BASE_URL",
    "https://onboard.laviefatigue.com"
)


class OnboardingMonitorModule:
    """Daily monitor for onboarding form submissions.

    Checks for new submissions (status='submitted'),
    transitions them to 'processing', and will trigger
    domain generation (future: next engine module).

    Also checks for stale clients who haven't submitted
    after a configurable number of days.
    """

    def __init__(self, db, alerter=None, audit_logger=None):
        """
        Initialize the onboarding monitor.

        Args:
            db: asyncpg connection pool
            alerter: SlackAlerter instance (for ops notifications)
            audit_logger: AuditLogger instance
        """
        self.db = db
        self.alerter = alerter
        self.audit_logger = audit_logger
        self.reminder_days = ONBOARDING_REMINDER_DAYS
        self.slack_bot_token = SLACK_BOT_TOKEN

    async def process_new_submissions(self) -> dict:
        """Find and process submitted onboarding forms.

        Picks up submissions with status='submitted' and processed_at IS NULL.
        For clients with multiple submissions, processes only the latest one.

        Returns:
            dict with keys: processed, skipped, errors
        """
        results = {"processed": 0, "skipped": 0, "errors": 0}

        # Find new submissions — latest per client, only unprocessed
        rows = await self.db.fetch("""
            SELECT DISTINCT ON (s.client_id)
                s.id as submission_id,
                s.client_id,
                s.company_name,
                s.contact_name as submission_contact,
                s.submission_status,
                c.name as client_name,
                c.slack_channel_id,
                c.contact_email
            FROM client_onboarding_submissions s
            JOIN clients c ON c.id = s.client_id
            WHERE s.submission_status = 'submitted'
              AND s.processed_at IS NULL
            ORDER BY s.client_id, s.submitted_at DESC
        """)

        if not rows:
            logger.info("Onboarding monitor: no new submissions to process")
            return results

        for row in rows:
            try:
                submission_id = row["submission_id"]
                client_name = row["client_name"]
                company = row["company_name"] or client_name

                # Transition: submitted → processing
                await self.db.execute("""
                    UPDATE client_onboarding_submissions
                    SET submission_status = 'processing',
                        processed_at = NOW(),
                        updated_at = NOW()
                    WHERE id = $1
                """, submission_id)

                logger.info(
                    f"Onboarding monitor: processing submission {submission_id} "
                    f"for client '{client_name}' (company: {company})"
                )

                # Notify client's Slack channel
                if row["slack_channel_id"]:
                    await self._notify_client_channel(
                        row["slack_channel_id"],
                        f"Onboarding form received from {company}. "
                        f"Processing submission and preparing for domain generation."
                    )

                # Notify ops via SlackAlerter
                if self.alerter:
                    await self.alerter.send_alert(
                        level="info",
                        title="Onboarding Form Received",
                        message=f"Client *{client_name}* submitted onboarding form.",
                        fields={
                            "Company": company,
                            "Contact": row["submission_contact"] or "—",
                        }
                    )

                # TODO: Trigger domain generation here
                # This will be wired in when the domain-generation engine doc is implemented.
                # For now, the submission sits in 'processing' status.

                results["processed"] += 1

            except Exception as e:
                logger.error(
                    f"Onboarding monitor: error processing submission "
                    f"{row['submission_id']}: {e}"
                )
                results["errors"] += 1

        return results

    async def check_stale_clients(self) -> dict:
        """Find clients with no submission after the reminder threshold.

        Checks for clients created more than ONBOARDING_REMINDER_DAYS ago
        who have no submission in submitted/processing/completed status.

        Returns:
            dict with key: reminded
        """
        results = {"reminded": 0}

        rows = await self.db.fetch(f"""
            SELECT
                c.id as client_id,
                c.name as client_name,
                c.contact_email,
                c.slack_channel_id,
                c.created_at
            FROM clients c
            WHERE c.created_at < NOW() - INTERVAL '{self.reminder_days} days'
              AND NOT EXISTS (
                  SELECT 1 FROM client_onboarding_submissions s
                  WHERE s.client_id = c.id
                    AND s.submission_status IN ('submitted', 'processing', 'completed')
              )
        """)

        if not rows:
            logger.info("Onboarding monitor: no stale clients found")
            return results

        for row in rows:
            client_name = row["client_name"]
            days_ago = (datetime.now(row["created_at"].tzinfo) - row["created_at"]).days

            # Notify client's Slack channel
            if row["slack_channel_id"]:
                form_url = f"{ONBOARDING_FORM_BASE_URL}?client_id={row['client_id']}"
                await self._notify_client_channel(
                    row["slack_channel_id"],
                    f"Reminder: Onboarding form has not been submitted yet "
                    f"(created {days_ago} days ago).\n"
                    f"<{form_url}|Complete the onboarding form>"
                )

            # Notify ops
            if self.alerter:
                await self.alerter.send_alert(
                    level="warning",
                    title="Stale Client — No Onboarding Form",
                    message=f"Client *{client_name}* was created {days_ago} days ago "
                            f"but has not submitted an onboarding form.",
                    fields={
                        "Client": client_name,
                        "Contact": row["contact_email"] or "—",
                        "Days Since Creation": str(days_ago),
                    }
                )

            results["reminded"] += 1
            logger.info(f"Onboarding monitor: reminder sent for stale client '{client_name}' ({days_ago} days)")

        return results

    async def _notify_client_channel(self, slack_channel_id: str, message: str) -> bool:
        """Post a notification to a client's Slack channel.

        Uses the bot token directly (same httpx pattern as SlackAlerter).
        Returns True on success, False on failure.
        """
        if not self.slack_bot_token or not slack_channel_id:
            return False

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    "https://slack.com/api/chat.postMessage",
                    json={
                        "channel": slack_channel_id,
                        "text": message,
                    },
                    headers={
                        "Authorization": f"Bearer {self.slack_bot_token}",
                        "Content-Type": "application/json; charset=utf-8",
                    },
                )
                result = response.json()
                if not result.get("ok"):
                    logger.warning(f"Slack post to {slack_channel_id} failed: {result.get('error')}")
                    return False
                return True
        except Exception as e:
            logger.warning(f"Slack notify error for channel {slack_channel_id}: {e}")
            return False

    async def run(self) -> dict:
        """Main entry point — called by sync worker daily.

        Returns combined results from submission processing and stale client checks.
        """
        results = {}
        results["submissions"] = await self.process_new_submissions()
        results["stale"] = await self.check_stale_clients()
        return results
