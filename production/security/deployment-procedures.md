# Security & Deployment Procedures

## Security Architecture

### Defense in Depth

```
Layer 1: Cloudflare DDoS Protection
    ↓
Layer 2: Cloudflare Zero Trust Access (Google OAuth)
    ↓
Layer 3: Cloudflare Tunnel (IP hidden)
    ↓
Layer 4: UFW Firewall (SSH only)
    ↓
Layer 5: Coolify Container Isolation
```

### What's Protected

| Component | Protection |
|-----------|------------|
| VPS IP | Hidden behind Cloudflare Tunnel |
| Admin UIs | Google OAuth (@hirecharm.com) |
| SSH Access | Key-based, port 22 only |
| API | Tunnel + Firewall (no direct access) |

## Application-Level Security (2026-03-03)

### Authentication Flow

```
Frontend (behind Cloudflare Access)
    ↓
Cloudflare injects CF-Access-Authenticated-User-Email header
    ↓
Next.js reads header in /api/auth/user route
    ↓
Stores email in sessionStorage
    ↓
API calls include X-User-Email header
    ↓
FastAPI validates email domain (@hirecharm.com only)
```

### Critical Endpoint Protection

| Endpoint | Auth | Rate Limit | Activity Log |
|----------|------|------------|--------------|
| `POST /bulk-purchase` | Required | 10/min | Yes |
| `POST /hypertide-order` | Required | 5/min | Yes |
| Other endpoints | Optional | No | No |

### Security Controls

#### 1. Email Domain Validation (`api/deps/user.py`)
- Only `@hirecharm.com` emails accepted
- Invalid domains logged and rejected
- Prevents spoofed X-User-Email headers

#### 2. Origin Validation
- Allowed origins: `app.wizardgrimoire.cloud`, `dashboard.wizardgrimoire.cloud`, `localhost:3000/8000`
- Requests from other origins rejected

#### 3. Rate Limiting (`api/deps/rate_limit.py`)
- In-memory rate limiter per IP
- Configurable per-endpoint limits
- Returns 429 Too Many Requests when exceeded

#### 4. CORS Configuration (`api/config.py`)
- Default: explicit allowlist (no wildcards)
- Set `CORS_ORIGINS_RAW` env var for custom origins
- Production: only wizardgrimoire.cloud domains allowed

#### 5. Dev Header Bypass Protection
- `x-dev-user-email` header only works in `NODE_ENV=development`
- Production builds ignore this header completely

#### 6. Slack Webhook Signature Verification
- Required in production (DEBUG=false)
- Only skipped in local development (DEBUG=true)
- Invalid signatures rejected with 401

### Activity Logging

All critical actions logged to `activity_log` table:
- User email
- Action type
- Resource type/ID
- Request details (JSONB)
- IP address
- Timestamp

Query recent activity:
```sql
SELECT user_email, action, resource_type, details, created_at
FROM activity_log
ORDER BY created_at DESC
LIMIT 20;
```

### Security Audit Checklist

- [ ] All purchase endpoints require authentication
- [ ] Rate limiting active on critical endpoints
- [ ] CORS configured (no wildcards in production)
- [ ] Dev headers disabled in production
- [ ] Slack signing secret configured
- [ ] Activity logging capturing user actions

## Deployment Checklist

### Before Deployment

- [ ] Code reviewed and tested locally
- [ ] Environment variables prepared
- [ ] Database migrations ready (if any)

### During Deployment

1. **Deploy via Coolify MCP or UI**
2. **Monitor logs** during deployment
3. **Verify health check** passes

### After Deployment

- [ ] Health check: `curl https://api.wizardgrimoire.cloud/health`
- [ ] Frontend loads correctly
- [ ] Key functionality tested
- [ ] No errors in logs

## Rollback Procedure

### Via Coolify UI
1. Go to application
2. Deployments tab
3. Find previous successful deployment
4. Click "Rollback"

### Manual Rollback
1. SSH to VPS
2. Coolify will handle container replacement

## Security Procedures

### Adding New Subdomain

1. **Create DNS record in Cloudflare**
   - Type: CNAME
   - Name: new-subdomain
   - Target: tunnel ID.cfargotunnel.com

2. **Update tunnel config** (`/etc/cloudflared/config.yml`)
   ```yaml
   - hostname: new-subdomain.wizardgrimoire.cloud
     service: http://localhost:80
     originRequest:
       httpHostHeader: {coolify-sslip.io-domain}
   ```

3. **Restart tunnel**
   ```bash
   systemctl restart cloudflared
   ```

4. **Add Access policy** (if admin UI)
   - Cloudflare Zero Trust Dashboard
   - Access > Applications > Add application

### Rotating API Keys

1. Generate new key in provider dashboard
2. Update in Coolify environment variables
3. Redeploy affected services
4. Verify functionality
5. Revoke old key

### Emergency: Blocking Access

If compromise suspected:

1. **Block all traffic** (Cloudflare)
   - Security > WAF > Create rule to block all

2. **Disable tunnel** (VPS)
   ```bash
   systemctl stop cloudflared
   ```

3. **Investigate** via SSH

### SSH Key Management

- Keys managed in Coolify server settings
- Never commit SSH keys to repository
- Rotate keys periodically

### Hostinger SSH Key Management

SSH keys can be managed via Hostinger API (VPS MCP tools):
- `VPS_getPublicKeysV1` - List registered keys
- `VPS_createPublicKeyV1` - Add new key to account
- `VPS_attachPublicKeyV1` - Attach key to VPS

**Important**: Attaching a key via API registers it for **future provisioning** only.
It does NOT automatically add to running instances' `~/.ssh/authorized_keys`.

## Database Migration Procedure

### Why Special Handling Is Needed

The VPS IP is hidden behind Cloudflare Tunnel, and UFW blocks all direct access except SSH.
Database port 5433 is not exposed through the tunnel for security reasons.

### Option 1: Coolify Web Terminal (Recommended)

Secure access via Coolify's container terminal:

1. Navigate to https://coolify.wizardgrimoire.cloud
2. Projects → charm-email-os → postgres (database)
3. Click "Terminal" tab
4. Run migrations:
   ```bash
   psql -U charm -d postgres
   # Then paste SQL or use \i /path/to/migration.sql
   ```

### Option 2: Temporary Public Access

For running migrations from local machine:

1. **Enable**: Coolify → postgres → Settings → Check "Make it publicly available"
2. **Run migration**:
   ```bash
   PGPASSWORD=$POSTGRES_PASSWORD psql -h 187.77.19.81 -p 5433 -U charm -d postgres \
     -f migrations/0XX_migration.sql
   ```
3. **Disable immediately**: Uncheck "Make it publicly available"

**Warning**: Docker bypasses UFW when "publicly available" is enabled. Always disable after use.

### Option 3: SSH Tunnel (Requires VPS_3_SSH Key)

If you have the VPS_3_SSH private key:
```bash
ssh -L 5433:localhost:5432 root@187.77.19.81 -N &
PGPASSWORD=$POSTGRES_PASSWORD psql -h localhost -p 5433 -U charm -d postgres
```

### VPS Reference

| VPS ID | IP | Plan | Purpose |
|--------|-----|------|---------|
| 1364022 | 187.77.19.81 | KVM 4 | Production |
| 787119 | 82.180.160.120 | KVM 2 | Legacy |
| 881597 | 31.97.142.123 | KVM 2 | Legacy |

## Monitoring

### Health Checks

| Endpoint | Expected |
|----------|----------|
| `/health` | `{"status":"healthy"}` |

### Logs

```bash
# Via Coolify UI
# Application > Logs tab

# Via MCP
# /coolify-logs skill
```

### Tunnel Status

```bash
# On VPS
systemctl status cloudflared
journalctl -u cloudflared -f
```

## Incident Response

### API Down

1. Check health endpoint
2. Check Coolify logs
3. Check tunnel status
4. Restart service if needed

### Frontend Not Loading

1. Check browser console for errors
2. Verify API_URL environment variable
3. Check Cloudflare Access isn't blocking
4. Redeploy if NEXT_PUBLIC_* was changed

### Tunnel Disconnected (Error 1043)

1. SSH to VPS
2. `systemctl restart cloudflared`
3. Verify: `systemctl status cloudflared`

### Access Blocking Legitimate Users

1. Check Cloudflare Zero Trust logs
2. Verify user email domain is allowed
3. Check session hasn't expired

## Compliance Notes

- All admin access requires Google OAuth
- Audit logs available in Cloudflare dashboard
- No direct IP access possible (firewall + tunnel)
- All traffic encrypted (HTTPS via Cloudflare)
