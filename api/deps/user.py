"""
User dependency for extracting user email from frontend requests.

The frontend (behind Cloudflare Access) passes the authenticated user's email
via the X-User-Email header. The API trusts this header because:
1. Frontend is behind Cloudflare Access (only @hirecharm.com can access)
2. API is only accessible via Cloudflare tunnel (no direct access)

SECURITY NOTES:
- X-User-Email header is validated to be @hirecharm.com domain
- Origin header is checked against allowed frontends
- For activity logging, we also capture IP and User-Agent.
"""

from fastapi import Header, Request
from typing import Optional
from pydantic import BaseModel
from uuid import UUID
import logging
import re

# Import from parent directory
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database import fetch_one, execute

logger = logging.getLogger(__name__)

# Allowed email domains for authenticated users
ALLOWED_EMAIL_DOMAINS = ["hirecharm.com"]

# Allowed origins for API requests (checked if Origin header present)
ALLOWED_ORIGINS = [
    "https://app.wizardgrimoire.cloud",
    "https://dashboard.wizardgrimoire.cloud",
    "http://localhost:3000",
    "http://localhost:8000",
]


class CurrentUser(BaseModel):
    """Current authenticated user context"""
    id: Optional[UUID] = None
    email: Optional[str] = None
    display_name: Optional[str] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None

    class Config:
        from_attributes = True


async def get_current_user(
    request: Request,
    x_user_email: Optional[str] = Header(None, alias="X-User-Email"),
) -> CurrentUser:
    """
    Extract current user from request headers.

    Headers:
    - X-User-Email: Set by frontend from CF-Access-Authenticated-User-Email

    SECURITY:
    - Validates email domain is in ALLOWED_EMAIL_DOMAINS
    - Optionally validates Origin header
    - Auto-creates user records on first seen (upsert pattern).
    """
    if not x_user_email:
        return CurrentUser()

    # SECURITY: Validate email domain
    email_domain = x_user_email.split('@')[-1].lower() if '@' in x_user_email else None
    if not email_domain or email_domain not in ALLOWED_EMAIL_DOMAINS:
        logger.warning(f"Rejected X-User-Email with invalid domain: {x_user_email}")
        return CurrentUser()  # Return unauthenticated user

    # SECURITY: Validate Origin header if present (browser requests)
    origin = request.headers.get("Origin")
    if origin and origin not in ALLOWED_ORIGINS:
        logger.warning(f"Rejected request from unauthorized origin: {origin}")
        return CurrentUser()  # Return unauthenticated user

    # Get IP and User-Agent for logging
    # X-Forwarded-For may contain multiple IPs; take the first one
    forwarded_for = request.headers.get("X-Forwarded-For", "")
    ip_address = forwarded_for.split(",")[0].strip() if forwarded_for else (
        request.client.host if request.client else None
    )
    user_agent = request.headers.get("User-Agent")

    # Derive display name from email
    name_part = x_user_email.split('@')[0]
    display_name = ' '.join(
        word.capitalize()
        for word in name_part.replace('.', ' ').replace('_', ' ').replace('-', ' ').split()
    )

    try:
        # Upsert user record (create if not exists, update last_seen if exists)
        user_row = await fetch_one("""
            INSERT INTO users (email, display_name)
            VALUES ($1, $2)
            ON CONFLICT (email) DO UPDATE SET
                last_seen_at = NOW(),
                display_name = COALESCE(users.display_name, EXCLUDED.display_name)
            RETURNING id, email, display_name
        """, x_user_email, display_name)

        if user_row:
            return CurrentUser(
                id=user_row["id"],
                email=user_row["email"],
                display_name=user_row["display_name"],
                ip_address=ip_address,
                user_agent=user_agent,
            )
    except Exception as e:
        # Log but don't fail the request if user tracking fails
        logger.warning(f"Failed to upsert user record for {x_user_email}: {e}")

    # Return basic user info even if DB upsert failed
    return CurrentUser(
        email=x_user_email,
        display_name=display_name,
        ip_address=ip_address,
        user_agent=user_agent,
    )
