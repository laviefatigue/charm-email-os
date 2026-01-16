---
title: Infrastructure Overview
created: 2026-01-16
updated: 2026-01-16
tags: [hub, infrastructure]
---

# Infrastructure

Charm Email OS runs on a self-hosted infrastructure using Coolify for deployments.

## Components

- [[coolify]] - Self-hosted PaaS for container deployments
- [[supabase]] - PostgreSQL database (managed)
- [[vps]] - Hetzner VPS hosting the Coolify instance

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                    VPS (31.97.142.123)                      │
│  ┌────────────────────────────────────────────────────────┐ │
│  │                    Coolify                              │ │
│  │  ┌──────────────┐    ┌──────────────┐                  │ │
│  │  │  charm-api   │    │charm-frontend│                  │ │
│  │  │  (FastAPI)   │    │  (Next.js)   │                  │ │
│  │  └──────────────┘    └──────────────┘                  │ │
│  └────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
                              │
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                    Supabase (AWS)                           │
│  ┌────────────────────────────────────────────────────────┐ │
│  │                   PostgreSQL                            │ │
│  │            aws-0-us-east-1.pooler.supabase.com         │ │
│  └────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

## Access Methods

| Service | Access Method |
|---------|---------------|
| Coolify | Web UI + [[mcp-coolify]] |
| Supabase | Connection string (asyncpg) |
| VPS | SSH (if needed) |

## Related

- [[../index]] - Main documentation hub
- [[../architecture/data-flow]] - Data flow through infrastructure
