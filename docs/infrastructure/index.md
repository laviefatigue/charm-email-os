---
title: Infrastructure Overview
created: 2026-01-16
updated: 2026-02-11
tags: [hub, infrastructure, localhost]
---

# Infrastructure

> **Localhost-First**: Charm Email OS now runs entirely on localhost via Docker. Coolify/VPS deployments are deprecated.

## Current Architecture (Localhost)

```
┌──────────────────────────────────────────────────────────────────────┐
│                       LOCALHOST (Docker)                              │
│                                                                       │
│  ┌─────────────┐  ┌──────────────┐  ┌─────────────┐                  │
│  │  charm-api  │  │charm-frontend│  │  onboarding │                  │
│  │  (FastAPI)  │  │  (Next.js)   │  │    form     │                  │
│  │  :8000      │  │  :3000       │  │  :3004      │                  │
│  └─────────────┘  └──────────────┘  └─────────────┘                  │
│                                                                       │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                   │
│  │  strategy   │  │  emailbison │  │  postgres   │                   │
│  │   worker    │  │    sync     │  │    :5433    │                   │
│  └─────────────┘  └─────────────┘  └─────────────┘                   │
│                                                                       │
└──────────────────────────────────────────────────────────────────────┘
```

## Access Points

| Service | URL | Port |
|---------|-----|------|
| Frontend | http://localhost:3000 | 3000 |
| API | http://localhost:8000 | 8000 |
| API Docs | http://localhost:8000/docs | 8000 |
| Onboarding Form | http://localhost:3004 | 3004 |
| PostgreSQL | localhost:5433 | 5433 |

## Getting Started

```bash
cd D:\Work\charm-email-os
docker compose -f docker-compose.local.yml up -d
```

See [[../local-development/index]] for complete setup instructions.

## Infrastructure Policies & Constraints

- [[hypertide-rotation-policy]] - **CRITICAL** - Hypertide domain rotation constraints
  - Cannot add/remove individual inboxes
  - Must replace entire domains
  - Two-tier rotation strategy
  - Requires 20-30% capacity buffer

## Legacy Documentation (Deprecated)

The following infrastructure documentation is preserved for reference only:

- [[coolify]] - ⚠️ DEPRECATED - Self-hosted PaaS
- [[supabase]] - Database reference
- [[vps]] - ⚠️ DEPRECATED - Hetzner VPS
- [[security-hardening]] - Security assessment guide

## Related

- [[../local-development/index]] - **Start here** - Local development hub
- [[../architecture/data-flow]] - Data flow through infrastructure
- [[../features/hypertide-health-v3-impact]] - How rotation policy affects Health V3
