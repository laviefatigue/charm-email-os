# Coolify Configuration

## Access

| Item | Value |
|------|-------|
| URL | https://coolify.wizardgrimoire.cloud |
| Authentication | Google OAuth (@hirecharm.com) |
| VPS IP | 187.77.19.81 (hidden behind Cloudflare) |

## Server Details

| Item | Value |
|------|-------|
| Server Name | localhost |
| Platform | Ubuntu (VPS) |
| Docker | Managed by Coolify |
| Proxy | Traefik (port 80) |

## Projects

### charm-email-os
Main project containing all Charm services.

## Deployment

**IMPORTANT**: Auto-deploy is DISABLED on all apps. See [services.md](services.md) for full deployment workflow.

### Why Manual Deployment?
All 7 apps share the same monorepo. With auto-deploy, pushing ANY change rebuilt ALL apps, overloading the VPS.

### Via MCP (Recommended)
```bash
# Deploy specific app by UUID
mcp__coolify__deploy uuid="nckgggwww8sggg0kc4wo00o8" confirm=true  # charm-api
```

See [services.md](services.md) for all app UUIDs.

### Via Skills
```
/deploy           # Quick deployment
/coolify-status   # Health check all services
/coolify-logs     # View application logs
```

### Via UI
1. Navigate to https://coolify.wizardgrimoire.cloud
2. Authenticate with Google (@hirecharm.com)
3. Select application
4. Click "Deploy" or "Redeploy"

## Environment Variables

Environment variables are managed in Coolify UI:
1. Go to application
2. Click "Environment Variables" tab
3. Add/edit variables
4. **Important**: Redeploy after changes

### Build-time vs Runtime

| Prefix | When Applied | Example |
|--------|--------------|---------|
| `NEXT_PUBLIC_*` | Build time | `NEXT_PUBLIC_API_URL` |
| Others | Runtime | `DATABASE_URL` |

**Note**: Changes to `NEXT_PUBLIC_*` variables require full redeploy (rebuild).

## Terminal Access

### Server Terminal (VPS)

Coolify provides terminal access to VPS:
1. Go to Coolify dashboard
2. Click server (localhost)
3. Select "Terminal" tab
4. Commands execute on VPS directly

Useful for:
- Checking firewall: `ufw status`
- Restarting tunnel: `systemctl restart cloudflared`
- Viewing logs: `journalctl -u cloudflared -f`

### Container Terminal (Database Migrations)

For running database migrations securely:
1. Go to Coolify dashboard
2. Projects → charm-email-os → postgres
3. Click "Terminal" tab
4. Run: `psql -U charm -d postgres`

This is the **recommended** method for database migrations as it:
- Doesn't expose the database publicly
- Doesn't require SSH key access
- Works through Cloudflare tunnel

## Domains

Each Coolify application has:
- **Internal domain**: `{random}.187.77.19.81.sslip.io`
- **Public domain**: Configured via Cloudflare tunnel

The tunnel's `httpHostHeader` maps public domains to internal sslip.io domains.
