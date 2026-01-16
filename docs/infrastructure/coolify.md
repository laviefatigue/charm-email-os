---
title: Coolify Deployment Platform
created: 2026-01-16
updated: 2026-01-16
tags: [infrastructure, coolify, deployment]
---

# Coolify

Self-hosted PaaS for deploying and managing Docker containers.

## Service Details

| Property | Value |
|----------|-------|
| Dashboard | `https://panel.laviefatigue.com` |
| Access Method | Web UI + Coolify MCP Server |
| VPS IP | `31.97.142.123` |

## Deployed Applications

| Application | UUID | FQDN | Git Branch | Status |
|-------------|------|------|------------|--------|
| charm-api | `ccssgc4gowsog04wck400o0w` | `http://ccssgc4gowsog04wck400o0w.31.97.142.123.sslip.io` | master | running |
| charm-frontend | `jskswosswg80cg8wwk8g8kww` | `http://jskswosswg80cg8wwk8g8kww.31.97.142.123.sslip.io` | master | running |

## Deployment Process

1. Push code to `master` branch on GitHub
2. Trigger deployment via Coolify MCP or dashboard
3. Coolify pulls code, builds Docker image, deploys

### Using Coolify MCP

```python
# Trigger deployment
mcp__coolify__trigger_deployment(
    application_uuid="ccssgc4gowsog04wck400o0w",
    confirm=True
)

# Check deployment status
mcp__coolify__get_deployment_details(
    deployment_uuid="..."
)

# View application logs
mcp__coolify__get_application_logs(
    application_uuid="ccssgc4gowsog04wck400o0w"
)
```

## Environment Variables

### charm-api
| Variable | Purpose |
|----------|---------|
| `POSTGRES_HOST` | Supabase connection host |
| `POSTGRES_PORT` | Database port (6543) |
| `POSTGRES_DB` | Database name (postgres) |
| `POSTGRES_USER` | Database user |
| `POSTGRES_PASSWORD` | Database password |
| `CORS_ORIGINS` | Allowed CORS origins |

### charm-frontend
| Variable | Purpose |
|----------|---------|
| `NEXT_PUBLIC_API_URL` | Backend API URL |

## Docker Configuration

### API Dockerfile Location
`D:\Work\charm-email-os\api\Dockerfile`

### Frontend Dockerfile Location
`D:\Work\charm-email-os\charm-email-os\Dockerfile`

## Monitoring

- View logs: Coolify dashboard → Application → Logs
- View deployments: Coolify dashboard → Application → Deployments
- Health check: Application status in dashboard

## Related

- [[supabase]] - Database hosting
- [[vps]] - Server hosting Coolify
- [[../architecture/api-endpoints]] - API routes deployed here
