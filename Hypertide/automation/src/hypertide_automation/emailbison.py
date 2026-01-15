"""
Email Bison API client for inbox management.

Handles uploading provisioned inboxes to Email Bison workspaces.

Note: Email Bison workspace CREATION is not supported by API.
Workspaces must be created manually in the UI first.
"""

import os
from typing import Optional, List, Dict, Any
from datetime import datetime

import httpx
import structlog
from pydantic import BaseModel, Field

logger = structlog.get_logger()


class EmailBisonConfig(BaseModel):
    """Email Bison API configuration."""
    api_url: str = Field(default="https://api.emailbison.com")
    api_token: str = Field(default="")
    timeout: int = Field(default=30)

    @classmethod
    def from_env(cls) -> "EmailBisonConfig":
        """Load from environment variables."""
        return cls(
            api_url=os.getenv("EMAILBISON_API_URL", "https://api.emailbison.com"),
            api_token=os.getenv("EMAILBISON_API_TOKEN", ""),
            timeout=int(os.getenv("EMAILBISON_TIMEOUT", "30")),
        )


class InboxUpload(BaseModel):
    """Data for uploading an inbox to Email Bison."""
    email: str
    first_name: str
    last_name: str
    provider: str  # 'azure' or 'google'
    smtp_host: Optional[str] = None
    smtp_port: Optional[int] = None
    imap_host: Optional[str] = None
    imap_port: Optional[int] = None
    username: Optional[str] = None
    password: Optional[str] = None


class UploadResult(BaseModel):
    """Result of an inbox upload operation."""
    email: str
    success: bool
    emailbison_inbox_id: Optional[str] = None
    error: Optional[str] = None


class EmailBisonClient:
    """
    Client for Email Bison API.

    Usage:
        async with EmailBisonClient() as client:
            result = await client.upload_inbox(workspace, inbox)
    """

    def __init__(self, config: Optional[EmailBisonConfig] = None):
        self.config = config or EmailBisonConfig.from_env()
        self._client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self) -> "EmailBisonClient":
        self._client = httpx.AsyncClient(
            base_url=self.config.api_url,
            timeout=self.config.timeout,
            headers={
                "Authorization": f"Bearer {self.config.api_token}",
                "Content-Type": "application/json",
            },
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        if self._client:
            await self._client.aclose()

    # =========================================================================
    # Workspace Operations
    # =========================================================================

    async def list_workspaces(self) -> List[Dict[str, Any]]:
        """List all accessible workspaces."""
        try:
            response = await self._client.get("/workspaces")
            response.raise_for_status()
            return response.json().get("workspaces", [])
        except httpx.HTTPError as e:
            logger.error("Failed to list workspaces", error=str(e))
            return []

    async def get_workspace(self, workspace_name: str) -> Optional[Dict[str, Any]]:
        """Get workspace by name."""
        workspaces = await self.list_workspaces()
        for ws in workspaces:
            if ws.get("name") == workspace_name or ws.get("slug") == workspace_name:
                return ws
        return None

    # =========================================================================
    # Inbox Operations
    # =========================================================================

    async def upload_inbox(
        self,
        workspace_name: str,
        inbox: InboxUpload,
    ) -> UploadResult:
        """
        Upload a single inbox to a workspace.

        Args:
            workspace_name: Target workspace name/slug
            inbox: Inbox data to upload

        Returns:
            UploadResult with success status
        """
        try:
            # Find workspace
            workspace = await self.get_workspace(workspace_name)
            if not workspace:
                return UploadResult(
                    email=inbox.email,
                    success=False,
                    error=f"Workspace '{workspace_name}' not found",
                )

            workspace_id = workspace.get("id")

            # Prepare inbox payload
            payload = {
                "email": inbox.email,
                "first_name": inbox.first_name,
                "last_name": inbox.last_name,
                "provider": inbox.provider,
            }

            # Add optional SMTP/IMAP config if provided
            if inbox.smtp_host:
                payload["smtp_config"] = {
                    "host": inbox.smtp_host,
                    "port": inbox.smtp_port or 587,
                }
            if inbox.imap_host:
                payload["imap_config"] = {
                    "host": inbox.imap_host,
                    "port": inbox.imap_port or 993,
                }
            if inbox.username and inbox.password:
                payload["credentials"] = {
                    "username": inbox.username,
                    "password": inbox.password,
                }

            # Upload inbox
            response = await self._client.post(
                f"/workspaces/{workspace_id}/inboxes",
                json=payload,
            )
            response.raise_for_status()

            data = response.json()
            return UploadResult(
                email=inbox.email,
                success=True,
                emailbison_inbox_id=data.get("id"),
            )

        except httpx.HTTPStatusError as e:
            error_msg = f"HTTP {e.response.status_code}: {e.response.text}"
            logger.error("Inbox upload failed", email=inbox.email, error=error_msg)
            return UploadResult(
                email=inbox.email,
                success=False,
                error=error_msg,
            )
        except Exception as e:
            logger.error("Inbox upload failed", email=inbox.email, error=str(e))
            return UploadResult(
                email=inbox.email,
                success=False,
                error=str(e),
            )

    async def upload_inboxes_batch(
        self,
        workspace_name: str,
        inboxes: List[InboxUpload],
    ) -> List[UploadResult]:
        """
        Upload multiple inboxes to a workspace.

        Args:
            workspace_name: Target workspace
            inboxes: List of inboxes to upload

        Returns:
            List of UploadResults
        """
        results = []
        for inbox in inboxes:
            result = await self.upload_inbox(workspace_name, inbox)
            results.append(result)

            # Log progress
            status = "✓" if result.success else "✗"
            logger.info(
                f"{status} {inbox.email}",
                success=result.success,
                error=result.error,
            )

        return results

    # =========================================================================
    # Workspace Inbox Listing
    # =========================================================================

    async def list_workspace_inboxes(
        self,
        workspace_name: str,
    ) -> List[Dict[str, Any]]:
        """List all inboxes in a workspace."""
        try:
            workspace = await self.get_workspace(workspace_name)
            if not workspace:
                logger.warning("Workspace not found", workspace=workspace_name)
                return []

            workspace_id = workspace.get("id")
            response = await self._client.get(f"/workspaces/{workspace_id}/inboxes")
            response.raise_for_status()
            return response.json().get("inboxes", [])

        except httpx.HTTPError as e:
            logger.error("Failed to list inboxes", error=str(e))
            return []


# Convenience function
async def get_emailbison_client() -> EmailBisonClient:
    """Get an Email Bison client instance."""
    client = EmailBisonClient()
    await client.__aenter__()
    return client
