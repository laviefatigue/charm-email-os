---
title: Strategy Worker Setup
created: 2026-02-12
updated: 2026-02-12
tags: [worker, strategy, claude, ai, generation]
---

# Strategy Worker Setup

The Strategy Worker generates 4-campaign strategy cycles using Claude Code. It implements a phased generation approach for reliability.

## Prerequisites

- Docker Desktop running
- Claude Code account with valid subscription (ClaudeCodeMax recommended)
- Claude credentials in `~/.claude` directory

## Architecture

### Phased Generation

The worker uses a 2-phase approach to avoid timeouts:

```
Phase 1: SCAFFOLD (~3 min)
├── Creates campaign_cycle record
├── Creates cycle_strategy_config (ICP, variables)
└── Creates 4 campaign_document stubs (no email content)

Phase 2: CAMPAIGN COPY (4 phases × ~3 min each)
├── Campaign 1: Custom Signal (hiring/funding triggers)
├── Campaign 2: Persona Pain (role challenges)
├── Campaign 3: Case Study (social proof)
└── Campaign 4: Risk/Efficiency (business outcomes)
```

### Data Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                     STRATEGY WORKER                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  1. Poll for pending jobs/phases                                 │
│     SELECT * FROM strategy_generation_phases                     │
│     WHERE status = 'pending' ORDER BY created_at                 │
│                                                                  │
│  2. Spawn Claude Code with skill                                 │
│     claude -p "Generate scaffold..."                             │
│            --mcp-config strategy_mcp_config.json                 │
│            --dangerously-skip-permissions                        │
│                                                                  │
│  3. Claude Code executes skill                                   │
│     ├── get_client_context() → Client + submission data          │
│     ├── get_feedback_summary() → Previous approvals/denials      │
│     └── save_cycle_scaffold() → Write to database                │
│                                                                  │
│  4. Worker creates campaign phases                               │
│     INSERT INTO strategy_generation_phases                       │
│     (phase_type='campaign_copy', campaign_number=1..4)          │
│                                                                  │
│  5. Process each campaign phase                                  │
│     claude -p "Generate campaign 1 copy..."                      │
│     └── save_campaign_copy() → Update campaign_document          │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `POSTGRES_HOST` | postgres | Database host |
| `POSTGRES_PORT` | 5432 | Database port |
| `POSTGRES_DB` | postgres | Database name |
| `POSTGRES_USER` | postgres | Database user |
| `POSTGRES_PASSWORD` | - | Database password |
| `POLL_INTERVAL` | 5 | Seconds between job polls |
| `CLAUDE_ACCOUNT` | ClaudeCodeMax | Claude subscription account |
| `OAUTH_CHECK_INTERVAL` | 3600 | OAuth health check interval |
| `STRATEGY_PHASED_MODE` | true | Enable phased generation |
| `STRATEGY_LOCAL_MODE` | false | Write to files instead of DB |

### Docker Compose Configuration

```yaml
strategy-worker:
  build:
    context: .
    dockerfile: Dockerfile.strategy-worker
  container_name: charm-strategy-worker
  restart: unless-stopped
  environment:
    - POSTGRES_HOST=postgres
    - POSTGRES_PORT=5432
    - POSTGRES_DB=postgres
    - POSTGRES_USER=postgres
    - POSTGRES_PASSWORD=localdevpassword
    - POLL_INTERVAL=5
    - CLAUDE_ACCOUNT=ClaudeCodeMax
    - OAUTH_CHECK_INTERVAL=3600
    - STRATEGY_LOCAL_MODE=false
    - STRATEGY_PHASED_MODE=true
  volumes:
    # Mount Claude credentials from Windows user profile
    - ${USERPROFILE}/.claude:/home/claude/.claude
    # Mount skill files for live editing
    - ./.claude/skills:/app/.claude/skills:ro
  depends_on:
    postgres:
      condition: service_healthy
  networks:
    - charm-network
```

## Authentication

### Option 1: Mount Existing Credentials (Recommended)

If you have Claude Code configured on your host machine:

```yaml
volumes:
  - ${USERPROFILE}/.claude:/home/claude/.claude
```

The credentials at `~/.claude/.credentials.json` will be available inside the container.

### Option 2: Authenticate Inside Container

```bash
# Enter the container
docker exec -it charm-strategy-worker bash

# Login with OAuth
claude /login
# Follow browser flow

# Or use long-lived token
claude setup-token
# Copy token from browser

# Verify authentication
claude -p "Say OK" --max-turns 1
```

### Option 3: Pre-configure Credentials File

Create credentials file manually:

```bash
# On host machine
cat > ~/.claude/.credentials.json << 'EOF'
{
  "claudeAiOauth": {
    "accessToken": "YOUR_TOKEN_HERE",
    "expiresAt": 4102444800000,
    "scopes": ["user:inference", "user:profile", "user:sessions:claude_code"],
    "subscriptionType": "max"
  }
}
EOF
chmod 600 ~/.claude/.credentials.json
```

## MCP Server Configuration

The worker uses the Strategy MCP server for database operations:

### MCP Tools

| Tool | Purpose |
|------|---------|
| `get_client_context` | Fetch client + onboarding submission data |
| `get_feedback_summary` | Get previous approval/denial patterns |
| `save_cycle_scaffold` | Create cycle, config, campaign stubs |
| `get_campaign_context` | Get scaffold context for campaign phase |
| `save_campaign_copy` | Save generated emails to campaign document |

### MCP Config File

```json
{
  "mcpServers": {
    "strategy": {
      "command": "python3",
      "args": ["/app/strategy_mcp/server.py"],
      "env": {
        "POSTGRES_HOST": "postgres",
        "POSTGRES_PORT": "5432",
        "POSTGRES_DB": "postgres",
        "POSTGRES_USER": "postgres",
        "POSTGRES_PASSWORD": "localdevpassword"
      }
    }
  }
}
```

## Skill Files

### Scaffold Skill

**File**: `.claude/skills/generate-strategy-scaffold.md`

Creates:
- ICP mapping (target, pain points, objections)
- Cycle variables (apply to all campaigns)
- 4 campaign stubs with angles and variables

### Campaign Copy Skill

**File**: `.claude/skills/generate-campaign-copy.md`

Creates:
- 4 email positions × 2-3 variants each
- QA scoring (6 dimensions)
- Strategy notes (callouts, enrichment, A/B testing)

## Operations

### Start the Worker

```bash
# Start with docker compose
docker compose -f docker-compose.local.yml up -d strategy-worker

# Check status
docker logs -f charm-strategy-worker
```

Expected startup output:
```
Strategy Generation Worker starting...
Database: postgres:5432/postgres
Poll interval: 5 seconds
PHASED_MODE: True
Loading phased skills...
OAuth token is valid ✓
Worker ready - polling for jobs...
```

### Trigger Generation

```bash
# 1. Create a cycle for the client
curl -X POST "http://localhost:8000/api/strategy/cycles/4bd07dc0-059a-448b-b6f4-3275d0c104a9" \
  -H "Content-Type: application/json" \
  -d '{}'

# Response: {"id": "cycle-uuid", ...}

# 2. Generate campaigns for the cycle
curl -X POST "http://localhost:8000/api/strategy/cycles/{cycle-uuid}/generate" \
  -H "Content-Type: application/json" \
  -d '{}'

# Response: {"job_id": "job-uuid", ...}
```

### Monitor Progress

```bash
# Check job phases
curl "http://localhost:8000/api/strategy/jobs/{job-uuid}/phases"

# Response includes:
# - Phase status (pending, processing, completed, failed)
# - Campaign names and angles
# - Progress percentage
# - Estimated time remaining
```

### Check Worker Logs

```bash
# Follow logs
docker logs -f charm-strategy-worker

# View recent logs
docker logs charm-strategy-worker --tail 50

# Check for errors
docker logs charm-strategy-worker 2>&1 | grep ERROR
```

## Troubleshooting

### "OAuth token is invalid"

Re-authenticate:

```bash
docker exec -it charm-strategy-worker bash
claude /login
exit
```

### "MCP server not found"

Check MCP config path:

```bash
docker exec charm-strategy-worker cat /app/strategy_mcp_config.json
```

### Phase stuck in "processing"

Check if Claude Code is running:

```bash
docker exec charm-strategy-worker ps aux | grep claude
```

Kill stuck process and retry:

```bash
docker exec charm-strategy-worker pkill -f claude
# Worker will auto-retry the phase
```

### Skill file not found

Verify skills are mounted:

```bash
docker exec charm-strategy-worker ls -la /app/.claude/skills/
```

### Database connection errors

Verify PostgreSQL is healthy:

```bash
docker exec charm-postgres pg_isready
```

## Files

| File | Purpose |
|------|---------|
| `strategy_worker.py` | Main worker script |
| `Dockerfile.strategy-worker` | Container definition |
| `strategy_mcp/server.py` | MCP server implementation |
| `strategy_mcp/__init__.py` | MCP module exports |
| `strategy_mcp_config.json` | MCP server configuration |
| `.claude/skills/generate-strategy-scaffold.md` | Phase 1 skill |
| `.claude/skills/generate-campaign-copy.md` | Phase 2 skill |

## Database Tables

| Table | Purpose |
|-------|---------|
| `strategy_generation_jobs` | Job queue and status |
| `strategy_generation_phases` | Phase tracking for phased generation |
| `campaign_cycles` | Cycle metadata |
| `cycle_strategy_config` | ICP mapping, variables, strategic focus |
| `campaign_documents` | Generated campaign content |

## Generation Timeline

| Phase | Duration | Description |
|-------|----------|-------------|
| Scaffold | ~3 min | ICP, variables, campaign stubs |
| Campaign 1 | ~3 min | Custom Signal (16 emails) |
| Campaign 2 | ~3 min | Persona Pain (16 emails) |
| Campaign 3 | ~3 min | Case Study (16 emails) |
| Campaign 4 | ~3 min | Risk/Efficiency (16 emails) |
| **Total** | **~15 min** | Complete 4-campaign cycle |

## Related

- [[quick-start]] - Complete Local Setup
- [[workers]] - All Workers Reference
- [[../features/strategy-generation]] - Strategy Generation Feature
- [[../architecture/claude-code-worker]] - Worker Architecture
