# Charm DB MCP - Production Database Access

Direct read/write access to the Charm Email OS production database via MCP.

## Setup

### 1. Enable Database Public Access (Coolify)

The production database is behind the Coolify network. To access it:

1. Go to **Coolify** → **Projects** → **charm-email-os** → **postgres**
2. Go to **Settings** → **General**
3. Enable **"Publicly available"**
4. Note the **Public Port** (e.g., `32768`)

The connection will be: `host:public_port`

### 2. Get Connection Details

From Coolify postgres settings:
- **Host**: Your VPS IP (e.g., `187.77.19.81`)
- **Port**: The public port from step 1
- **User**: `charm`
- **Password**: (from Coolify secrets or `.env`)
- **Database**: `postgres`

### 3. Add to .mcp.json

Add the `charm-db` server to your `.mcp.json`:

```json
{
  "mcpServers": {
    "charm-db": {
      "command": "py",
      "args": ["-m", "mcp.charm_db.server"],
      "env": {
        "PYTHONPATH": "D:/Work/charm-email-os",
        "CHARM_DB_HOST": "187.77.19.81",
        "CHARM_DB_PORT": "32768",
        "CHARM_DB_USER": "charm",
        "CHARM_DB_PASSWORD": "your-password-here",
        "CHARM_DB_NAME": "postgres"
      }
    }
  }
}
```

### 4. Install Dependencies

```bash
pip install mcp asyncpg
```

### 5. Restart Claude Code

After updating `.mcp.json`, restart Claude Code to load the new MCP server.

## Available Tools

### query_inventory
Get inventory_pool_status distribution for a workspace.

```
query_inventory(workspace_name="Selery")
```

Returns:
```json
{
  "workspace": "Selery",
  "allocation": [
    {"provider": "entra", "inventory_pool_status": "deployed", "inbox_count": 520},
    {"provider": "entra", "inventory_pool_status": "reserve", "inbox_count": 93},
    {"provider": "google", "inventory_pool_status": "deployed", "inbox_count": 63},
    {"provider": "google", "inventory_pool_status": "reserve", "inbox_count": 11}
  ]
}
```

### query_capacity
Get client capacity data from v_client_capacity view.

```
query_capacity(client_name="Selery")
```

Returns targets, live counts, reserve counts, surplus, and calculated reserve capacity.

### query_domains
Get domain-level allocation status.

```
query_domains(workspace_name="Selery")
```

Returns each domain with its pool status, inbox count, and health score.

### query_sql
Run arbitrary SELECT queries.

```
query_sql(sql="SELECT * FROM workspaces LIMIT 5")
```

Safety: Only SELECT queries allowed. Blocks DROP, DELETE, UPDATE, etc.

### apply_allocation
Apply domain allocation based on capacity and health scoring.

```
apply_allocation(workspace_name="Selery", dry_run=true)
```

- `dry_run=true`: Shows what would change without applying
- `dry_run=false`: Actually updates inventory_pool_status

## Security Notes

1. **Temporary Access**: Consider disabling public DB access when not actively using it
2. **Read-Only by Default**: query_* tools are read-only
3. **Write Tools**: Only `apply_allocation` modifies data, and requires explicit `dry_run=false`
4. **Firewall**: VPS firewall (UFW) must allow the public port

## Troubleshooting

### Connection Refused
- Check VPS firewall: `ufw allow 32768/tcp`
- Verify public access is enabled in Coolify
- Check the public port matches your config

### Authentication Failed
- Verify password in .mcp.json matches Coolify postgres secrets
- Default user is `charm`, database is `postgres`

### MCP Not Loading
- Check PYTHONPATH points to charm-email-os root
- Ensure `mcp` and `asyncpg` are installed
- Check Claude Code logs for errors

## Alternative: SSH Tunnel

If you prefer not to expose the database publicly:

```bash
ssh -L 5432:postgres:5432 user@vps-ip
```

Then use `localhost:5432` in your MCP config.

This requires SSH key access to the VPS.
