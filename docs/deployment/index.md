---
title: Deployment Documentation
created: 2026-01-16
updated: 2026-01-16
tags: [deployment, index]
---

# Deployment Documentation

Documentation for deploying Charm Email OS components.

## Deployment Guides

- [[ai-component]] - Charm Strategy AI container architecture and usage
- [[strategy-worker-vps]] - Strategy worker deployment on VPS

## Status Tracking

- [[strategy-ai-deployment-status]] - Current deployment progress and blockers

## Infrastructure

See [[../infrastructure/index]] for infrastructure details:
- [[../infrastructure/coolify]] - Coolify self-hosted PaaS
- [[../infrastructure/supabase]] - Database hosting
- [[../infrastructure/vps]] - VPS configuration

## Quick Reference

### Coolify Applications

| Application | Purpose | Status |
|-------------|---------|--------|
| charm-api | FastAPI backend | Running |
| charm-frontend | Next.js frontend | Running |
| charm-strategy-ai | AI strategy container | Built (batch job) |

### VPS Components

| Component | Location | Purpose |
|-----------|----------|---------|
| Claude credentials | `/root/.claude/` | Persisted auth for containers |
| Prefect worker | Systemd service | Orchestrates strategy jobs |

## Deployment Workflow

1. **Code changes** → Push to GitHub
2. **Coolify** → Auto-deploys charm-api and charm-frontend
3. **Strategy AI** → Manual rebuild or Prefect-triggered runs

## Related

- [[../architecture/index]] - System architecture
- [[../features/index]] - Feature documentation
