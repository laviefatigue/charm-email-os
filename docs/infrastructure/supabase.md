---
title: Supabase Database
created: 2026-01-16
updated: 2026-01-16
tags: [infrastructure, supabase, database, postgresql]
---

# Supabase

Managed PostgreSQL database hosting for Charm Email OS.

## Connection Details

| Property | Value |
|----------|-------|
| Host | `aws-0-us-east-1.pooler.supabase.com` |
| Port | `6543` |
| Database | `postgres` |
| Project ID | `lhnzdotfevttijwyfcib` |
| Connection Method | Transaction pooler (PgBouncer) |

## Connection String

```
postgresql://postgres.lhnzdotfevttijwyfcib:[PASSWORD]@aws-0-us-east-1.pooler.supabase.com:6543/postgres
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
| `strategy_generation_jobs` | Strategy generation queue (NEW) |
| `strategy_suggestions` | Generated suggestions (NEW) |

## Access Methods

1. **Application code** - Via environment variables
2. **CLI (psql)** - Direct connection for debugging
3. **Supabase Studio** - Web UI at `https://supabase.com/dashboard`

## Backup & Recovery

Managed by Supabase - automatic daily backups with point-in-time recovery.

## Related

- [[coolify]] - Applications connecting to this database
- [[../database/schema]] - Full schema documentation
- [[../database/migrations]] - Migration history
