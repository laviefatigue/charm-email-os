"""
Admin routes - Internal operations for development and debugging.

These endpoints are protected by an admin key and should NOT be exposed publicly.
"""

from fastapi import APIRouter, HTTPException, Query, Response
from fastapi.responses import StreamingResponse
import subprocess
import os
import io
import logging
from datetime import datetime

router = APIRouter()
logger = logging.getLogger(__name__)

# Admin key for protected endpoints (set via environment variable)
ADMIN_KEY = os.getenv("ADMIN_KEY", "")


def verify_admin_key(key: str) -> bool:
    """Verify the admin key matches."""
    if not ADMIN_KEY:
        # If no admin key is set, allow in development mode
        return os.getenv("DEBUG", "false").lower() == "true"
    return key == ADMIN_KEY


@router.get("/db-export")
async def export_database(
    key: str = Query(..., description="Admin key for authentication"),
    exclude_audit: bool = Query(True, description="Exclude large audit tables")
):
    """
    Export the database as a SQL dump.

    This endpoint runs pg_dump and streams the result.
    Protected by admin key.

    Usage (from local machine):
        curl "https://api.wizardgrimoire.cloud/api/admin/db-export?key=YOUR_ADMIN_KEY" > dump.sql

    Then restore locally:
        psql -h localhost -p 5433 -U postgres -d postgres -f dump.sql
    """
    if not verify_admin_key(key):
        raise HTTPException(status_code=403, detail="Invalid admin key")

    # Build pg_dump command
    pg_host = os.getenv("POSTGRES_HOST", "localhost")
    pg_port = os.getenv("POSTGRES_PORT", "5432")
    pg_db = os.getenv("POSTGRES_DB", "postgres")
    pg_user = os.getenv("POSTGRES_USER", "postgres")
    pg_password = os.getenv("POSTGRES_PASSWORD", "")

    # Build exclusions
    exclude_tables = []
    if exclude_audit:
        exclude_tables = [
            "--exclude-table=sync_audit_log",
            "--exclude-table=response_messages",
            "--exclude-table=activity_log",
        ]

    cmd = [
        "pg_dump",
        f"--host={pg_host}",
        f"--port={pg_port}",
        f"--username={pg_user}",
        f"--dbname={pg_db}",
        "--no-owner",
        "--no-privileges",
        "--clean",
        "--if-exists",
    ] + exclude_tables

    logger.info(f"Running pg_dump: host={pg_host}, db={pg_db}, exclude_audit={exclude_audit}")

    try:
        # Set password via environment
        env = os.environ.copy()
        env["PGPASSWORD"] = pg_password

        # Run pg_dump
        result = subprocess.run(
            cmd,
            capture_output=True,
            env=env,
            timeout=300  # 5 minute timeout
        )

        if result.returncode != 0:
            error_msg = result.stderr.decode("utf-8")
            logger.error(f"pg_dump failed: {error_msg}")
            raise HTTPException(status_code=500, detail=f"pg_dump failed: {error_msg}")

        # Return as downloadable file
        dump_data = result.stdout
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"charm_db_export_{timestamp}.sql"

        logger.info(f"Database export successful: {len(dump_data)} bytes")

        return Response(
            content=dump_data,
            media_type="application/sql",
            headers={
                "Content-Disposition": f"attachment; filename={filename}"
            }
        )

    except subprocess.TimeoutExpired:
        logger.error("pg_dump timed out after 5 minutes")
        raise HTTPException(status_code=504, detail="Database export timed out")
    except Exception as e:
        logger.error(f"Database export failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/db-tables")
async def list_tables(
    key: str = Query(..., description="Admin key for authentication")
):
    """
    List all tables with row counts.
    Useful for verifying sync completeness.
    """
    if not verify_admin_key(key):
        raise HTTPException(status_code=403, detail="Invalid admin key")

    from database import fetch_all

    rows = await fetch_all("""
        SELECT
            schemaname,
            relname as table_name,
            n_tup_ins as rows_inserted,
            n_live_tup as row_count
        FROM pg_stat_user_tables
        ORDER BY n_live_tup DESC
    """)

    return {
        "tables": [dict(r) for r in rows],
        "total_tables": len(rows)
    }
