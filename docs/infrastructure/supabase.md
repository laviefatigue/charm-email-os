---
title: Supabase Database (Coolify Self-Hosted)
created: 2026-01-16
updated: 2026-01-19
tags: [infrastructure, supabase, database, postgresql, coolify]
---

# Supabase (Coolify Self-Hosted)

Self-hosted Supabase instance running on Coolify. This is the **only** database used by Charm Email OS.

## Coolify Service

| Property | Value |
|----------|-------|
| Service UUID | `p0440sksgk4o0s4o444skwg8` |
| Service Name | `supabase-p0440sksgk4o0s4o444skwg8` |
| Image | `supabase/postgres:17.4.1.032` |
| Coolify URL | [panel.laviefatigue.com](https://panel.laviefatigue.com/project/iso808osc4wo0sgsos0wsg40/environment/ak4kg08kkgkoockkk044swcs/service/p0440sksgk4o0s4o444skwg8) |

## Connection Details

| Property | Value |
|----------|-------|
| Host | `31.97.142.123` |
| Port | `5432` |
| Database | `postgres` |
| User | `postgres` |
| Password | `ZEN3hMv6UpA0hfd8OcAUSiJWgpY33q5V` |

## Connection String

```
postgresql://postgres:ZEN3hMv6UpA0hfd8OcAUSiJWgpY33q5V@31.97.142.123:5432/postgres
```

## Supabase API URLs

| Property | Value |
|----------|-------|
| Kong Gateway | `https://supafun.laviefatigue.com` |
| Dashboard User | `wOzUsjVA5BkjqyOh` |
| Dashboard Password | `U0ax5PTcyHCPpaPGfwJRl6WvsFXEBiEO` |

## Environment Variables (for applications)

```bash
POSTGRES_HOST=31.97.142.123
POSTGRES_PORT=5432
POSTGRES_DB=postgres
POSTGRES_USER=postgres
POSTGRES_PASSWORD=ZEN3hMv6UpA0hfd8OcAUSiJWgpY33q5V
```

## Database Libraries

| Application | Library |
|-------------|---------|
| FastAPI (async) | `asyncpg` |
| Workers (sync) | `psycopg2` |

## Connection Code

### Async (API)
```python
import asyncpg

pool = await asyncpg.create_pool(
    host=os.getenv("POSTGRES_HOST"),
    port=int(os.getenv("POSTGRES_PORT")),
    database=os.getenv("POSTGRES_DB"),
    user=os.getenv("POSTGRES_USER"),
    password=os.getenv("POSTGRES_PASSWORD"),
)
```

### Sync (Workers)
```python
import psycopg2

conn = psycopg2.connect(
    host=os.getenv("POSTGRES_HOST"),
    port=int(os.getenv("POSTGRES_PORT")),
    database=os.getenv("POSTGRES_DB"),
    user=os.getenv("POSTGRES_USER"),
    password=os.getenv("POSTGRES_PASSWORD"),
)
```

## Tables Overview

See [[../database/schema]] for full schema documentation.

### Core Tables
| Table | Purpose |
|-------|---------|
| `clients` | Client accounts |
| `workspaces` | OwnRBL workspaces (read-only) |
| `domains` | Email domains |
| `sender_accounts` | Email inboxes |

### Onboarding Tables
| Table | Purpose |
|-------|---------|
| `client_onboarding_submissions` | Form submissions |
| `client_segments` | Customer segments |
| `client_personas` | Buyer personas |

### Job Tables
| Table | Purpose |
|-------|---------|
| `domain_generation_jobs` | Domain generation queue |
| `strategy_generation_jobs` | Strategy generation queue |
| `strategy_suggestions` | Generated email variants |

## Access Methods

1. **Application code** - Via environment variables
2. **CLI (psql)** - Direct connection: `psql -h 31.97.142.123 -p 5432 -U postgres -d postgres`
3. **Supabase Studio** - Via `https://supafun.laviefatigue.com`

## Backup & Recovery

Managed via Coolify snapshot functionality.

## Related

- [[coolify]] - Coolify deployment platform
- [[../database/schema]] - Full schema documentation
- [[../database/migrations]] - Migration history
