---
title: AI Workers Reference
created: 2026-02-10
updated: 2026-02-10
tags: [workers, claude, ai, mcp]
---

# AI Workers Reference

Charm Email OS uses Claude Code-powered workers for AI-intensive tasks. These run as background daemons that poll for jobs and execute them using Claude Code CLI.

## Worker Overview

| Worker | Purpose | Poll Table | Dockerfile |
|--------|---------|------------|------------|
| **Strategy** | Generate 4-campaign strategies | `strategy_generation_jobs` | `Dockerfile.strategy-worker` |
| **Domain** | Generate domain suggestions | `domain_generation_jobs` | `Dockerfile.domain-worker` |
| **Spintax** | Process spintax in emails | `spintax_jobs` | `Dockerfile.spintax-worker` |
| **Purchase** | Automate HyperTide inbox buys | `purchase_jobs` | `Dockerfile.purchase-worker` |

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                       WORKER DAEMON                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│   ┌───────────────────────────────────────────────────────────┐ │
│   │  1. POLL LOOP                                              │ │
│   │     SELECT * FROM jobs WHERE status = 'pending'           │ │
│   │     LIMIT 1 FOR UPDATE SKIP LOCKED                        │ │
│   └───────────────────────────────────────────────────────────┘ │
│                              │                                   │
│                              ▼ job found                         │
│   ┌───────────────────────────────────────────────────────────┐ │
│   │  2. CLAIM JOB                                              │ │
│   │     UPDATE jobs SET status = 'processing' WHERE id = ?    │ │
│   └───────────────────────────────────────────────────────────┘ │
│                              │                                   │
│                              ▼                                   │
│   ┌───────────────────────────────────────────────────────────┐ │
│   │  3. SPAWN CLAUDE CODE                                      │ │
│   │     claude --print "Generate strategy for job {job_id}"   │ │
│   │            --mcp strategy_mcp                              │ │
│   │            --skill generate-strategy                       │ │
│   └───────────────────────────────────────────────────────────┘ │
│                              │                                   │
│                              ▼                                   │
│   ┌───────────────────────────────────────────────────────────┐ │
│   │  4. CLAUDE CODE EXECUTION                                  │ │
│   │     - Uses MCP tools to read context                       │ │
│   │     - Generates content using skill                        │ │
│   │     - Saves output via MCP tools                           │ │
│   └───────────────────────────────────────────────────────────┘ │
│                              │                                   │
│                              ▼                                   │
│   ┌───────────────────────────────────────────────────────────┐ │
│   │  5. COMPLETE JOB                                           │ │
│   │     UPDATE jobs SET status = 'completed' WHERE id = ?     │ │
│   └───────────────────────────────────────────────────────────┘ │
│                              │                                   │
│                              ▼                                   │
│   ┌───────────────────────────────────────────────────────────┐ │
│   │  6. SLEEP & REPEAT                                         │ │
│   │     time.sleep(POLL_INTERVAL)                              │ │
│   └───────────────────────────────────────────────────────────┘ │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## Strategy Worker

**File**: `workers/strategy_worker.py`
**Dockerfile**: `Dockerfile.strategy-worker`
**Compose**: `docker-compose.strategy-worker.yml`

### Purpose

Generates 4-campaign strategy cycles based on client onboarding data. Each cycle includes:
- 4 campaigns (different angles)
- 4 emails per campaign
- ICP mapping
- Variable schema
- QA scoring

### Configuration

| Env Var | Purpose | Default |
|---------|---------|---------|
| `POLL_INTERVAL` | Seconds between polls | 5 |
| `CLAUDE_ACCOUNT` | Claude subscription account | ClaudeCodeMax |
| `OAUTH_CHECK_INTERVAL` | Seconds between OAuth checks | 3600 |

### MCP Tools

The strategy worker uses the `strategy_mcp` server:

| Tool | Purpose |
|------|---------|
| `get_client_context` | Get client + onboarding data |
| `get_job_context` | Get job details |
| `save_campaign_document` | Save generated stablekernel doc |
| `update_job_status` | Mark job complete/failed |

### Local Testing

```bash
# Option 1: Enable in local compose (uncomment strategy-worker)
docker compose -f docker-compose.local.yml up -d strategy-worker

# Option 2: Run standalone
docker compose -f docker-compose.strategy-worker.yml up -d

# Authenticate (first time)
docker exec -it charm-strategy-worker claude /login

# Monitor logs
docker logs -f charm-strategy-worker
```

## Domain Worker

**File**: `workers/domain_generator_worker.py`
**Dockerfile**: `Dockerfile.domain-worker`
**Compose**: `docker-compose.domain-worker.yml`

### Purpose

Generates domain name suggestions for clients based on their business context and legitimacy requirements.

### Local Testing

```bash
docker compose -f docker-compose.domain-worker.yml up -d
docker exec -it charm-domain-worker claude /login
docker logs -f charm-domain-worker
```

## Spintax Worker

**File**: `workers/spintax_worker.py`
**Dockerfile**: `Dockerfile.spintax-worker`
**Compose**: `docker-compose.spintax-worker.yml`

### Purpose

Processes spintax syntax in email copy to create variation. Converts `{Hello|Hi|Hey}` into multiple versions.

### Local Testing

```bash
docker compose -f docker-compose.spintax-worker.yml up -d
docker exec -it charm-spintax-worker claude /login
docker logs -f charm-spintax-worker
```

## Purchase Worker

**File**: `workers/purchase_worker.py`
**Dockerfile**: `Dockerfile.purchase-worker`

### Purpose

Automates inbox provisioning via HyperTide browser automation. Uses Chrome DevTools MCP for browser control.

### Additional Configuration

| Env Var | Purpose |
|---------|---------|
| `HYPERTIDE_EMAIL` | HyperTide login email |
| `HYPERTIDE_PASSWORD` | HyperTide login password |
| `BISON_USERNAME` | EmailBison login |
| `BISON_PASSWORD` | EmailBison password |

## Authentication

All workers require Claude Code authentication.

### Initial Setup

```bash
# Enter container
docker exec -it <worker-container> bash

# Authenticate with OAuth (expires ~30 days)
claude /login
# Follow browser OAuth flow

# Alternative: API key (never expires)
claude setup-token
```

### Re-authentication

When you see `Invalid API key - Please run /login`:

```bash
docker exec -it <worker-container> claude /login
```

### Credential Persistence

Credentials are stored in a Docker named volume:

```yaml
volumes:
  charm-claude-credentials:
    external: true
```

This volume is shared across all workers, so authenticating once works for all.

## Local Development vs Production

| Aspect | Local | Production |
|--------|-------|------------|
| **Enabled** | Optional (uncomment in compose) | Always running |
| **Database** | Local PostgreSQL | Production OwnRBL |
| **Deployment** | Docker Desktop | Coolify (manual) |
| **Auto-deploy** | N/A | OFF (pinned commit) |

## Production Deployment

Workers do NOT auto-deploy on push. To deploy:

```bash
# Via Coolify MCP
# strategy-worker: qwgc8ws0wwk0wgg4s48ssg0w
# domain-worker: ew8cw0o00ksws8gg4gggws4k
# spintax-worker: roccs4g0gwkcs8ws8k8kgog4
# purchase-worker: xo4o4wcco0scgs8gskggw00k
```

## Monitoring

### Log Viewing

```bash
# Local
docker logs -f charm-strategy-worker

# Production (via Coolify MCP)
# Use coolify tools to view logs
```

### Health Checks

All workers have healthchecks that verify the Python process is running:

```yaml
healthcheck:
  test: ["CMD", "pgrep", "-f", "python3.*strategy_worker.py"]
  interval: 30s
  timeout: 10s
  retries: 3
```

## Creating Test Jobs

```bash
# Run the test script
python scripts/test_strategy_generation.py

# Or insert directly
psql -h localhost -p 5433 -U postgres -d postgres -c "
INSERT INTO strategy_generation_jobs (id, client_id, status)
VALUES (gen_random_uuid(), '4bd07dc0-059a-448b-b6f4-3275d0c104a9', 'pending');
"
```

## Related

- [[architecture]] - System architecture
- [[file-locations]] - Where worker files live
- [[../deployment/strategy-worker-vps]] - VPS deployment guide
- [[../architecture/claude-code-worker]] - Worker architecture details
