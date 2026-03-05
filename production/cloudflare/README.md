# Cloudflare Configuration

## Account Details

| Item | Value |
|------|-------|
| Account ID | `edc3f397f5bf38a27120797e8f1b361a` |
| Domain | `wizardgrimoire.cloud` |
| DNS | Managed by Cloudflare |
| SSL Mode | Flexible |

## Tunnel Configuration

| Item | Value |
|------|-------|
| Tunnel Name | `charm-tunnel` |
| Tunnel ID | `3622b036-2569-45b8-a787-ac4862098d52` |
| Config Path | `/etc/cloudflared/config.yml` |
| Credentials | `/etc/cloudflared/{tunnel-id}.json` |
| Service | `systemctl cloudflared` |

## DNS Records

All DNS records point to the tunnel:

| Type | Name | Content |
|------|------|---------|
| CNAME | app | `3622b036-2569-45b8-a787-ac4862098d52.cfargotunnel.com` |
| CNAME | api | `3622b036-2569-45b8-a787-ac4862098d52.cfargotunnel.com` |
| CNAME | dashboard | `3622b036-2569-45b8-a787-ac4862098d52.cfargotunnel.com` |
| CNAME | coolify | `3622b036-2569-45b8-a787-ac4862098d52.cfargotunnel.com` |

## Access Policies

### Protected Applications

| Application | URL | Authentication |
|-------------|-----|----------------|
| Charm Frontend | app.wizardgrimoire.cloud | Google OAuth |
| Executive Dashboard | dashboard.wizardgrimoire.cloud | Google OAuth |
| Coolify Panel | coolify.wizardgrimoire.cloud | Google OAuth |

### Service Token (for automation)

| Item | Value |
|------|-------|
| Name | `Charm API Automation` |
| Client ID | `2d248ecd21fc2106dac566160e1d73b3.access` |
| Client Secret | (stored securely) |

**Usage:**
```bash
curl -H "CF-Access-Client-Id: {client_id}" \
     -H "CF-Access-Client-Secret: {client_secret}" \
     https://app.wizardgrimoire.cloud/api/endpoint
```

### API Endpoint

The API (`api.wizardgrimoire.cloud`) does **NOT** have Access protection because:
- Frontend runs in browser and needs to fetch() to API
- Browser cannot send service token headers automatically
- Security provided by: tunnel (IP hidden) + firewall (SSH only)

## Management Commands

### Via MCP (Cloudflare plugin)
```
# Available through MCP cloudflare server
# See production/mcp/README.md
```

### Via API
```bash
# List Access applications
curl -X GET "https://api.cloudflare.com/client/v4/accounts/{account_id}/access/apps" \
     -H "Authorization: Bearer {api_token}"

# Get tunnel status
curl -X GET "https://api.cloudflare.com/client/v4/accounts/{account_id}/cfd_tunnel/{tunnel_id}" \
     -H "Authorization: Bearer {api_token}"
```

### On VPS
```bash
# Check tunnel service
systemctl status cloudflared

# Restart tunnel
systemctl restart cloudflared

# View tunnel logs
journalctl -u cloudflared -f
```

## Troubleshooting

### Error 1043 (Tunnel not connected)
```bash
# SSH to VPS and restart cloudflared
systemctl restart cloudflared
```

### Access blocking API calls
If frontend shows "Failed to fetch":
1. Check if Access is on API subdomain (it shouldn't be)
2. Remove Access app from API if present
3. API security comes from tunnel + firewall, not Access

### SSL/Certificate errors
- SSL mode should be "Flexible" (tunnel routes to HTTP internally)
- Coolify services run on HTTP, Cloudflare handles HTTPS
