---
title: Docker Compose Reference
created: 2026-02-10
updated: 2026-02-10
tags: [docker, compose, reference]
---

# Docker Compose Reference

All docker-compose files in the Charm Email OS project and their purposes.

## Compose Files Overview

| File | Purpose | When to Use |
|------|---------|-------------|
| `docker-compose.local.yml` | **Local development stack** | Daily development |
| `docker-compose.yml` | Production reference | Coolify uses this |
| `docker-compose.strategy-worker.yml` | Standalone strategy worker | Worker-only testing |
| `docker-compose.strategy-local.yml` | **Strategy worker local testing** | Skill development, safe testing |
| `docker-compose.domain-worker.yml` | Standalone domain worker | Worker-only testing |
| `docker-compose.spintax-worker.yml` | Standalone spintax worker | Worker-only testing |

## docker-compose.local.yml (Primary)

**Purpose**: Full local development stack mirroring production.

**Location**: `D:\Work\charm-email-os\docker-compose.local.yml`

### Services

```yaml
services:
  postgres:         # Local PostgreSQL database
  charm-api:        # FastAPI backend
  charm-frontend:   # Next.js frontend
  # strategy-worker:  # (optional, uncomment to enable)
  # domain-worker:    # (optional, uncomment to enable)
  # spintax-worker:   # (optional, uncomment to enable)
  # purchase-worker:  # (optional, uncomment to enable)
```

### Usage

```bash
# Start all services
docker compose -f docker-compose.local.yml up -d

# Start specific services
docker compose -f docker-compose.local.yml up -d postgres charm-api

# View logs
docker compose -f docker-compose.local.yml logs -f

# Stop services (keep data)
docker compose -f docker-compose.local.yml down

# Stop and delete data
docker compose -f docker-compose.local.yml down -v

# Rebuild after code changes
docker compose -f docker-compose.local.yml up -d --build
```

### Service Details

#### postgres

```yaml
postgres:
  image: postgres:15-alpine
  container_name: charm-postgres
  ports:
    - "5433:5432"  # External 5433, Internal 5432
  environment:
    POSTGRES_DB: postgres
    POSTGRES_USER: postgres
    POSTGRES_PASSWORD: localdevpassword
  volumes:
    - charm-postgres-data:/var/lib/postgresql/data
    - ./docker/init:/docker-entrypoint-initdb.d:ro
```

**Notes**:
- Uses port 5433 to avoid conflict with local PostgreSQL
- Init scripts run automatically on first start
- Data persists in `charm-postgres-data` volume

#### charm-api

```yaml
charm-api:
  build:
    context: ./api
    dockerfile: Dockerfile
  container_name: charm-api
  ports:
    - "8000:8000"
  environment:
    - POSTGRES_HOST=postgres
    - POSTGRES_PORT=5432
    - POSTGRES_DB=postgres
    - POSTGRES_USER=postgres
    - POSTGRES_PASSWORD=localdevpassword
    - CORS_ORIGINS=["http://localhost:3000","http://charm-frontend:3000"]
  depends_on:
    postgres:
      condition: service_healthy
```

**Notes**:
- Connects to `postgres` service (internal Docker network)
- CORS configured for both localhost and Docker network access

#### charm-frontend

```yaml
charm-frontend:
  build:
    context: ./charm-email-os
    dockerfile: Dockerfile
    args:
      NEXT_PUBLIC_API_URL: http://localhost:8000
  container_name: charm-frontend
  ports:
    - "3000:3000"
  environment:
    - NODE_ENV=production
    - NEXT_PUBLIC_API_URL=http://localhost:8000
  depends_on:
    charm-api:
      condition: service_healthy
```

**Notes**:
- API URL passed at build time via args
- Waits for API to be healthy before starting

## docker-compose.strategy-worker.yml

**Purpose**: Standalone strategy worker for isolated testing.

**Location**: `D:\Work\charm-email-os\docker-compose.strategy-worker.yml`

### Usage

```bash
# Start standalone worker
docker compose -f docker-compose.strategy-worker.yml up -d

# Authenticate
docker exec -it charm-spintax-worker claude /login

# View logs
docker compose -f docker-compose.strategy-worker.yml logs -f
```

### Configuration

```yaml
services:
  strategy-worker:
    build:
      context: .
      dockerfile: Dockerfile.strategy-worker
    environment:
      - POSTGRES_HOST=${POSTGRES_HOST}
      - POSTGRES_PORT=${POSTGRES_PORT:-5432}
      - POSTGRES_DB=${POSTGRES_DB:-postgres}
      - POSTGRES_USER=${POSTGRES_USER}
      - POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
      - POLL_INTERVAL=${POLL_INTERVAL:-5}
      - CLAUDE_ACCOUNT=${CLAUDE_ACCOUNT:-}
    volumes:
      - charm-claude-credentials:/home/claude/.claude
```

**Notes**:
- Requires environment variables (set via `.env` or Coolify)
- Shares credentials volume with other workers

## docker-compose.strategy-local.yml

**Purpose**: Safe local testing of strategy worker without affecting production database.

**Location**: `D:\Work\charm-email-os\docker-compose.strategy-local.yml`

### Key Features

- **LOCAL_MODE**: Saves output to filesystem instead of production database
- **SQLite tracking**: Uses SQLite for job tracking only
- **Live skill editing**: Mounts skill files for real-time changes
- **Read-only production access**: Connects to production DB only to fetch client context

### Usage

```bash
# 1. Start worker
docker compose -f docker-compose.strategy-local.yml up -d --build

# 2. Create test job
python scripts/test_strategy_generation.py

# 3. Monitor output
docker logs -f charm-strategy-test

# 4. Validate results
python scripts/validate_output.py
```

### Configuration

```yaml
services:
  strategy-worker:
    container_name: charm-strategy-test
    environment:
      # LOCAL MODE - saves to filesystem, not production database
      - STRATEGY_LOCAL_MODE=true
      - STRATEGY_OUTPUT_DIR=/app/test-output
      # SQLite for job tracking only
      - SQLITE_DB_PATH=/app/test-output/jobs.db
      # Production DB for READ-ONLY client context
      - POSTGRES_HOST=31.97.142.123
      - POSTGRES_PORT=5432
      # ...
    volumes:
      # Test output
      - ./test-output:/app/test-output
      # Claude credentials
      - ${USERPROFILE}/.claude:/home/claude/.claude
      # Skill files for live editing (read-only)
      - ./.claude/skills:/app/.claude/skills:ro
```

### Output Location

All generated output is saved to `./test-output/`:

```
test-output/
├── jobs.db              # SQLite job tracking
├── {job-id}/            # Per-job output
│   ├── strategy.json    # Generated strategy
│   ├── sequences/       # Email sequences
│   └── logs/            # Execution logs
```

**Notes**:
- Use for skill development and testing
- Safe to run repeatedly without affecting production
- Mount skill files with `:ro` to prevent accidental writes
- Test output can be reviewed before production deployment

## Volumes

### charm-postgres-data

Persists PostgreSQL data between restarts.

```yaml
volumes:
  charm-postgres-data:
    name: charm-postgres-data
```

### charm-claude-credentials

Persists Claude Code OAuth credentials.

```yaml
volumes:
  charm-claude-credentials:
    external: true  # Must exist before container starts
```

**Create volume manually**:
```bash
docker volume create charm-claude-credentials
```

## Networks

### charm-network-local

Internal Docker network for local development.

```yaml
networks:
  charm-network:
    driver: bridge
    name: charm-network-local
```

**Notes**:
- All services connected to this network
- Services can reach each other by container name

## Environment Variables

See [[environment-variables]] for complete reference.

## Common Operations

### Start Everything

```bash
docker compose -f docker-compose.local.yml up -d
```

### Start Backend Only (for frontend hot reload)

```bash
docker compose -f docker-compose.local.yml up -d postgres charm-api
```

### Rebuild Single Service

```bash
docker compose -f docker-compose.local.yml build --no-cache charm-api
docker compose -f docker-compose.local.yml up -d charm-api
```

### View Service Logs

```bash
# All services
docker compose -f docker-compose.local.yml logs -f

# Single service
docker compose -f docker-compose.local.yml logs -f charm-api
```

### Reset Database

```bash
docker compose -f docker-compose.local.yml down -v
docker compose -f docker-compose.local.yml up -d
```

### Enable Optional Workers

Edit `docker-compose.local.yml` and uncomment the worker services:

```yaml
# Uncomment these lines:
strategy-worker:
  build:
    context: .
    dockerfile: Dockerfile.strategy-worker
  # ... rest of config
```

Then:
```bash
docker compose -f docker-compose.local.yml up -d
```

## Related

- [[file-locations]] - Where files live
- [[environment-variables]] - All environment variables
- [[workers]] - Worker documentation
- [[troubleshooting]] - Common issues
