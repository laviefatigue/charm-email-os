"""
Prefect Flow: Push Campaign to EmailBison

This flow handles pushing approved campaign suggestions from Charm Email OS
to a client's EmailBison workspace.

The flow:
1. Fetches the suggestion content from the Charm database
2. Creates a campaign variant in EmailBison via their API
3. Updates the Charm database with the EmailBison campaign ID

Usage:
    # Run directly
    python push_to_emailbison.py --suggestion-id <uuid>

    # Or trigger via Prefect deployment
    from prefect.deployments import run_deployment
    run_deployment(
        name="push-to-emailbison/production",
        parameters={"suggestion_id": "<uuid>"}
    )

Environment Variables:
    POSTGRES_HOST, POSTGRES_PORT, POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD
    EMAILBISON_API_KEY - API key for EmailBison
    EMAILBISON_API_URL - Base URL for EmailBison API (default: https://spellcast.hirecharm.com/api)
"""
import os
import sys
import subprocess
import asyncio
import argparse
from datetime import datetime
from typing import Optional

# Ensure required packages are installed
def _ensure_dependencies():
    """Install missing dependencies at runtime."""
    required = [("httpx", "httpx"), ("asyncpg", "asyncpg")]
    for module_name, package_name in required:
        try:
            __import__(module_name)
        except ImportError:
            print(f"Installing missing dependency: {package_name}")
            subprocess.check_call([sys.executable, "-m", "pip", "install", package_name])

_ensure_dependencies()

import httpx
import asyncpg
from prefect import flow, task, get_run_logger

# Database configuration
DB_CONFIG = {
    "host": os.getenv("POSTGRES_HOST", "localhost"),
    "port": int(os.getenv("POSTGRES_PORT", "5432")),
    "database": os.getenv("POSTGRES_DB", "postgres"),
    "user": os.getenv("POSTGRES_USER", "postgres"),
    "password": os.getenv("POSTGRES_PASSWORD", ""),
}

# EmailBison configuration
EMAILBISON_API_URL = os.getenv("EMAILBISON_API_URL", "https://spellcast.hirecharm.com/api")
EMAILBISON_API_KEY = os.getenv("EMAILBISON_API_KEY", "")


async def get_db_pool():
    """Create a database connection pool."""
    return await asyncpg.create_pool(
        host=DB_CONFIG["host"],
        port=DB_CONFIG["port"],
        database=DB_CONFIG["database"],
        user=DB_CONFIG["user"],
        password=DB_CONFIG["password"],
    )


@task(name="fetch-suggestion-content", retries=2, retry_delay_seconds=5)
async def fetch_suggestion_content(suggestion_id: str) -> dict:
    """
    Fetch the suggestion content and client workspace info from Charm DB.

    Returns:
        Dict with suggestion content, client info, and workspace details
    """
    logger = get_run_logger()
    logger.info(f"Fetching suggestion {suggestion_id} from database")

    pool = await get_db_pool()

    try:
        async with pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT
                    s.id,
                    s.client_id,
                    s.strategy_id,
                    s.subject_line,
                    s.email_body,
                    s.edited_subject_line,
                    s.edited_email_body,
                    s.campaign_type,
                    s.score,
                    s.status,
                    s.pushed_to_emailbison,
                    c.name as client_name,
                    c.workspace_id,
                    st.name as strategy_name
                FROM strategy_suggestions s
                JOIN clients c ON c.id = s.client_id
                LEFT JOIN strategies st ON st.id = s.strategy_id
                WHERE s.id = $1
            """, suggestion_id)

            if not row:
                raise ValueError(f"Suggestion {suggestion_id} not found")

            # Use edited content if available, otherwise original
            content = {
                "suggestion_id": str(row["id"]),
                "client_id": str(row["client_id"]),
                "client_name": row["client_name"],
                "workspace_id": str(row["workspace_id"]) if row["workspace_id"] else None,
                "strategy_id": str(row["strategy_id"]) if row["strategy_id"] else None,
                "strategy_name": row["strategy_name"],
                "subject_line": row["edited_subject_line"] or row["subject_line"],
                "email_body": row["edited_email_body"] or row["email_body"],
                "campaign_type": row["campaign_type"] or "cold_outreach",
                "score": row["score"],
                "status": row["status"],
                "already_pushed": row["pushed_to_emailbison"],
            }

            logger.info(f"Retrieved suggestion for client '{content['client_name']}'")
            return content

    finally:
        await pool.close()


@task(name="create-emailbison-campaign", retries=3, retry_delay_seconds=30)
async def create_emailbison_campaign(
    workspace_id: str,
    subject_line: str,
    email_body: str,
    campaign_name: str,
    campaign_type: str = "cold_outreach",
) -> dict:
    """
    Create a campaign in EmailBison via their REST API.

    Note: EmailBison MCP is read-only (analytics only), so we must use
    the REST API directly for campaign creation.

    Args:
        workspace_id: The client's EmailBison workspace UUID
        subject_line: Email subject line
        email_body: Email body content
        campaign_name: Name for the campaign in EmailBison
        campaign_type: Type of campaign (cold_outreach, newsletter, etc.)

    Returns:
        Dict with campaign_id and creation status
    """
    logger = get_run_logger()
    logger.info(f"Creating campaign in EmailBison workspace {workspace_id}")

    if not EMAILBISON_API_KEY:
        logger.warning("EMAILBISON_API_KEY not set - simulating campaign creation")
        # For development/testing without API key
        return {
            "campaign_id": f"eb_simulated_{datetime.now().strftime('%Y%m%d%H%M%S')}",
            "status": "simulated",
            "message": "Campaign creation simulated (no API key)",
        }

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            f"{EMAILBISON_API_URL}/campaigns",
            headers={
                "Authorization": f"Bearer {EMAILBISON_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "workspace_id": workspace_id,
                "name": campaign_name,
                "subject_line": subject_line,
                "email_body": email_body,
                "campaign_type": campaign_type,
                "status": "draft",  # Create as draft for human review
            },
        )

        if response.status_code == 401:
            raise ValueError("EmailBison API authentication failed - check API key")

        if response.status_code == 404:
            raise ValueError(f"EmailBison workspace {workspace_id} not found")

        response.raise_for_status()
        result = response.json()

        logger.info(f"Created EmailBison campaign: {result.get('campaign_id', 'unknown')}")
        return {
            "campaign_id": result.get("campaign_id") or result.get("id"),
            "status": "created",
            "message": "Campaign created successfully",
        }


@task(name="update-suggestion-pushed", retries=2, retry_delay_seconds=5)
async def update_suggestion_pushed(
    suggestion_id: str,
    emailbison_campaign_id: str,
    success: bool = True,
    error_message: Optional[str] = None,
):
    """
    Update the suggestion record in Charm DB after push attempt.

    Args:
        suggestion_id: The Charm suggestion UUID
        emailbison_campaign_id: The campaign ID from EmailBison (if successful)
        success: Whether the push was successful
        error_message: Error message if push failed
    """
    logger = get_run_logger()
    logger.info(f"Updating suggestion {suggestion_id} push status")

    pool = await get_db_pool()

    try:
        async with pool.acquire() as conn:
            if success:
                # Mark as successfully pushed
                await conn.execute("""
                    UPDATE strategy_suggestions
                    SET pushed_to_emailbison = TRUE,
                        pushed_at = NOW()
                    WHERE id = $1
                """, suggestion_id)

                # If there's a strategy, update it with the campaign ID
                await conn.execute("""
                    UPDATE strategies
                    SET emailbison_campaign_id = $2,
                        status = 'active',
                        updated_at = NOW()
                    WHERE id = (
                        SELECT strategy_id FROM strategy_suggestions WHERE id = $1
                    )
                    AND emailbison_campaign_id IS NULL
                """, suggestion_id, emailbison_campaign_id)

                logger.info(f"Suggestion {suggestion_id} marked as pushed")
            else:
                # Log the error but don't mark as pushed
                logger.error(f"Push failed for suggestion {suggestion_id}: {error_message}")
                # Could add an error_message column to track failures

    finally:
        await pool.close()


@flow(name="push-to-emailbison", log_prints=True)
async def push_suggestion_to_emailbison(suggestion_id: str) -> dict:
    """
    Main flow: Push an approved suggestion to EmailBison.

    This flow:
    1. Fetches the suggestion content from Charm DB
    2. Creates a campaign in the client's EmailBison workspace
    3. Updates the suggestion record with the push status

    Args:
        suggestion_id: The UUID of the suggestion to push

    Returns:
        Dict with push results including the EmailBison campaign ID
    """
    logger = get_run_logger()
    logger.info(f"Starting push to EmailBison for suggestion {suggestion_id}")

    try:
        # Step 1: Fetch suggestion content
        content = await fetch_suggestion_content(suggestion_id)

        # Validate suggestion state
        if content["status"] != "approved":
            raise ValueError(f"Suggestion must be approved (current status: {content['status']})")

        if content["already_pushed"]:
            logger.warning(f"Suggestion {suggestion_id} was already pushed - skipping")
            return {
                "suggestion_id": suggestion_id,
                "status": "skipped",
                "message": "Already pushed to EmailBison",
            }

        if not content["workspace_id"]:
            raise ValueError(f"Client {content['client_name']} has no linked EmailBison workspace")

        # Step 2: Create campaign in EmailBison
        campaign_name = f"{content['client_name']} - {content['strategy_name'] or 'Campaign'}"
        campaign_result = await create_emailbison_campaign(
            workspace_id=content["workspace_id"],
            subject_line=content["subject_line"],
            email_body=content["email_body"],
            campaign_name=campaign_name,
            campaign_type=content["campaign_type"],
        )

        # Step 3: Update Charm DB
        await update_suggestion_pushed(
            suggestion_id=suggestion_id,
            emailbison_campaign_id=campaign_result["campaign_id"],
            success=True,
        )

        logger.info(f"Successfully pushed suggestion {suggestion_id} to EmailBison")
        return {
            "suggestion_id": suggestion_id,
            "client_name": content["client_name"],
            "workspace_id": content["workspace_id"],
            "emailbison_campaign_id": campaign_result["campaign_id"],
            "status": "success",
            "message": "Campaign created in EmailBison",
        }

    except Exception as e:
        logger.error(f"Failed to push suggestion {suggestion_id}: {str(e)}")
        # Update DB to record failure (optional)
        try:
            await update_suggestion_pushed(
                suggestion_id=suggestion_id,
                emailbison_campaign_id="",
                success=False,
                error_message=str(e),
            )
        except Exception:
            pass  # Don't fail on DB update error

        raise


# CLI entry point for testing
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Push campaign suggestion to EmailBison")
    parser.add_argument("--suggestion-id", required=True, help="UUID of the suggestion to push")
    args = parser.parse_args()

    result = asyncio.run(push_suggestion_to_emailbison(args.suggestion_id))
    print(f"Result: {result}")
