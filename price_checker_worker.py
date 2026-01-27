"""
Price Checker Worker

Continuously checks domain prices in the background to work around
Porkbun's strict rate limiting (1 check per 10 seconds).

The worker cycles through domains that need price checks:
- Domains never checked (porkbun_price IS NULL)
- Domains with stale prices (last_price_check > 24 hours ago)

This ensures all domains eventually get Porkbun prices without
hitting rate limits.

Usage:
    python price_checker_worker.py

Environment variables:
    POSTGRES_HOST, POSTGRES_PORT, POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD
    PORKBUN_API_KEY, PORKBUN_API_SECRET
    DYNADOT_API_KEY
    CHECK_INTERVAL (default: 12 seconds - respects Porkbun's 10s limit)
    STALE_HOURS (default: 24 - hours before re-checking a domain)
"""

import os
import sys
import time
import asyncio
import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional

import psycopg2
from psycopg2.extras import RealDictCursor

# Add the api directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'api'))

from services.porkbun import PorkbunService
from services.dynadot import DynadotService

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Database configuration
DB_CONFIG = {
    "host": os.getenv("POSTGRES_HOST", "localhost"),
    "port": int(os.getenv("POSTGRES_PORT", "5432")),
    "database": os.getenv("POSTGRES_DB", "postgres"),
    "user": os.getenv("POSTGRES_USER", "postgres"),
    "password": os.getenv("POSTGRES_PASSWORD", ""),
}

# Worker configuration
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", "12"))  # 12s > 10s rate limit
STALE_HOURS = int(os.getenv("STALE_HOURS", "24"))  # Re-check after 24 hours


def get_db_connection():
    """Create a database connection."""
    return psycopg2.connect(**DB_CONFIG, cursor_factory=RealDictCursor)


def get_next_domain_to_check() -> Optional[dict]:
    """
    Get the next domain that needs a price check.

    Priority:
    1. Domains missing Porkbun price (porkbun_price IS NULL)
    2. Domains with stale prices (last_price_check > STALE_HOURS ago)

    Only checks domains in pending/approved status (not purchased/denied).
    """
    conn = get_db_connection()
    try:
        cur = conn.cursor()

        stale_threshold = datetime.utcnow() - timedelta(hours=STALE_HOURS)

        # Get domain needing check - prioritize missing Porkbun price, then stale
        cur.execute("""
            SELECT id, domain_name, workspace_id
            FROM domains
            WHERE approval_status IN ('pending', 'approved', 'pending_approval')
            AND (
                -- Missing Porkbun price (primary target - Porkbun is rate-limited)
                porkbun_price IS NULL
                OR
                -- Stale check (older than threshold)
                (last_price_check IS NOT NULL AND last_price_check < %s)
            )
            ORDER BY
                -- Missing Porkbun price first
                CASE WHEN porkbun_price IS NULL THEN 0 ELSE 1 END,
                -- Then oldest checks first
                last_price_check ASC NULLS FIRST
            LIMIT 1
        """, (stale_threshold,))

        row = cur.fetchone()
        return dict(row) if row else None

    finally:
        cur.close()
        conn.close()


def update_domain_prices(
    domain_id: str,
    porkbun_available: Optional[bool],
    porkbun_price: Optional[Decimal],
    dynadot_available: Optional[bool],
    dynadot_price: Optional[Decimal],
):
    """Update domain with price check results."""
    conn = get_db_connection()
    try:
        cur = conn.cursor()

        # Calculate best price
        best_price = None
        best_provider = None

        if porkbun_price is not None and dynadot_price is not None:
            if porkbun_price <= dynadot_price:
                best_price = porkbun_price
                best_provider = 'porkbun'
            else:
                best_price = dynadot_price
                best_provider = 'dynadot'
        elif porkbun_price is not None:
            best_price = porkbun_price
            best_provider = 'porkbun'
        elif dynadot_price is not None:
            best_price = dynadot_price
            best_provider = 'dynadot'

        cur.execute("""
            UPDATE domains
            SET
                porkbun_available = %s,
                porkbun_price = %s,
                dynadot_available = %s,
                dynadot_price = %s,
                cached_price = %s,
                selected_provider = %s,
                last_price_check = NOW(),
                updated_at = NOW()
            WHERE id = %s
        """, (
            porkbun_available,
            float(porkbun_price) if porkbun_price else None,
            dynadot_available,
            float(dynadot_price) if dynadot_price else None,
            float(best_price) if best_price else None,
            best_provider,
            domain_id,
        ))

        conn.commit()

    except Exception as e:
        logger.error(f"Failed to update domain prices: {e}")
        conn.rollback()
    finally:
        cur.close()
        conn.close()


def mark_domain_unavailable(domain_id: str):
    """Mark a domain as unavailable (auto-deny if both providers say unavailable)."""
    conn = get_db_connection()
    try:
        cur = conn.cursor()

        # Check if both providers show unavailable
        cur.execute("""
            SELECT porkbun_available, dynadot_available
            FROM domains
            WHERE id = %s
        """, (domain_id,))

        row = cur.fetchone()
        if row:
            pb_avail = row.get('porkbun_available')
            dd_avail = row.get('dynadot_available')

            # If both checked and both unavailable, auto-deny
            if pb_avail is False and dd_avail is False:
                cur.execute("""
                    UPDATE domains
                    SET approval_status = 'denied',
                        updated_at = NOW()
                    WHERE id = %s
                    AND approval_status IN ('pending', 'approved', 'pending_approval')
                """, (domain_id,))
                conn.commit()
                logger.info(f"Auto-denied unavailable domain {domain_id}")
                return True

        return False

    except Exception as e:
        logger.error(f"Failed to check/deny domain: {e}")
        conn.rollback()
        return False
    finally:
        cur.close()
        conn.close()


async def check_domain_price(domain_name: str) -> tuple:
    """
    Check prices for a domain from both providers.

    Returns:
        Tuple of (porkbun_available, porkbun_price, dynadot_available, dynadot_price)
    """
    porkbun_available = None
    porkbun_price = None
    dynadot_available = None
    dynadot_price = None

    # Check Porkbun
    try:
        async with PorkbunService() as porkbun:
            result = await porkbun.check_availability(domain_name)
            porkbun_available = result.available
            if result.available and result.price is not None:
                porkbun_price = result.price
            logger.debug(f"Porkbun {domain_name}: available={result.available}, price={result.price}")
    except Exception as e:
        logger.warning(f"Porkbun check failed for {domain_name}: {e}")

    # Check Dynadot (no strict rate limit, can check immediately)
    try:
        async with DynadotService() as dynadot:
            result = await dynadot.check_availability(domain_name)
            dynadot_available = result.available
            if result.available and result.price is not None:
                dynadot_price = result.price
            logger.debug(f"Dynadot {domain_name}: available={result.available}, price={result.price}")
    except Exception as e:
        logger.warning(f"Dynadot check failed for {domain_name}: {e}")

    return porkbun_available, porkbun_price, dynadot_available, dynadot_price


async def process_one_domain():
    """Process a single domain price check."""
    domain = get_next_domain_to_check()

    if not domain:
        logger.debug("No domains need price checking")
        return False

    domain_id = str(domain['id'])
    domain_name = domain['domain_name']

    logger.info(f"Checking prices for: {domain_name}")

    # Check prices
    pb_avail, pb_price, dd_avail, dd_price = await check_domain_price(domain_name)

    # Update database
    update_domain_prices(
        domain_id=domain_id,
        porkbun_available=pb_avail,
        porkbun_price=pb_price,
        dynadot_available=dd_avail,
        dynadot_price=dd_price,
    )

    # Log result
    pb_str = f"${pb_price}" if pb_price else ("N/A" if pb_avail is False else "error")
    dd_str = f"${dd_price}" if dd_price else ("N/A" if dd_avail is False else "error")
    logger.info(f"  {domain_name}: PB={pb_str}, DD={dd_str}")

    # Auto-deny if unavailable everywhere
    if pb_avail is False and dd_avail is False:
        mark_domain_unavailable(domain_id)

    return True


async def run_worker():
    """Main worker loop."""
    logger.info("=" * 60)
    logger.info("Price Checker Worker starting")
    logger.info(f"Check interval: {CHECK_INTERVAL}s")
    logger.info(f"Stale threshold: {STALE_HOURS}h")
    logger.info("=" * 60)

    # Verify API credentials are configured
    if not os.getenv("PORKBUN_API_KEY"):
        logger.warning("PORKBUN_API_KEY not set - Porkbun checks will fail")
    if not os.getenv("DYNADOT_API_KEY"):
        logger.warning("DYNADOT_API_KEY not set - Dynadot checks will fail")

    consecutive_empty = 0

    while True:
        try:
            processed = await process_one_domain()

            if processed:
                consecutive_empty = 0
            else:
                consecutive_empty += 1
                # If no work for a while, log less frequently
                if consecutive_empty % 10 == 0:
                    logger.info(f"No domains to check (idle for {consecutive_empty * CHECK_INTERVAL}s)")

            # Sleep to respect rate limits
            await asyncio.sleep(CHECK_INTERVAL)

        except KeyboardInterrupt:
            logger.info("Shutting down...")
            break

        except Exception as e:
            logger.error(f"Worker error: {e}")
            await asyncio.sleep(CHECK_INTERVAL)


def main():
    """Entry point."""
    try:
        asyncio.run(run_worker())
    except KeyboardInterrupt:
        logger.info("Worker stopped")


if __name__ == "__main__":
    main()
