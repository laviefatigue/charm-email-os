"""
EmailBison API client for real-time inbox metrics.

Provides workspace summary, inbox health, and connection status directly from EmailBison.
"""

import httpx
import logging
import os
from typing import Optional
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class InboxSummary(BaseModel):
    """Summary of inbox metrics from EmailBison."""
    total_inboxes: int = 0
    connected: int = 0
    not_connected: int = 0
    avg_health_score: float = 0.0


class ProviderBreakdown(BaseModel):
    """Provider-specific inbox metrics."""
    provider: str
    count: int = 0
    percentage: float = 0.0
    connected: int = 0
    connection_rate: float = 0.0
    avg_health_score: float = 0.0


class TopIssue(BaseModel):
    """An inbox with issues."""
    email: str
    provider: Optional[str] = None
    health_score: Optional[int] = None
    bounce_rate: Optional[float] = None
    bounced: Optional[int] = None
    sent: Optional[int] = None


class WorkspaceHealthSummary(BaseModel):
    """Complete workspace health summary from EmailBison."""
    workspace_name: str
    total_inboxes: int = 0
    connected: int = 0
    not_connected: int = 0
    avg_health_score: float = 0.0
    provider_breakdown: list[ProviderBreakdown] = []
    disconnected_sample: list[TopIssue] = []
    low_health_sample: list[TopIssue] = []
    high_bounce_sample: list[TopIssue] = []
    recommendations: list[str] = []
    error: Optional[str] = None


class EmailBisonService:
    """
    EmailBison API client for real-time inbox data.

    Usage:
        async with EmailBisonService() as bison:
            summary = await bison.get_workspace_summary("Charm")
    """

    BASE_URL = "https://spellcast.hirecharm.com"

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
    ):
        """
        Initialize EmailBison client.

        Args:
            api_key: EmailBison API key (or use EMAILBISON_API_KEY env var)
            base_url: Base API URL (or use EMAILBISON_API_URL env var)
        """
        self.api_key = api_key or os.environ.get("EMAILBISON_API_KEY", "")
        self.base_url = base_url or os.environ.get("EMAILBISON_API_URL", self.BASE_URL)
        self.base_url = self.base_url.rstrip("/")

        self._client: Optional[httpx.AsyncClient] = None
        self._workspace_id: Optional[int] = None

    async def __aenter__(self):
        await self._ensure_client()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def _ensure_client(self):
        """Create HTTP client if not exists."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=30.0,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                }
            )

    async def close(self):
        """Close HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def _get_workspace_id(self, workspace_name: str) -> Optional[int]:
        """Get workspace ID by name from the API."""
        try:
            response = await self._client.get(f"{self.base_url}/api/workspaces/v1.1")
            response.raise_for_status()
            data = response.json()
            workspaces = data.get("data", [])

            for ws in workspaces:
                if ws.get("name", "").lower() == workspace_name.lower():
                    return ws.get("id")

            return None
        except Exception as e:
            logger.error(f"Failed to get workspace list: {e}")
            return None

    async def _switch_workspace(self, workspace_id: int) -> bool:
        """Switch to a specific workspace context."""
        try:
            response = await self._client.post(
                f"{self.base_url}/api/workspaces/v1.1/switch-workspace",
                json={"team_id": workspace_id}
            )
            response.raise_for_status()
            self._workspace_id = workspace_id
            return True
        except Exception as e:
            logger.error(f"Failed to switch workspace: {e}")
            return False

    async def get_workspace_summary(self, workspace_name: str) -> WorkspaceHealthSummary:
        """
        Get real-time health summary for a workspace.

        Args:
            workspace_name: Name of the EmailBison workspace

        Returns:
            WorkspaceHealthSummary with inbox counts, health scores, and issues
        """
        if not self.api_key:
            logger.warning("EmailBison API key not configured")
            return WorkspaceHealthSummary(
                workspace_name=workspace_name,
                error="EmailBison API key not configured"
            )

        await self._ensure_client()

        try:
            # Step 1: Find workspace ID by name
            workspace_id = await self._get_workspace_id(workspace_name)
            if workspace_id is None:
                return WorkspaceHealthSummary(
                    workspace_name=workspace_name,
                    error=f"Workspace '{workspace_name}' not found"
                )

            # Step 2: Switch to that workspace
            switched = await self._switch_workspace(workspace_id)
            if not switched:
                return WorkspaceHealthSummary(
                    workspace_name=workspace_name,
                    error=f"Failed to switch to workspace '{workspace_name}'"
                )

            # Step 3: Get sender emails (inboxes) with pagination
            all_inboxes = []
            page = 1
            while True:
                response = await self._client.get(
                    f"{self.base_url}/api/sender-emails",
                    params={"page": page, "per_page": 100}
                )
                response.raise_for_status()
                data = response.json()

                inboxes = data.get("data", [])
                if not inboxes:
                    break

                all_inboxes.extend(inboxes)

                # Check if more pages
                meta = data.get("meta", {})
                last_page = meta.get("last_page", 1)
                if page >= last_page:
                    break
                page += 1

            return self._parse_inbox_list(workspace_name, all_inboxes)

        except httpx.HTTPStatusError as e:
            logger.error(f"EmailBison API error: {e.response.status_code} - {e.response.text}")
            return WorkspaceHealthSummary(
                workspace_name=workspace_name,
                error=f"API error: {e.response.status_code}"
            )
        except Exception as e:
            logger.error(f"EmailBison API error: {e}")
            return WorkspaceHealthSummary(
                workspace_name=workspace_name,
                error=str(e)
            )

    def _parse_inbox_list(self, workspace_name: str, inboxes: list) -> WorkspaceHealthSummary:
        """Parse raw inbox list into summary."""
        if not inboxes:
            return WorkspaceHealthSummary(
                workspace_name=workspace_name,
                recommendations=["No inboxes found in this workspace"]
            )

        total = len(inboxes)
        connected = 0
        not_connected = 0
        health_scores = []

        # Provider stats
        providers: dict[str, dict] = {}

        # Issue tracking
        disconnected_sample = []
        low_health_sample = []
        high_bounce_sample = []

        for inbox in inboxes:
            # Connection status - EmailBison uses "connection_status" field
            status = inbox.get("connection_status", inbox.get("status", "")).lower()
            is_connected = status in ("connected", "active", "1", "true")
            if is_connected:
                connected += 1
            else:
                not_connected += 1
                if len(disconnected_sample) < 5:
                    disconnected_sample.append(TopIssue(
                        email=inbox.get("email", inbox.get("email_address", "")),
                        provider=inbox.get("provider", inbox.get("esp_type", ""))
                    ))

            # Health score
            health = inbox.get("health_score", inbox.get("health", 100))
            if health is not None:
                health_scores.append(float(health))
                if health < 50 and len(low_health_sample) < 5:
                    low_health_sample.append(TopIssue(
                        email=inbox.get("email", inbox.get("email_address", "")),
                        health_score=int(health)
                    ))

            # Bounce rate
            bounced = inbox.get("bounced", 0) or 0
            sent = inbox.get("emails_sent", inbox.get("sent", 0)) or 0
            if sent > 0:
                bounce_rate = bounced / sent
                if bounce_rate > 0.02 and len(high_bounce_sample) < 5:
                    high_bounce_sample.append(TopIssue(
                        email=inbox.get("email", inbox.get("email_address", "")),
                        bounce_rate=round(bounce_rate, 4),
                        bounced=bounced,
                        sent=sent
                    ))

            # Provider breakdown - EmailBison uses "esp_type"
            provider = inbox.get("esp_type", inbox.get("provider", "Unknown"))
            if provider == "microsoft":
                provider = "Microsoft"
            elif provider == "google":
                provider = "Google"

            if provider not in providers:
                providers[provider] = {
                    "count": 0,
                    "connected": 0,
                    "health_scores": []
                }
            providers[provider]["count"] += 1
            if is_connected:
                providers[provider]["connected"] += 1
            if health is not None:
                providers[provider]["health_scores"].append(float(health))

        # Calculate averages
        avg_health = sum(health_scores) / len(health_scores) if health_scores else 0.0

        # Build provider breakdown
        provider_breakdown = []
        for name, stats in providers.items():
            count = stats["count"]
            conn = stats["connected"]
            scores = stats["health_scores"]
            provider_breakdown.append(ProviderBreakdown(
                provider=name,
                count=count,
                percentage=round(count / total * 100, 1) if total > 0 else 0,
                connected=conn,
                connection_rate=round(conn / count * 100, 1) if count > 0 else 0,
                avg_health_score=round(sum(scores) / len(scores), 1) if scores else 0
            ))

        # Sort by count descending
        provider_breakdown.sort(key=lambda p: p.count, reverse=True)

        # Generate recommendations
        recommendations = []
        if not_connected > 0:
            recommendations.append(f"🔴 {not_connected} disconnected inboxes - reconnect to restore capacity")
        if low_health_sample:
            recommendations.append(f"⚠️ {len([h for h in health_scores if h < 50])} inboxes with health < 50 - review and repair")
        if high_bounce_sample:
            recommendations.append(f"🚨 {len(high_bounce_sample)} HIGH BOUNCE inboxes (>2% bounce rate) - immediate review needed")

        return WorkspaceHealthSummary(
            workspace_name=workspace_name,
            total_inboxes=total,
            connected=connected,
            not_connected=not_connected,
            avg_health_score=round(avg_health, 1),
            provider_breakdown=provider_breakdown,
            disconnected_sample=disconnected_sample,
            low_health_sample=low_health_sample,
            high_bounce_sample=high_bounce_sample,
            recommendations=recommendations
        )


# Singleton instance for reuse
_service: Optional[EmailBisonService] = None


async def get_emailbison_service() -> EmailBisonService:
    """Get or create EmailBison service instance."""
    global _service
    if _service is None:
        _service = EmailBisonService()
    return _service
