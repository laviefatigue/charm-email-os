"""
Hypertide Slack Notifications

Sends Slack notifications for order lifecycle events:
- Order started (processing)
- Order completed (success)
- Order failed (with manual retry option)

Features:
- Color-coded messages (blue=started, green=success, red=failed)
- Detailed error information for debugging
- Manual retry button for failed orders
- No automatic retry messaging

Usage:
    notifier = SlackNotifier(webhook_url="...")
    await notifier.notify_order_started(request)
    await notifier.notify_order_failed(request, result, error)
    await notifier.notify_order_completed(request, result)
"""

import httpx
import logging
from datetime import datetime
from typing import Optional, Any
from uuid import UUID

from .models import (
    PlanType,
    OrderStatus,
    FailureReason,
    SingleOrderRequest,
    OrderResult,
    BatchOrderResult,
    PLAN_SPECS,
)


logger = logging.getLogger(__name__)


# =============================================================================
# Slack Message Colors
# =============================================================================

class SlackColor:
    """Slack attachment colors."""
    INFO = "#3498db"      # Blue - started, info
    SUCCESS = "#28a745"   # Green - completed
    WARNING = "#f39c12"   # Amber - partial success
    ERROR = "#dc3545"     # Red - failed


# =============================================================================
# Slack Notifier
# =============================================================================

class SlackNotifier:
    """
    Slack notification service for Hypertide orders.

    Sends formatted messages to a Slack webhook with:
    - Order details and status
    - Color-coded severity
    - Action buttons (retry, view)
    - Error details for debugging
    """

    def __init__(
        self,
        webhook_url: str,
        channel: Optional[str] = None,
        app_base_url: str = "https://app2.hypertide.io",
        api_base_url: str = "https://api.charmemailos.com",
    ):
        self.webhook_url = webhook_url
        self.channel = channel
        self.app_base_url = app_base_url
        self.api_base_url = api_base_url
        self.enabled = bool(webhook_url)

    async def send(self, message: dict) -> bool:
        """Send a Slack message via webhook."""
        if not self.enabled:
            logger.warning("Slack notifications disabled (no webhook URL)")
            return False

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(self.webhook_url, json=message)

            if response.status_code == 200:
                logger.info("Slack notification sent successfully")
                return True
            else:
                logger.warning(
                    f"Slack notification failed: {response.status_code} - {response.text}"
                )
                return False

        except Exception as e:
            logger.error(f"Failed to send Slack notification: {e}")
            return False

    # =========================================================================
    # Order Lifecycle Notifications
    # =========================================================================

    async def notify_order_started(
        self,
        request: SingleOrderRequest,
        client_name: Optional[str] = None,
    ) -> bool:
        """
        Notify that order processing has started.

        Blue color indicator.
        """
        name = client_name or request.client_name
        spec = PLAN_SPECS[request.plan]
        expected_inboxes = len(request.domains) * spec["inboxes_per_domain"]
        monthly_cost = request.monthly_cost

        blocks = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": ":rocket: *Hypertide Order Started*"
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"*Client:* {name}\n"
                        f"*Plan:* {self._plan_emoji(request.plan)} {request.plan.value.upper()}\n"
                        f"*Domains:* {len(request.domains)}\n"
                        f"*Expected Inboxes:* {expected_inboxes}\n"
                        f"*Est. Cost:* ${monthly_cost:.0f}/mo"
                    )
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Domains:*\n```{self._format_domains(request.domains)}```"
                }
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"Order ID: `{str(request.order_id)[:8]}...` | :hourglass_flowing_sand: Processing via API..."
                    }
                ]
            }
        ]

        message = {
            "attachments": [{"color": SlackColor.INFO, "blocks": blocks}],
            "text": f"Order started for {name}"
        }

        return await self.send(message)

    async def notify_order_completed(
        self,
        request: SingleOrderRequest,
        result: OrderResult,
        client_name: Optional[str] = None,
    ) -> bool:
        """
        Notify that order completed successfully.

        Green color indicator.
        """
        name = client_name or request.client_name

        blocks = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": ":white_check_mark: *Hypertide Order Completed*"
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"*Client:* {name}\n"
                        f"*Plan:* {self._plan_emoji(request.plan)} {request.plan.value.upper()}\n"
                        f"*Domains:* {len(request.domains)}\n"
                        f"*Inboxes Created:* {result.inboxes_created}\n"
                        f"*Monthly Cost:* ${result.monthly_cost:.0f}/mo"
                    )
                }
            },
        ]

        # Add Hypertide order IDs if available
        if result.hypertide_order_ids:
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Hypertide Order IDs:*\n`{', '.join(result.hypertide_order_ids)}`"
                }
            })

        # Add duration
        if result.duration_seconds:
            blocks.append({
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"Order ID: `{str(request.order_id)[:8]}...` | Completed in {result.duration_seconds:.1f}s"
                    }
                ]
            })

        message = {
            "attachments": [{"color": SlackColor.SUCCESS, "blocks": blocks}],
            "text": f"Order completed for {name}"
        }

        return await self.send(message)

    async def notify_order_failed(
        self,
        request: SingleOrderRequest,
        result: OrderResult,
        client_name: Optional[str] = None,
        job_id: Optional[UUID] = None,
    ) -> bool:
        """
        Notify that order failed with error details.

        Red color indicator.
        Includes manual retry button (no auto-retry).
        """
        name = client_name or request.client_name
        job_id = job_id or request.job_id

        # Error details
        error_type = result.failure_reason.value if result.failure_reason else "unknown"
        error_message = result.error_message or "Unknown error"

        blocks = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": ":x: *Hypertide Order Failed*"
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"*Client:* {name}\n"
                        f"*Plan:* {self._plan_emoji(request.plan)} {request.plan.value.upper()}\n"
                        f"*Domains:* {len(request.domains)}"
                    )
                }
            },
            {"type": "divider"},
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"*Error Type:* `{error_type}`\n"
                        f"*Error Message:*\n```{error_message[:500]}```"
                    )
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Domains:*\n```{self._format_domains(request.domains)}```"
                }
            },
        ]

        # Add action buttons
        actions = []

        # Manual retry button (requires job_id)
        if job_id:
            retry_url = f"{self.api_base_url}/v1/inbox-purchasing/{job_id}/retry"
            actions.append({
                "type": "button",
                "text": {"type": "plain_text", "text": ":arrows_counterclockwise: Manual Retry", "emoji": True},
                "url": retry_url,
                "style": "primary"
            })

        # View in Hypertide
        actions.append({
            "type": "button",
            "text": {"type": "plain_text", "text": ":eyes: View Hypertide", "emoji": True},
            "url": f"{self.app_base_url}/orders"
        })

        if actions:
            blocks.append({
                "type": "actions",
                "elements": actions
            })

        # Context footer
        blocks.append({
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": (
                        f"Order ID: `{str(request.order_id)[:8]}...` | "
                        f"No automatic retry - manual intervention required"
                    )
                }
            ]
        })

        message = {
            "attachments": [{"color": SlackColor.ERROR, "blocks": blocks}],
            "text": f"Order failed for {name}: {error_type}"
        }

        return await self.send(message)

    async def notify_batch_completed(
        self,
        result: BatchOrderResult,
        client_name: Optional[str] = None,
    ) -> bool:
        """
        Notify batch order completion.

        Color based on success:
        - Green: all succeeded
        - Amber: partial success
        - Red: all failed
        """
        name = client_name or result.client_name

        if result.success:
            emoji = ":white_check_mark:"
            title = "Batch Order Completed"
            color = SlackColor.SUCCESS
        elif result.partial_success:
            emoji = ":warning:"
            title = "Batch Order Partially Completed"
            color = SlackColor.WARNING
        else:
            emoji = ":x:"
            title = "Batch Order Failed"
            color = SlackColor.ERROR

        blocks = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"{emoji} *{title}*"
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"*Client:* {name}\n"
                        f"*Orders:* {result.successful_orders}/{result.total_orders} succeeded\n"
                        f"*Total Inboxes:* {result.total_inboxes}\n"
                        f"*Monthly Cost:* ${result.total_monthly_cost:.0f}/mo"
                    )
                }
            },
        ]

        # Add errors if any
        if result.errors:
            error_summary = "\n".join(f"- {e[:100]}" for e in result.errors[:5])
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Errors:*\n{error_summary}"
                }
            })

        # Add duplicate domains if any
        if result.duplicate_domains:
            dupe_list = ", ".join(result.duplicate_domains[:10])
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Duplicate Domains:* {dupe_list}"
                }
            })

        # Context
        duration = None
        if result.completed_at:
            duration = (result.completed_at - result.started_at).total_seconds()

        blocks.append({
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": (
                        f"Batch ID: `{str(result.batch_id)[:8]}...` | "
                        f"Duration: {duration:.1f}s" if duration else ""
                    )
                }
            ]
        })

        message = {
            "attachments": [{"color": color, "blocks": blocks}],
            "text": f"{title}: {name}"
        }

        return await self.send(message)

    # =========================================================================
    # Helper Methods
    # =========================================================================

    def _plan_emoji(self, plan: PlanType) -> str:
        """Get emoji for plan type."""
        return ":office:" if plan == PlanType.ENTRA else ":envelope:"

    def _format_domains(self, domains: list[str], limit: int = 20) -> str:
        """Format domain list for display."""
        display = "\n".join(domains[:limit])
        if len(domains) > limit:
            display += f"\n... and {len(domains) - limit} more"
        return display


# =============================================================================
# Factory Function
# =============================================================================

def create_slack_notifier(
    webhook_url: Optional[str] = None,
) -> SlackNotifier:
    """
    Create a Slack notifier from environment or parameter.

    Checks SLACK_ORDERS_WEBHOOK_URL env var if not provided.
    """
    import os

    url = webhook_url or os.getenv("SLACK_ORDERS_WEBHOOK_URL", "")

    return SlackNotifier(
        webhook_url=url,
        app_base_url=os.getenv("HYPERTIDE_APP_URL", "https://app2.hypertide.io"),
        api_base_url=os.getenv("CHARM_API_URL", "https://api.charmemailos.com"),
    )
