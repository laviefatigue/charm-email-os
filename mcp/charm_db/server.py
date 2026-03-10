#!/usr/bin/env python3
"""
Charm DB MCP Server - Direct production database queries.

Provides read-only access to the Charm Email OS production database
for inventory status, capacity analysis, and ad-hoc queries.

Setup:
    1. Enable public access on postgres in Coolify (temporarily)
    2. Add to .mcp.json with connection details
    3. Restart Claude Code
    4. Disable public access when done (or keep for ongoing use)

Tools:
    - query_inventory: Get inventory_pool_status by workspace
    - query_capacity: Get v_client_capacity data
    - query_domains: Get domain allocation status
    - query_sql: Run arbitrary SELECT queries
"""
import os
import json
import asyncio
from typing import Any, Sequence
from datetime import datetime, date
from decimal import Decimal
from uuid import UUID

import asyncpg

try:
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import Tool, TextContent
except ImportError:
    print("ERROR: MCP SDK not installed. Run: pip install mcp")
    exit(1)

# Database config from environment
POSTGRES_HOST = os.getenv('CHARM_DB_HOST', 'localhost')
POSTGRES_PORT = int(os.getenv('CHARM_DB_PORT', 5432))
POSTGRES_USER = os.getenv('CHARM_DB_USER', 'charm')
POSTGRES_PASSWORD = os.getenv('CHARM_DB_PASSWORD', '')
POSTGRES_DB = os.getenv('CHARM_DB_NAME', 'postgres')

server = Server("charm-db")

# JSON encoder for database types
def json_serial(obj):
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, UUID):
        return str(obj)
    raise TypeError(f"Type {type(obj)} not serializable")


async def get_connection():
    """Get a database connection."""
    return await asyncpg.connect(
        host=POSTGRES_HOST,
        port=POSTGRES_PORT,
        user=POSTGRES_USER,
        password=POSTGRES_PASSWORD,
        database=POSTGRES_DB
    )


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="query_inventory",
            description="Get inventory_pool_status distribution for a workspace. Shows reserve vs deployed counts by provider type.",
            inputSchema={
                "type": "object",
                "properties": {
                    "workspace_name": {
                        "type": "string",
                        "description": "Workspace name (e.g., 'Selery', 'Search Atlas')"
                    }
                },
                "required": ["workspace_name"]
            }
        ),
        Tool(
            name="query_capacity",
            description="Get client capacity data from v_client_capacity view. Shows targets, live counts, reserve counts, and gaps.",
            inputSchema={
                "type": "object",
                "properties": {
                    "client_name": {
                        "type": "string",
                        "description": "Client name (e.g., 'Selery')"
                    }
                },
                "required": ["client_name"]
            }
        ),
        Tool(
            name="query_domains",
            description="Get domain-level allocation status for a workspace. Shows which domains are reserve vs live.",
            inputSchema={
                "type": "object",
                "properties": {
                    "workspace_name": {
                        "type": "string",
                        "description": "Workspace name"
                    }
                },
                "required": ["workspace_name"]
            }
        ),
        Tool(
            name="query_sql",
            description="Run a read-only SQL query against the production database. SELECT queries only.",
            inputSchema={
                "type": "object",
                "properties": {
                    "sql": {
                        "type": "string",
                        "description": "SQL SELECT query"
                    }
                },
                "required": ["sql"]
            }
        ),
        Tool(
            name="apply_allocation",
            description="Apply domain allocation for a workspace. Sets inventory_pool_status based on capacity and health scoring.",
            inputSchema={
                "type": "object",
                "properties": {
                    "workspace_name": {
                        "type": "string",
                        "description": "Workspace name to allocate"
                    },
                    "dry_run": {
                        "type": "boolean",
                        "description": "If true, only show what would change without applying",
                        "default": True
                    }
                },
                "required": ["workspace_name"]
            }
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> Sequence[TextContent]:
    conn = await get_connection()

    try:
        if name == "query_inventory":
            workspace = arguments["workspace_name"]
            rows = await conn.fetch("""
                SELECT
                    CASE WHEN sa.esp = 'microsoft' THEN 'entra' ELSE 'google' END as provider,
                    sa.inventory_pool_status,
                    COUNT(*) as inbox_count,
                    COUNT(DISTINCT d.id) as domain_count
                FROM sender_accounts sa
                JOIN domains d ON sa.domain_id = d.id
                JOIN workspaces w ON d.workspace_id = w.id
                WHERE w.workspace_name = $1
                  AND sa.inbox_state = 'live'
                  AND sa.is_active = TRUE
                GROUP BY 1, 2
                ORDER BY 1, 2
            """, workspace)

            result = {
                "workspace": workspace,
                "allocation": [dict(r) for r in rows],
                "summary": {}
            }

            # Calculate summary
            for r in rows:
                provider = r['provider']
                status = r['inventory_pool_status'] or 'unset'
                if provider not in result["summary"]:
                    result["summary"][provider] = {"total": 0}
                result["summary"][provider][status] = r['inbox_count']
                result["summary"][provider]["total"] += r['inbox_count']

            return [TextContent(type="text", text=json.dumps(result, indent=2, default=json_serial))]

        elif name == "query_capacity":
            client = arguments["client_name"]
            row = await conn.fetchrow("""
                SELECT
                    client_name,
                    workspace_id,
                    entra_inboxes_target,
                    entra_inboxes_live,
                    entra_inboxes_reserve,
                    (entra_inboxes_live - entra_inboxes_target) as entra_surplus,
                    google_inboxes_target,
                    google_inboxes_live,
                    google_inboxes_reserve,
                    (google_inboxes_live - google_inboxes_target) as google_surplus,
                    target_buffer_ratio
                FROM v_client_capacity
                WHERE client_name = $1
            """, client)

            if row:
                result = dict(row)
                # Calculate expected reserve capacity
                spare = float(result.get('target_buffer_ratio') or 0.15)
                result['entra_reserve_capacity'] = min(
                    int((result.get('entra_inboxes_target') or 0) * spare),
                    max(0, result.get('entra_surplus') or 0)
                )
                result['google_reserve_capacity'] = min(
                    int((result.get('google_inboxes_target') or 0) * spare),
                    max(0, result.get('google_surplus') or 0)
                )
                return [TextContent(type="text", text=json.dumps(result, indent=2, default=json_serial))]
            return [TextContent(type="text", text=json.dumps({"error": f"No capacity data for {client}"}))]

        elif name == "query_domains":
            workspace = arguments["workspace_name"]
            rows = await conn.fetch("""
                SELECT
                    d.domain_name,
                    CASE WHEN sa.esp = 'microsoft' THEN 'entra' ELSE 'google' END as provider,
                    sa.inventory_pool_status,
                    COUNT(*) as inbox_count,
                    ROUND(AVG(sa.health_score)::numeric, 1) as avg_health
                FROM sender_accounts sa
                JOIN domains d ON sa.domain_id = d.id
                JOIN workspaces w ON d.workspace_id = w.id
                WHERE w.workspace_name = $1
                  AND sa.inbox_state = 'live'
                  AND sa.is_active = TRUE
                GROUP BY d.domain_name, sa.esp, sa.inventory_pool_status
                ORDER BY sa.inventory_pool_status NULLS LAST, provider, avg_health DESC
            """, workspace)

            result = {
                "workspace": workspace,
                "domains": [dict(r) for r in rows],
                "total_domains": len(set(r['domain_name'] for r in rows))
            }
            return [TextContent(type="text", text=json.dumps(result, indent=2, default=json_serial))]

        elif name == "query_sql":
            sql = arguments["sql"].strip()

            # Safety: only allow SELECT
            if not sql.upper().startswith("SELECT"):
                return [TextContent(type="text", text=json.dumps({"error": "Only SELECT queries allowed"}))]

            # Safety: block dangerous patterns
            dangerous = ['DROP', 'DELETE', 'TRUNCATE', 'UPDATE', 'INSERT', 'ALTER', 'CREATE', 'GRANT']
            sql_upper = sql.upper()
            for d in dangerous:
                if d in sql_upper:
                    return [TextContent(type="text", text=json.dumps({"error": f"Query contains blocked keyword: {d}"}))]

            rows = await conn.fetch(sql)
            result = [dict(r) for r in rows]
            return [TextContent(type="text", text=json.dumps(result, indent=2, default=json_serial))]

        elif name == "apply_allocation":
            workspace = arguments["workspace_name"]
            dry_run = arguments.get("dry_run", True)

            # Get capacity data
            capacity = await conn.fetchrow("""
                SELECT
                    cc.workspace_id,
                    COALESCE(cc.entra_inboxes_target, 0) as entra_target,
                    COALESCE(cc.entra_inboxes_live, 0) as entra_live,
                    COALESCE(cc.google_inboxes_target, 0) as google_target,
                    COALESCE(cc.google_inboxes_live, 0) as google_live,
                    COALESCE(cc.target_buffer_ratio, 0.15) as spare_ratio
                FROM v_client_capacity cc
                JOIN workspaces w ON cc.workspace_id = w.id
                WHERE w.workspace_name = $1
            """, workspace)

            if not capacity:
                return [TextContent(type="text", text=json.dumps({"error": f"No capacity data for {workspace}"}))]

            workspace_id = capacity['workspace_id']
            spare_ratio = float(capacity['spare_ratio'])

            # Calculate reserve capacity
            entra_surplus = capacity['entra_live'] - capacity['entra_target']
            google_surplus = capacity['google_live'] - capacity['google_target']
            entra_reserve_cap = min(int(capacity['entra_target'] * spare_ratio), max(0, entra_surplus))
            google_reserve_cap = min(int(capacity['google_target'] * spare_ratio), max(0, google_surplus))

            # Get domains with health scoring
            domains = await conn.fetch("""
                WITH domain_metrics AS (
                    SELECT
                        d.id as domain_id,
                        d.domain_name,
                        CASE WHEN sa.esp = 'microsoft' THEN 'entra' ELSE 'google' END as provider,
                        COUNT(sa.id) as inbox_count,
                        100.0
                            - CASE WHEN BOOL_OR(sa.kill_trigger::text = 'spam_complaint') THEN 200 ELSE 0 END
                            - CASE WHEN BOOL_OR(sa.kill_trigger::text LIKE 'provider_block%') THEN 100 ELSE 0 END
                            - (AVG(COALESCE(sa.bounce_rate_7d, 0)) * 500)
                            + ((AVG(sa.health_score) - 80) * 2)
                        AS score
                    FROM domains d
                    JOIN sender_accounts sa ON sa.domain_id = d.id
                    WHERE d.workspace_id = $1
                      AND d.is_active = TRUE
                      AND sa.inbox_state = 'live'
                      AND sa.is_active = TRUE
                    GROUP BY d.id, d.domain_name, sa.esp
                )
                SELECT * FROM domain_metrics WHERE inbox_count > 0
                ORDER BY provider, score DESC
            """, workspace_id)

            # Allocate domains
            entra_domains = [d for d in domains if d['provider'] == 'entra']
            google_domains = [d for d in domains if d['provider'] == 'google']

            def select_reserve(doms, cap):
                reserve, live = [], []
                reserve_count = 0
                for d in doms:
                    if reserve_count < cap:
                        reserve.append(d)
                        reserve_count += d['inbox_count']
                    else:
                        live.append(d)
                return reserve, live

            entra_reserve, entra_live = select_reserve(entra_domains, entra_reserve_cap)
            google_reserve, google_live = select_reserve(google_domains, google_reserve_cap)

            reserve_domains = entra_reserve + google_reserve
            live_domains = entra_live + google_live

            result = {
                "workspace": workspace,
                "dry_run": dry_run,
                "capacity": {
                    "entra_reserve_cap": entra_reserve_cap,
                    "google_reserve_cap": google_reserve_cap,
                    "entra_surplus": entra_surplus,
                    "google_surplus": google_surplus
                },
                "allocation": {
                    "reserve_domains": len(reserve_domains),
                    "reserve_inboxes": sum(d['inbox_count'] for d in reserve_domains),
                    "live_domains": len(live_domains),
                    "live_inboxes": sum(d['inbox_count'] for d in live_domains)
                },
                "reserve_domain_list": [
                    {"domain": d['domain_name'], "provider": d['provider'], "inboxes": d['inbox_count'], "score": round(d['score'], 1)}
                    for d in reserve_domains
                ]
            }

            if not dry_run:
                # Apply allocation
                reserve_ids = [d['domain_id'] for d in reserve_domains]
                live_ids = [d['domain_id'] for d in live_domains]

                # Update reserve
                if reserve_ids:
                    await conn.execute("""
                        UPDATE sender_accounts
                        SET inventory_pool_status = 'reserve', updated_at = NOW()
                        WHERE domain_id = ANY($1::uuid[])
                          AND inbox_state = 'live' AND is_active = TRUE
                    """, reserve_ids)

                # Update live
                if live_ids:
                    await conn.execute("""
                        UPDATE sender_accounts
                        SET inventory_pool_status = 'deployed', updated_at = NOW()
                        WHERE domain_id = ANY($1::uuid[])
                          AND inbox_state = 'live' AND is_active = TRUE
                    """, live_ids)

                result["applied"] = True

            return [TextContent(type="text", text=json.dumps(result, indent=2, default=json_serial))]

        else:
            return [TextContent(type="text", text=json.dumps({"error": f"Unknown tool: {name}"}))]

    finally:
        await conn.close()


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
