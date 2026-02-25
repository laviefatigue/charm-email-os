#!/usr/bin/env python3
"""
Create a test strategy generation job for local validation.

This script creates a job in the production database that the strategy worker
will pick up and process. Output is saved locally when worker runs in LOCAL_MODE.

Uses Charm client data by default.

Usage:
    python scripts/test_strategy_generation.py
    python scripts/test_strategy_generation.py --client-id <uuid>
"""
import argparse
import json
import os
import uuid
from pathlib import Path
from datetime import datetime

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
except ImportError:
    print("psycopg2 not installed. Run: pip install psycopg2-binary")
    exit(1)

# Default client IDs for testing
CHARM_CLIENT_ID = "4bd07dc0-059a-448b-b6f4-3275d0c104a9"

# Database configuration (same as worker uses)
DB_CONFIG = {
    "host": os.getenv("POSTGRES_HOST", "31.97.142.123"),
    "port": int(os.getenv("POSTGRES_PORT", "5432")),
    "database": os.getenv("POSTGRES_DB", "postgres"),
    "user": os.getenv("POSTGRES_USER", "postgres"),
    "password": os.getenv("POSTGRES_PASSWORD", "ZEN3hMv6UpA0hfd8OcAUSiJWgpY33q5V"),
}

# Paths
SCRIPTS_DIR = Path(__file__).parent
PROJECT_DIR = SCRIPTS_DIR.parent
OUTPUT_DIR = PROJECT_DIR / "test-output"


def get_db():
    """Get database connection."""
    return psycopg2.connect(**DB_CONFIG)


def create_test_job(client_id: str = CHARM_CLIENT_ID, description: str = None) -> str:
    """Create a new test job in the production database."""
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    job_id = str(uuid.uuid4())

    try:
        # Insert job into production database
        cur.execute("""
            INSERT INTO strategy_generation_jobs
            (id, client_id, status, generation_round, created_at)
            VALUES (%s, %s, 'pending', 1, NOW())
            RETURNING id, created_at
        """, (job_id, client_id))

        result = cur.fetchone()
        conn.commit()

        # Create local output directory
        job_dir = OUTPUT_DIR / "jobs" / job_id
        job_dir.mkdir(parents=True, exist_ok=True)

        # Write local metadata
        metadata = {
            "job_id": job_id,
            "client_id": client_id,
            "description": description or "Test strategy generation (local mode)",
            "status": "pending",
            "created_at": str(result["created_at"])
        }
        with open(job_dir / "metadata.json", "w") as f:
            json.dump(metadata, f, indent=2)

        print(f"\n{'='*60}")
        print("TEST JOB CREATED")
        print(f"{'='*60}")
        print(f"Job ID:         {job_id}")
        print(f"Client:         {client_id}")
        print(f"Database:       {DB_CONFIG['host']}:{DB_CONFIG['port']}")
        print(f"Local output:   {job_dir}")
        print(f"{'='*60}")
        print("\nNext steps:")
        print("1. Start the worker (if not running):")
        print("   docker compose -f docker-compose.strategy-local.yml up -d")
        print("\n2. Monitor logs:")
        print("   docker logs -f charm-strategy-test")
        print("\n3. After completion, validate output:")
        print("   python scripts/validate_output.py")
        print(f"{'='*60}\n")

        return job_id

    except Exception as e:
        conn.rollback()
        print(f"Error creating job: {e}")
        raise
    finally:
        cur.close()
        conn.close()


def list_jobs(client_id: str = None):
    """List recent strategy generation jobs."""
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    try:
        if client_id:
            cur.execute("""
                SELECT id, client_id, status, created_at, completed_at
                FROM strategy_generation_jobs
                WHERE client_id = %s
                ORDER BY created_at DESC
                LIMIT 10
            """, (client_id,))
        else:
            cur.execute("""
                SELECT id, client_id, status, created_at, completed_at
                FROM strategy_generation_jobs
                ORDER BY created_at DESC
                LIMIT 10
            """)

        jobs = cur.fetchall()

        if not jobs:
            print("No jobs found.")
            return

        print(f"\n{'='*90}")
        print("RECENT STRATEGY GENERATION JOBS")
        print(f"{'='*90}")
        print(f"{'ID':<38} {'Status':<12} {'Created':<20}")
        print(f"{'-'*90}")
        for job in jobs:
            created = str(job['created_at'])[:19] if job['created_at'] else 'N/A'
            print(f"{job['id']:<38} {job['status']:<12} {created:<20}")
        print(f"{'='*90}\n")

    finally:
        cur.close()
        conn.close()


def main():
    parser = argparse.ArgumentParser(description="Create test strategy generation jobs")
    parser.add_argument("--client-id", "-c", default=CHARM_CLIENT_ID,
                        help=f"Client UUID (default: Charm {CHARM_CLIENT_ID[:8]}...)")
    parser.add_argument("--description", "-d", help="Job description")
    parser.add_argument("--list", "-l", action="store_true", help="List recent jobs")

    args = parser.parse_args()

    if args.list:
        list_jobs()
    else:
        create_test_job(args.client_id, args.description)


if __name__ == "__main__":
    main()
