"""
Slack Alerter

Sends notifications to Slack webhook for sync errors and kill triggers.
"""
import os
from datetime import datetime
from typing import Dict, List, Optional
import httpx

SLACK_WEBHOOK_URL = os.getenv('SLACK_WEBHOOK_URL', '')


class SlackAlerter:
    """Slack notification service for sync alerts."""

    def __init__(self, webhook_url: str = None):
        self.webhook_url = webhook_url or SLACK_WEBHOOK_URL
        self.enabled = bool(self.webhook_url)

    async def send_alert(
        self,
        level: str,
        title: str,
        message: str,
        fields: Dict[str, str] = None,
        context: str = None
    ) -> bool:
        """
        Send alert to Slack channel.

        Args:
            level: 'error', 'warning', or 'info'
            title: Alert title
            message: Alert message
            fields: Optional key-value fields to display
            context: Optional context/footer text
        """
        if not self.enabled:
            print(f"[SLACK DISABLED] {level.upper()}: {title} - {message}")
            return False

        # Color mapping
        colors = {
            'error': '#dc3545',    # Red
            'warning': '#ffc107',  # Yellow
            'info': '#17a2b8',     # Blue
            'success': '#28a745'   # Green
        }

        # Build blocks
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"{self._get_emoji(level)} {title}",
                    "emoji": True
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": message
                }
            }
        ]

        # Add fields if provided
        if fields:
            field_blocks = [
                {"type": "mrkdwn", "text": f"*{k}:*\n{v}"}
                for k, v in fields.items()
            ]
            blocks.append({
                "type": "section",
                "fields": field_blocks[:10]  # Slack limit
            })

        # Add context/footer
        if context:
            blocks.append({
                "type": "context",
                "elements": [
                    {"type": "mrkdwn", "text": context}
                ]
            })

        # Add timestamp
        blocks.append({
            "type": "context",
            "elements": [
                {"type": "mrkdwn", "text": f"Sent at {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}"}
            ]
        })

        payload = {
            "attachments": [{
                "color": colors.get(level, '#6c757d'),
                "blocks": blocks
            }]
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(self.webhook_url, json=payload)
                return response.status_code == 200
        except Exception as e:
            print(f"[SLACK ERROR] Failed to send alert: {e}")
            return False

    def _get_emoji(self, level: str) -> str:
        """Get emoji for alert level."""
        return {
            'error': ':x:',
            'warning': ':warning:',
            'info': ':information_source:',
            'success': ':white_check_mark:'
        }.get(level, ':bell:')

    # =========================================================================
    # CONVENIENCE METHODS
    # =========================================================================

    async def alert_sync_failure(
        self,
        module: str,
        error: str,
        workspace: str = None,
        records_processed: int = 0
    ):
        """Alert on sync module failure."""
        fields = {'Module': module}
        if workspace:
            fields['Workspace'] = workspace
        if records_processed:
            fields['Records Processed'] = str(records_processed)

        await self.send_alert(
            level='error',
            title=f'Sync Module Failed: {module}',
            message=f"```{error[:1000]}```",
            fields=fields,
            context='EmailBison Daily Sync Worker'
        )

    async def alert_kill_trigger(
        self,
        inbox_email: str,
        workspace: str,
        trigger: str,
        value: float,
        threshold: float
    ):
        """Alert when inbox is queued for kill."""
        await self.send_alert(
            level='warning',
            title='Inbox Kill Trigger Fired',
            message=f"Inbox `{inbox_email}` has been queued for deletion (24hr waiting period)",
            fields={
                'Trigger': trigger,
                'Value': f'{value:.4f}',
                'Threshold': f'{threshold:.4f}',
                'Workspace': workspace,
                'Status': 'Tagged for 24hr queue'
            },
            context='Kill Queue Processor'
        )

    async def alert_inbox_deleted(
        self,
        inbox_email: str,
        workspace: str,
        trigger: str
    ):
        """Alert when inbox is actually deleted."""
        await self.send_alert(
            level='info',
            title='Inbox Deleted',
            message=f"Inbox `{inbox_email}` has been permanently removed after 24hr waiting period",
            fields={
                'Trigger': trigger,
                'Workspace': workspace
            },
            context='Kill Queue Processor'
        )

    async def alert_health_critical(
        self,
        workspace: str,
        critical_inboxes: int,
        dead_inboxes: int,
        health_score: float
    ):
        """Alert on critical health status."""
        await self.send_alert(
            level='error',
            title=f'Critical Health Alert: {workspace}',
            message=f"Workspace health has dropped to critical level",
            fields={
                'Health Score': f'{health_score:.1f}%',
                'Critical Inboxes': str(critical_inboxes),
                'Dead Inboxes': str(dead_inboxes)
            },
            context='Health Check Module'
        )

    async def alert_sync_summary(
        self,
        results: List[Dict],
        total_duration: float
    ):
        """Send daily sync summary."""
        total_processed = sum(r.get('records_processed', 0) for r in results)
        failed_modules = [r['sync_type'] for r in results if r.get('status') == 'failed']

        level = 'error' if failed_modules else 'success'
        title = 'Daily Sync Summary'

        message_parts = [
            f"*Total Records Processed:* {total_processed}",
            f"*Duration:* {total_duration:.1f} seconds",
        ]

        if failed_modules:
            message_parts.append(f"*Failed Modules:* {', '.join(failed_modules)}")

        await self.send_alert(
            level=level,
            title=title,
            message='\n'.join(message_parts),
            context='EmailBison Daily Sync Worker'
        )
