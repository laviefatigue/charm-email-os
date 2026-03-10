#!/usr/bin/env python3
"""
Charm DB MCP Server - Direct production database access.

Add to .mcp.json:
{
  "charm-db": {
    "command": "py",
    "args": ["-m", "mcp.charm_db_mcp"],
    "env": {
      "POSTGRES_HOST": "...",
      "POSTGRES_PASSWORD": "..."
    }
  }
}
"""
import os
import json
import asyncio
import asyncpg
from typing import Any

# MCP protocol imports
try:
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import Tool, TextContent
except ImportError:
    print("MCP SDK not installed. Run: pip install mcp")
    exit(1)

# Database config from environment
POSTGRES_HOST = os.getenv('POSTGRES_HOST', 'localhost')
POSTGRES_PORT = int(os.getenv('POSTGRES_PORT', 5432))
POSTGRES_USER = os.getenv('POSTGRES_USER', 'charm')
POSTGRES_PASSWORD = os.getenv('POSTGRES_PASSWORD', '')
POSTGRES_DB = os.getenv('POSTGRES_DB', 'postgres')

server = Server("charm-db")


async def get_db_pool():
    """Get database connection pool."""
    return await asyncpg.create_pool(
        host=POSTGRES_HOST,
        port=POSTGRES_PORT,
        user=POSTGRES_USER,
        password=POSTGRES_PASSWORD,
        database=POSTGRES_DB,
        min_size=1,
        max_size=3
    )


@server.list_tools()
async def list_tools():
    return [
        Tool(
            name="query_inventory_status",
            description="Get inventory_pool_status distribution for a workspace",
            inputSchema={
                "type": "object",
                "properties": {
                    "workspace_name": {"type": "string", "description": "Workspace name (e.g., 'Selery')"}
                },
                "required": ["workspace_name"]
            }
        ),
        Tool(
            name="query_capacity",
            description="Get v_client_capacity data for a client",
            inputSchema={
                "type": "object",
                "properties": {
                    "client_name": {"type": "string", "description": "Client name (e.g., 'Selery')"}
                },
                "required": ["client_name"]
            }
        ),
        Tool(
            name="query_sql",
            description="Run a read-only SQL query against production database",
            inputSchema={
                "type": "object",
                "properties": {
                    "sql": {"type": "string", "description": "SQL query (SELECT only)"}
                },
                "required": ["sql"]
            }
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    pool = await get_db_pool()

    try:
        if name == "query_inventory_status":
            workspace = arguments["workspace_name"]
            rows = await pool.fetch("""
                SELECT
                    CASE WHEN sa.esp = 'microsoft' THEN 'entra' ELSE 'google' END as provider,
                    sa.inventory_pool_status,
                    COUNT(*) as inbox_count
                FROM sender_accounts sa
                JOIN domains d ON sa.domain_id = d.id
                JOIN workspaces w ON d.workspace_id = w.id
                WHERE w.workspace_name = $1
                  AND sa.inbox_state = 'live'
                  AND sa.is_active = TRUE
                GROUP BY 1, 2
                ORDER BY 1, 2
            """, workspace)

            result = [dict(r) for r in rows]
            return [TextContent(type="text", text=json.dumps(result, indent=2, default=str))]

        elif name == "query_capacity":
            client = arguments["client_name"]
            row = await pool.fetchrow("""
                SELECT
                    client_name,
                    entra_inboxes_target,
                    entra_inboxes_live,
                    entra_inboxes_reserve,
                    google_inboxes_target,
                    google_inboxes_live,
                    google_inboxes_reserve,
                    target_buffer_ratio
                FROM v_client_capacity
                WHERE client_name = $1
            """, client)

            if row:
                result = dict(row)
                return [TextContent(type="text", text=json.dumps(result, indent=2, default=str))]
            return [TextContent(type="text", text=f"No capacity data for {client}")]

        elif name == "query_sql":
            sql = arguments["sql"].strip()

            # Safety check - only allow SELECT
            if not sql.upper().startswith("SELECT"):
                return [TextContent(type="text", text="Error: Only SELECT queries allowed")]

            rows = await pool.fetch(sql)
            result = [dict(r) for r in rows]
            return [TextContent(type="text", text=json.dumps(result, indent=2, default=str))]

        else:
            return [TextContent(type="text", text=f"Unknown tool: {name}")]

    finally:
        await pool.close()


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
