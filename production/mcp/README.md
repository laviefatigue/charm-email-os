# MCP Tools for Infrastructure Management

## Overview

MCP (Model Context Protocol) servers provide Claude Code with direct access to infrastructure APIs. This enables end-to-end management of production services.

## Available MCP Servers

| Server | Purpose | Location |
|--------|---------|----------|
| cloudflare | DNS, Tunnel, Access management | Global (~/.mcp.json) |
| coolify | Deployment, logs, status | Global (~/.mcp.json) |
| hostinger-api | Domain registration, VPS | Project (.mcp.json) |
| chrome-devtools | Browser automation for Coolify UI | Project (.mcp.json) |

## Configuration Files

### Global Config (~/.mcp.json)
Contains servers used across all projects:
- Cloudflare (API token + account ID)
- Coolify (API connection)

### Project Config (.mcp.json)
Contains project-specific servers:
- Hostinger API
- Chrome DevTools (for Coolify UI automation)

## Server Details

### cloudflare
Manages Cloudflare infrastructure via API.

**Capabilities**:
- DNS record management
- Tunnel configuration
- Zero Trust Access policies
- Domain settings

**Authentication**:
- API Token in environment variable
- Account ID in environment variable

### coolify
Manages Coolify deployments.

**Capabilities**:
- Deploy applications
- View logs
- Check service status
- Manage environment variables

**Skills Available**:
- `/deploy` - Quick deployment
- `/coolify-status` - Infrastructure health check
- `/coolify-logs` - View application logs
- `/coolify-setup` - Configuration wizard

### hostinger-api
Manages Hostinger services.

**Capabilities**:
- Domain registration
- DNS management
- VPS management

**Authentication**:
- API Token in environment variable

### chrome-devtools
Browser automation for Coolify UI when API access is limited.

**Capabilities**:
- Navigate pages
- Fill forms
- Click elements
- Take screenshots

**Use Cases**:
- Updating environment variables
- Terminal access
- UI-only operations

## Combined Configuration

See [mcp-servers.json](mcp-servers.json) for the full combined configuration template.

## Usage Examples

### Deploy via Coolify MCP
```
User: Deploy charm-api
Claude: [Uses coolify MCP to trigger deployment]
```

### Check DNS via Cloudflare MCP
```
User: Show DNS records for wizardgrimoire.cloud
Claude: [Uses cloudflare MCP to list DNS records]
```

### Register Domain via Hostinger
```
User: Register example.com
Claude: [Uses hostinger-api MCP to check availability and purchase]
```

## Adding New MCP Servers

1. Install the MCP server package
2. Add configuration to appropriate .mcp.json:
   - Global servers: `~/.mcp.json`
   - Project-specific: `./mcp.json`
3. Include required environment variables
4. Restart Claude Code to load new servers
