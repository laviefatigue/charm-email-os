"""
Rate limiting dependency for FastAPI.

Simple in-memory rate limiter for critical endpoints.
For production at scale, consider using Redis-backed rate limiting.

Usage:
    from deps.rate_limit import rate_limit, RateLimitConfig

    @router.post("/bulk-purchase")
    async def bulk_purchase(
        request: BulkPurchaseRequest,
        _: None = Depends(rate_limit(RateLimitConfig(requests=5, window_seconds=60))),
    ):
        ...
"""

from fastapi import Request, HTTPException
from typing import Dict, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)

# In-memory store for rate limiting
# Key: (client_identifier, endpoint) -> (request_count, window_start)
_rate_limit_store: Dict[str, Tuple[int, datetime]] = {}


@dataclass
class RateLimitConfig:
    """Rate limit configuration."""
    requests: int = 10  # Max requests per window
    window_seconds: int = 60  # Window size in seconds


def _get_client_identifier(request: Request) -> str:
    """Get a unique identifier for the client."""
    # Use X-User-Email if available (authenticated user)
    user_email = request.headers.get("X-User-Email")
    if user_email:
        return f"user:{user_email}"

    # Fall back to IP address
    forwarded_for = request.headers.get("X-Forwarded-For", "")
    if forwarded_for:
        return f"ip:{forwarded_for.split(',')[0].strip()}"

    return f"ip:{request.client.host if request.client else 'unknown'}"


def _cleanup_expired_entries(window_seconds: int):
    """Remove expired entries from the store."""
    now = datetime.now()
    expired_keys = [
        key for key, (_, window_start) in _rate_limit_store.items()
        if now - window_start > timedelta(seconds=window_seconds * 2)
    ]
    for key in expired_keys:
        del _rate_limit_store[key]


def rate_limit(config: RateLimitConfig = RateLimitConfig()):
    """
    Rate limiting dependency factory.

    Returns a dependency that enforces rate limits.
    """
    async def _rate_limit_dependency(request: Request) -> None:
        client_id = _get_client_identifier(request)
        endpoint = request.url.path
        key = f"{client_id}:{endpoint}"

        now = datetime.now()

        # Cleanup occasionally (every ~100 requests)
        if len(_rate_limit_store) > 100:
            _cleanup_expired_entries(config.window_seconds)

        # Check current rate
        if key in _rate_limit_store:
            count, window_start = _rate_limit_store[key]

            # Check if window has expired
            if now - window_start > timedelta(seconds=config.window_seconds):
                # Reset window
                _rate_limit_store[key] = (1, now)
            elif count >= config.requests:
                # Rate limit exceeded
                retry_after = config.window_seconds - (now - window_start).seconds
                logger.warning(f"Rate limit exceeded for {client_id} on {endpoint}")
                raise HTTPException(
                    status_code=429,
                    detail=f"Rate limit exceeded. Try again in {retry_after} seconds.",
                    headers={"Retry-After": str(retry_after)}
                )
            else:
                # Increment count
                _rate_limit_store[key] = (count + 1, window_start)
        else:
            # First request in window
            _rate_limit_store[key] = (1, now)

    return _rate_limit_dependency
