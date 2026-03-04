"""
Activity logging helper for audit trail.

Usage in routes:
    from deps.user import get_current_user, CurrentUser
    from deps.activity import log_activity

    @router.post("/bulk-purchase")
    async def bulk_purchase(
        request: BulkPurchaseRequest,
        user: CurrentUser = Depends(get_current_user),
    ):
        # ... do purchase ...

        await log_activity(
            user=user,
            action="domain_purchased",
            resource_type="domain",
            resource_id=str(domain_id),
            details={"domain_name": domain.name, "registrar": "porkbun", "price": 12.99}
        )
"""

from typing import Optional
from .user import CurrentUser
import json
import logging

# Import from parent directory
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database import execute

logger = logging.getLogger(__name__)


async def log_activity(
    user: CurrentUser,
    action: str,
    resource_type: Optional[str] = None,
    resource_id: Optional[str] = None,
    details: Optional[dict] = None,
) -> None:
    """
    Log a user activity to the activity_log table.

    Args:
        user: CurrentUser from get_current_user dependency
        action: Action name (e.g., 'domain_purchased', 'hypertide_order_created')
        resource_type: Type of resource affected (e.g., 'domain', 'client')
        resource_id: ID of the affected resource
        details: Additional context as dict (stored as JSONB)

    This function gracefully handles failures - it will log warnings but
    never raise exceptions that would interrupt the main request flow.
    """
    if not user.email:
        # Anonymous action - still log but with 'anonymous' user
        logger.info(f"Logging anonymous activity: {action}")

    try:
        await execute("""
            INSERT INTO activity_log (
                user_id, user_email, action, resource_type, resource_id,
                details, ip_address, user_agent
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        """,
            user.id,
            user.email or 'anonymous',
            action,
            resource_type,
            resource_id,
            json.dumps(details) if details else None,
            user.ip_address,
            user.user_agent,
        )
        logger.info(f"Activity logged: {action} by {user.email or 'anonymous'}")
    except Exception as e:
        # Don't fail the request if logging fails
        logger.error(f"Failed to log activity '{action}': {e}")
