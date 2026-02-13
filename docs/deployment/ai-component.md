# Charm Strategy AI Component

> **Note**: This component runs locally via `docker-compose.local.yml`. VPS/Coolify deployments are deprecated.

Purpose-built Docker container for autonomous email strategy generation.

## Overview

The `charm-strategy-ai` container is a self-contained AI component that:

1. Receives job parameters (client_id, job_id)
2. Runs Claude Code with the pre-configured Cold Email v2.0 skill
3. Writes generated variants to PostgreSQL via MCP server
4. Exits when complete - no human interaction during execution

```
┌─────────────────────────────────────────────────────────────────┐
│              charm-strategy-ai Container                        │
│                                                                 │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐ │
│  │ Claude Code │  │  Strategy   │  │      MCP Server         │ │
│  │    CLI      │  │   Skill     │  │  (DB interface)         │ │
│  └──────┬──────┘  └──────┬──────┘  └───────────┬─────────────┘ │
│         └────────────────┼─────────────────────┘               │
│                          │                                      │
│                          ▼                                      │
│              /generate-strategy                                 │
│              client_id=X job_id=Y                               │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
                    PostgreSQL (Supabase)
                  strategy_suggestions table
```

## Container Contents

| Component | Path | Purpose |
|-----------|------|---------|
| Claude Code CLI | `/root/.claude/bin/claude` | Executes strategy skill |
| Strategy Skill | `/app/.claude/skills/generate-strategy.md` | Cold Email v2.0 instructions |
| MCP Server | `/app/strategy_mcp/server.py` | Database interface (4 tools) |
| MCP Config | `/app/strategy_mcp_config.json` | Server configuration |
| Entrypoint | `/app/docker-entrypoint.sh` | Job execution script |

## MCP Tools Available

The MCP server provides 4 tools for Claude:

1. **get_client_context(client_id)** - Fetch client data, onboarding, personas
2. **get_feedback_summary(client_id)** - Get human feedback history
3. **save_campaign_variant(job_id, ...)** - Save generated email variant
4. **complete_job(job_id)** - Mark job as ready for review

## Build

```bash
cd /opt/charm-email-os

# Build the container
docker build -t charm-strategy-ai:latest -f Dockerfile.strategy-ai .
```

## Authentication (One-Time Setup)

Claude Code requires authentication. Do this once on the VPS:

```bash
# Run interactive shell
docker run -it --rm \
    -v /root/.claude:/root/.claude \
    charm-strategy-ai:latest bash

# Inside container
claude /login
# Follow browser prompts to authenticate

# Exit - credentials persisted at /root/.claude on host
exit
```

## Usage

### Manual Execution

```bash
docker run --rm \
    -e POSTGRES_HOST=aws-0-us-east-1.pooler.supabase.com \
    -e POSTGRES_PORT=6543 \
    -e POSTGRES_DB=postgres \
    -e POSTGRES_USER=postgres.lhnzdotfevttijwyfcib \
    -e POSTGRES_PASSWORD=<password> \
    -v /root/.claude:/root/.claude \
    charm-strategy-ai:latest \
    <client_id> <job_id> [submission_id]
```

### Via Prefect Worker

The Prefect worker calls the container automatically:

```python
# strategy_worker_prefect.py
cmd = [
    "docker", "run", "--rm",
    "-e", f"POSTGRES_HOST={DB_CONFIG['host']}",
    "-e", f"POSTGRES_PORT={DB_CONFIG['port']}",
    "-e", f"POSTGRES_DB={DB_CONFIG['database']}",
    "-e", f"POSTGRES_USER={DB_CONFIG['user']}",
    "-e", f"POSTGRES_PASSWORD={DB_CONFIG['password']}",
    "-v", "/root/.claude:/root/.claude",
    "charm-strategy-ai:latest",
    client_id,
    job_id,
]
```

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| POSTGRES_HOST | Yes | Database host |
| POSTGRES_PORT | No | Database port (default: 5432) |
| POSTGRES_DB | Yes | Database name |
| POSTGRES_USER | Yes | Database user |
| POSTGRES_PASSWORD | Yes | Database password |

## Volume Mounts

| Host Path | Container Path | Purpose |
|-----------|----------------|---------|
| /root/.claude | /root/.claude | Claude authentication credentials |

## Integration with Prefect

Set `USE_DOCKER=true` in the Prefect worker environment:

```bash
# Start worker with Docker mode
USE_DOCKER=true prefect worker start --pool default-agent-pool
```

Or in systemd service:

```ini
[Service]
Environment=USE_DOCKER=true
Environment=PREFECT_API_URL=https://prefect.laviefatigue.com/api
ExecStart=/opt/charm-email-os/venv/bin/prefect worker start --pool default-agent-pool
```

## Execution Flow

1. Frontend: User clicks "Trigger Generation" on Profile page
2. API: Creates job in `strategy_generation_jobs` table (status: pending)
3. Prefect: Worker picks up job, calls `docker run charm-strategy-ai ...`
4. Container: Runs Claude Code with strategy skill
5. Claude: Calls MCP tools to get context, save variants, complete job
6. Database: Variants stored in `strategy_suggestions` (status: pending)
7. Frontend: User reviews variants on Strategy tab

## Troubleshooting

### Container won't start

```bash
# Check if image exists
docker images | grep charm-strategy-ai

# Rebuild if needed
docker build -t charm-strategy-ai:latest -f Dockerfile.strategy-ai .
```

### Authentication expired

```bash
# Re-authenticate
docker run -it --rm \
    -v /root/.claude:/root/.claude \
    charm-strategy-ai:latest bash

claude /login
exit
```

### Database connection failed

```bash
# Test connection from container
docker run --rm \
    -e POSTGRES_HOST=... \
    -e POSTGRES_PORT=... \
    -e POSTGRES_DB=... \
    -e POSTGRES_USER=... \
    -e POSTGRES_PASSWORD=... \
    charm-strategy-ai:latest bash -c "python3 -c 'import psycopg2; print(\"OK\")'"
```

### View container logs

```bash
# Run without --rm to keep container
docker run \
    -e POSTGRES_HOST=... \
    ... \
    charm-strategy-ai:latest \
    <client_id> <job_id>

# Check logs
docker logs <container_id>
```

## Updating the Container

When skill or MCP server changes:

```bash
cd /opt/charm-email-os
git pull

# Rebuild
docker build -t charm-strategy-ai:latest -f Dockerfile.strategy-ai .

# Test
docker run --rm \
    -e POSTGRES_HOST=... \
    ... \
    charm-strategy-ai:latest \
    <test_client_id> <test_job_id>
```

## Security Notes

- Claude credentials stored at `/root/.claude` on VPS host
- Database password passed via environment variable (not in image)
- Container runs as root (required for Claude CLI)
- Use Docker secrets in production for sensitive data
