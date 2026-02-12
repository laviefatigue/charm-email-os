---
title: Deployment Documentation
created: 2026-01-16
updated: 2026-02-10
tags: [deployment, index]
---

# Deployment Documentation

Documentation for deploying Charm Email OS components.

## Development Workflow

**IMPORTANT**: All changes start locally, then deploy to production.

```
LOCAL DEVELOPMENT → TEST → COMMIT → PRODUCTION (Coolify)
```

See [[../local-development/development-workflow]] for the complete workflow.

## Deployment Guides

- [[../local-development/index]] - **Start here** - Local development hub
- [[local-docker]] - **Local Docker development** (recommended for testing)
- [[ai-component]] - Charm Strategy AI container architecture and usage
- [[strategy-worker-vps]] - Strategy worker deployment on VPS
- [[purchase-worker-coolify]] - **Purchase worker Coolify deployment** (Hypertide browser automation)

## Status Tracking

- [[strategy-ai-deployment-status]] - Current deployment progress and blockers

## Current Working Setup (as of 2026-01-20)

### Local Docker Worker (Active)

The strategy worker runs locally via Docker Desktop, connecting to the VPS database:

```bash
# Container name: charm-strategy-test
# Image: charm-strategy-worker:local
# Status: Running, Healthy
# Credential volume: charm-claude-credentials
```

| Aspect | Configuration |
|--------|---------------|
| Database | VPS PostgreSQL (31.97.142.123:5432) |
| Authentication | Claude Max subscription via OAuth |
| Credential Persistence | Docker named volume |
| Polling Interval | 5 seconds |

### Authentication Notes

- **OAuth tokens expire** - Refresh tokens last ~30 days
- **Re-auth required** when: `Invalid API key - Please run /login` error appears
- **Re-auth command**: `docker exec -it charm-strategy-test claude /login`

See [[local-docker]] for complete setup and troubleshooting guide.

## Infrastructure

See [[../infrastructure/index]] for infrastructure details:
- [[../infrastructure/coolify]] - Coolify self-hosted PaaS
- [[../infrastructure/supabase]] - Database hosting (currently using VPS PostgreSQL)
- [[../infrastructure/vps]] - VPS configuration

## Quick Reference

### Coolify Applications

| Application | UUID | Purpose | Status |
|-------------|------|---------|--------|
| charm-api | `ccssgc4gowsog04wck400o0w` | FastAPI backend | Running |
| charm-frontend | `jskswosswg80cg8wwk8g8kww` | Next.js frontend | Running |
| charm-purchase-worker | `xo4o4wcco0scgs8gskggw00k` | Hypertide purchase automation | Deploying |
| charm-strategy-ai | - | AI strategy container | Built (not active - using local Docker) |

### Local Docker Components

| Component | Container | Purpose |
|-----------|-----------|---------|
| Strategy Worker | `charm-strategy-test` | Polls DB, spawns Claude Code |
| Purchase Worker (test) | `charm-purchase-worker-test` | Purchase testing with step-by-step control |
| Claude Credentials | `charm-claude-credentials` volume | Persisted OAuth tokens |

## Deployment Workflow

1. **Code changes** → Push to GitHub
2. **Coolify** → Auto-deploys charm-api, charm-frontend, and charm-purchase-worker
3. **Strategy Worker** → Runs locally via Docker Desktop
4. **Purchase Worker** → Runs on Coolify (see [[purchase-worker-coolify]])
5. **Re-auth** → When OAuth expires, run `docker exec -it <container> claude /login`

## Related

- [[../local-development/index]] - Local development hub
- [[../local-development/development-workflow]] - Local → production workflow
- [[../architecture/index]] - System architecture
- [[../features/index]] - Feature documentation
