---
title: Local Docker Development
created: 2026-01-20
updated: 2026-01-20
tags: [deployment, docker, local, development, authentication]
---

# Local Docker Development

Running the Strategy Worker locally using Docker Desktop for development and testing.

## Overview

The strategy worker can run locally on Windows using Docker Desktop, connecting to the remote PostgreSQL database. This is useful for:
- Testing changes before VPS deployment
- Debugging worker issues
- Running with local Claude authentication

## Prerequisites

- Docker Desktop installed and running
- Claude Code CLI authenticated locally (for initial credential setup)
- Access to the PostgreSQL database (Supabase or VPS)

## Container Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  Local Docker Desktop (Windows)                                             │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  charm-strategy-test Container                                       │   │
│  │                                                                      │   │
│  │  ┌──────────────────┐  ┌──────────────────┐  ┌─────────────────┐   │   │
│  │  │ strategy_worker  │  │ Claude Code CLI  │  │  MCP Server     │   │   │
│  │  │     .py          │  │ (authenticated)  │  │ (DB interface)  │   │   │
│  │  └────────┬─────────┘  └────────┬─────────┘  └────────┬────────┘   │   │
│  │           │                     │                     │            │   │
│  │           └─────────────────────┴─────────────────────┘            │   │
│  └───────────────────────────────────────────────────────────────────────┘│
│                                    │                                        │
│  Volume: charm-claude-credentials  │                                        │
│  └── /home/claude/.claude/         │                                        │
│      └── .credentials.json         │                                        │
└────────────────────────────────────┼────────────────────────────────────────┘
                                     │
                                     ▼
                          PostgreSQL (VPS: 31.97.142.123)
                          └── strategy_generation_jobs
                          └── strategy_suggestions
```

## Quick Start

### Step 1: Build the Docker Image

```bash
cd D:\Work\charm-email-os
docker build -f Dockerfile.strategy-worker -t charm-strategy-worker:local .
```

### Step 2: First-Time Authentication

The first time you run the container, you need to authenticate Claude Code:

```bash
# Start interactive container with credential volume
docker run -it --rm \
    -v charm-claude-credentials:/home/claude/.claude \
    charm-strategy-worker:local \
    bash

# Inside container, authenticate
claude /login

# Select "Claude account with subscription"
# Complete OAuth in browser
# Exit when done
exit
```

### Step 3: Run the Worker Daemon

```bash
docker run -d \
    --name charm-strategy-test \
    -e POSTGRES_HOST=31.97.142.123 \
    -e POSTGRES_PORT=5432 \
    -e POSTGRES_DB=postgres \
    -e POSTGRES_USER=postgres \
    -e POSTGRES_PASSWORD='ZEN3hMv6UpA0hfd8OcAUSiJWgpY33q5V' \
    -v charm-claude-credentials:/home/claude/.claude \
    charm-strategy-worker:local
```

### Step 4: Monitor Logs

```bash
docker logs -f charm-strategy-test
```

## Credential Persistence

### How It Works

| Component | Location | Persists Across |
|-----------|----------|-----------------|
| Named Volume | `charm-claude-credentials` | Container restarts, rebuilds |
| Credential File | `/home/claude/.claude/.credentials.json` | OAuth tokens |
| Access Token | Inside .credentials.json | ~1 hour (auto-refreshes) |
| Refresh Token | Inside .credentials.json | ~30 days |

### Volume Mount

The `-v charm-claude-credentials:/home/claude/.claude` flag creates a Docker named volume that:
- Persists credential files across container restarts
- Survives `docker stop` and `docker start`
- Survives `docker rm` and recreating the container
- Is NOT deleted when rebuilding the image

### When Re-Authentication is Required

| Scenario | Re-Auth Needed? |
|----------|-----------------|
| Container restart | No |
| Container rebuild | No (volume persists) |
| Volume deletion | Yes |
| 30+ days inactive | Yes (refresh token expired) |
| Manual logout | Yes |

## Common Commands

### Container Management

```bash
# Check container status
docker ps -a --filter "name=charm-strategy"

# View logs
docker logs charm-strategy-test
docker logs --tail 50 charm-strategy-test
docker logs --since 5m charm-strategy-test

# Restart container
docker restart charm-strategy-test

# Stop container
docker stop charm-strategy-test

# Remove container (keeps volume)
docker rm charm-strategy-test

# Start fresh (recreate)
docker rm -f charm-strategy-test
# Then run the docker run command again
```

### Authentication

```bash
# Check if credentials exist
docker exec charm-strategy-test ls -la /home/claude/.claude/.credentials.json

# Re-authenticate (interactive)
docker exec -it charm-strategy-test claude /login

# Check Claude version
docker exec charm-strategy-test claude --version
```

### Database Operations

```bash
# Check pending jobs
docker exec charm-strategy-test python3 -c "
import psycopg2
import os
conn = psycopg2.connect(
    host=os.environ.get('POSTGRES_HOST'),
    port=os.environ.get('POSTGRES_PORT', '5432'),
    database=os.environ.get('POSTGRES_DB', 'postgres'),
    user=os.environ.get('POSTGRES_USER'),
    password=os.environ.get('POSTGRES_PASSWORD')
)
cur = conn.cursor()
cur.execute('SELECT id, status, created_at FROM strategy_generation_jobs ORDER BY created_at DESC LIMIT 5')
for row in cur.fetchall():
    print(f'{row[0]} | {row[1]} | {row[2]}')
conn.close()
"

# Reset a failed job to pending
docker exec charm-strategy-test python3 -c "
import psycopg2
import os
conn = psycopg2.connect(
    host=os.environ.get('POSTGRES_HOST'),
    port=os.environ.get('POSTGRES_PORT', '5432'),
    database=os.environ.get('POSTGRES_DB', 'postgres'),
    user=os.environ.get('POSTGRES_USER'),
    password=os.environ.get('POSTGRES_PASSWORD')
)
cur = conn.cursor()
cur.execute(\"UPDATE strategy_generation_jobs SET status = 'pending', error_message = NULL WHERE id = 'JOB_UUID_HERE'\")
conn.commit()
print('Job reset to pending')
conn.close()
"
```

### Volume Management

```bash
# List volumes
docker volume ls

# Inspect credential volume
docker volume inspect charm-claude-credentials

# DANGER: Delete credential volume (requires re-auth)
docker volume rm charm-claude-credentials
```

## Troubleshooting

### "Invalid API key - Please run /login"

**Cause:** OAuth tokens have expired or are missing.

**Fix:**
```bash
docker exec -it charm-strategy-test claude /login
# Complete OAuth flow in browser
```

Then reset any failed jobs:
```bash
docker exec charm-strategy-test python3 -c "
import psycopg2
import os
conn = psycopg2.connect(host=os.environ.get('POSTGRES_HOST'), port=os.environ.get('POSTGRES_PORT', '5432'), database=os.environ.get('POSTGRES_DB', 'postgres'), user=os.environ.get('POSTGRES_USER'), password=os.environ.get('POSTGRES_PASSWORD'))
cur = conn.cursor()
cur.execute(\"UPDATE strategy_generation_jobs SET status = 'pending', error_message = NULL WHERE status = 'failed' AND error_message LIKE '%API key%'\")
print(f'Reset {cur.rowcount} jobs')
conn.commit()
conn.close()
"
```

### "the input device is not a TTY"

**Cause:** Running interactive command without `-it` flag.

**Fix:** Always use `-it` for interactive commands:
```bash
docker exec -it charm-strategy-test claude /login
```

### Container Not Processing Jobs

**Check 1:** Is the container running?
```bash
docker ps --filter "name=charm-strategy"
```

**Check 2:** Are there pending jobs?
```bash
docker exec charm-strategy-test python3 -c "
import psycopg2, os
conn = psycopg2.connect(host=os.environ.get('POSTGRES_HOST'), port=os.environ.get('POSTGRES_PORT', '5432'), database=os.environ.get('POSTGRES_DB', 'postgres'), user=os.environ.get('POSTGRES_USER'), password=os.environ.get('POSTGRES_PASSWORD'))
cur = conn.cursor()
cur.execute(\"SELECT COUNT(*) FROM strategy_generation_jobs WHERE status = 'pending'\")
print(f'Pending jobs: {cur.fetchone()[0]}')
conn.close()
"
```

**Check 3:** Recent logs showing errors?
```bash
docker logs --since 2m charm-strategy-test
```

### Database Connection Failed

**Cause:** Network or credential issues.

**Fix:** Verify database connectivity:
```bash
docker exec charm-strategy-test python3 -c "
import psycopg2
import os
try:
    conn = psycopg2.connect(
        host=os.environ.get('POSTGRES_HOST'),
        port=os.environ.get('POSTGRES_PORT', '5432'),
        database=os.environ.get('POSTGRES_DB', 'postgres'),
        user=os.environ.get('POSTGRES_USER'),
        password=os.environ.get('POSTGRES_PASSWORD')
    )
    print('Connection successful')
    conn.close()
except Exception as e:
    print(f'Connection failed: {e}')
"
```

## Environment Variables

| Variable | Purpose | Example |
|----------|---------|---------|
| `POSTGRES_HOST` | Database host | `31.97.142.123` |
| `POSTGRES_PORT` | Database port | `5432` |
| `POSTGRES_DB` | Database name | `postgres` |
| `POSTGRES_USER` | Database user | `postgres` |
| `POSTGRES_PASSWORD` | Database password | (secret) |

## Files in Container

| Path | Purpose |
|------|---------|
| `/app/strategy_worker.py` | Main worker daemon |
| `/app/strategy_mcp/server.py` | MCP tools server |
| `/app/strategy_mcp_config.json` | MCP configuration |
| `/app/.claude/skills/generate-strategy.md` | Claude skill instructions |
| `/home/claude/.claude/.credentials.json` | OAuth credentials (volume) |

## Related

- [[index]] - Deployment overview
- [[../architecture/claude-code-worker]] - Worker architecture
- [[../features/strategy-generation]] - Strategy generation feature
- [[../infrastructure/vps]] - VPS configuration
