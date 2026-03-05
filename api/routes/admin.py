"""
Admin routes - Internal operations for development and debugging.

These endpoints are protected by an admin key and should NOT be exposed publicly.
"""

from fastapi import APIRouter, HTTPException, Query, Response
from fastapi.responses import StreamingResponse
import os
import io
import logging
import json
from datetime import datetime, date
from decimal import Decimal
from uuid import UUID

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


class SQLEncoder(json.JSONEncoder):
    """JSON encoder that handles UUID, datetime, Decimal."""
    def default(self, obj):
        if isinstance(obj, UUID):
            return str(obj)
        elif isinstance(obj, (datetime, date)):
            return obj.isoformat()
        elif isinstance(obj, Decimal):
            return float(obj)
        return super().default(obj)


def escape_sql_value(val):
    """Escape a value for SQL INSERT statement."""
    if val is None:
        return "NULL"
    elif isinstance(val, bool):
        return "TRUE" if val else "FALSE"
    elif isinstance(val, (int, float, Decimal)):
        return str(val)
    elif isinstance(val, (datetime, date)):
        return f"'{val.isoformat()}'"
    elif isinstance(val, UUID):
        return f"'{str(val)}'"
    elif isinstance(val, (dict, list)):
        # JSON fields - use custom encoder for nested UUIDs/dates
        json_str = json.dumps(val, cls=SQLEncoder).replace("'", "''")
        return f"'{json_str}'"
    else:
        # String - escape single quotes
        escaped = str(val).replace("'", "''")
        return f"'{escaped}'"


@router.get("/db-export")
async def export_database(
    key: str = Query(..., description="Admin key for authentication"),
    exclude_audit: bool = Query(True, description="Exclude large audit tables")
):
    """
    Export the database as SQL INSERT statements.

    Pure Python implementation - no pg_dump version issues.
    Protected by admin key.

    Usage (from local machine):
        curl "https://api.wizardgrimoire.cloud/api/admin/db-export?key=YOUR_ADMIN_KEY" > dump.sql

    Then restore locally:
        psql -h localhost -p 5433 -U postgres -d postgres -f dump.sql
    """
    if not verify_admin_key(key):
        raise HTTPException(status_code=403, detail="Invalid admin key")

    from database import fetch_all, get_pool

    # Tables to exclude
    excluded = {"sync_audit_log", "response_messages", "activity_log"} if exclude_audit else set()

    # Also exclude views and system tables
    excluded.add("pg_stat_statements")

    logger.info(f"Starting database export, exclude_audit={exclude_audit}")

    try:
        # Get all user tables in dependency order (foreign keys)
        tables = await fetch_all("""
            SELECT tablename
            FROM pg_tables
            WHERE schemaname = 'public'
            ORDER BY tablename
        """)

        table_names = [t["tablename"] for t in tables if t["tablename"] not in excluded]

        output = io.StringIO()
        output.write("-- Charm Email OS Database Export\n")
        output.write(f"-- Generated: {datetime.now().isoformat()}\n")
        output.write("-- Pure Python export with schema\n\n")

        # Disable triggers and foreign key checks during import
        output.write("SET session_replication_role = 'replica';\n")
        output.write("SET client_min_messages = 'warning';\n\n")

        # Export custom enum types
        enums = await fetch_all("""
            SELECT t.typname, string_agg(e.enumlabel, ',' ORDER BY e.enumsortorder) as labels
            FROM pg_type t
            JOIN pg_enum e ON t.oid = e.enumtypid
            JOIN pg_namespace n ON t.typnamespace = n.oid
            WHERE n.nspname = 'public'
            GROUP BY t.typname
        """)

        if enums:
            output.write("-- Custom enum types\n")
            for enum in enums:
                labels = ", ".join([f"'{l}'" for l in enum["labels"].split(",")])
                output.write(f"DROP TYPE IF EXISTS {enum['typname']} CASCADE;\n")
                output.write(f"CREATE TYPE {enum['typname']} AS ENUM ({labels});\n")
            output.write("\n")

        total_rows = 0

        for table in table_names:
            # Get column info with full type details
            cols = await fetch_all(f"""
                SELECT
                    c.column_name,
                    c.data_type,
                    c.udt_name,
                    c.is_nullable,
                    c.column_default,
                    c.character_maximum_length
                FROM information_schema.columns c
                WHERE c.table_name = '{table}' AND c.table_schema = 'public'
                ORDER BY c.ordinal_position
            """)

            if not cols:
                continue

            col_names = [c["column_name"] for c in cols]

            # Generate CREATE TABLE
            output.write(f"-- Table: {table}\n")
            output.write(f"DROP TABLE IF EXISTS {table} CASCADE;\n")

            col_defs = []
            for c in cols:
                col_type = c["udt_name"]
                # Map common types
                if col_type == "int4":
                    col_type = "INTEGER"
                elif col_type == "int8":
                    col_type = "BIGINT"
                elif col_type == "float8":
                    col_type = "DOUBLE PRECISION"
                elif col_type == "bool":
                    col_type = "BOOLEAN"
                elif col_type == "varchar" and c["character_maximum_length"]:
                    col_type = f"VARCHAR({c['character_maximum_length']})"
                elif col_type == "timestamptz":
                    col_type = "TIMESTAMP WITH TIME ZONE"
                elif col_type == "timestamp":
                    col_type = "TIMESTAMP"

                nullable = "" if c["is_nullable"] == "YES" else " NOT NULL"
                default = f" DEFAULT {c['column_default']}" if c["column_default"] else ""
                col_defs.append(f"    {c['column_name']} {col_type.upper()}{nullable}{default}")

            output.write(f"CREATE TABLE {table} (\n")
            output.write(",\n".join(col_defs))
            output.write("\n);\n\n")

            # Get all rows
            rows = await fetch_all(f"SELECT * FROM {table}")

            if rows:
                for row in rows:
                    values = [escape_sql_value(row[col]) for col in col_names]
                    output.write(f"INSERT INTO {table} ({', '.join(col_names)}) VALUES ({', '.join(values)});\n")
                total_rows += len(rows)
                output.write("\n")

        # Re-enable triggers
        output.write("SET session_replication_role = 'origin';\n")

        dump_data = output.getvalue().encode('utf-8')
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"charm_db_export_{timestamp}.sql"

        logger.info(f"Database export successful: {len(dump_data)} bytes, {total_rows} rows, {len(table_names)} tables")

        return Response(
            content=dump_data,
            media_type="application/sql",
            headers={
                "Content-Disposition": f"attachment; filename={filename}"
            }
        )

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
