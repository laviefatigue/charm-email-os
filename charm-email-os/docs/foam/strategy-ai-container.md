# Strategy AI Container

**Purpose-built Docker container for autonomous email strategy generation using Claude Code.**

## Overview

The `charm-strategy-ai` container runs Claude Code with the Cold Email v2.0 skill to generate email campaign variants. It operates as a **batch job** - runs once with arguments, generates strategies, writes to database, and exits.

```
┌─────────────────────────────────────────────────────────────────┐
│                    charm-strategy-ai Container                   │
│                                                                 │
│  ┌──────────────────┐  ┌──────────────────┐  ┌───────────────┐ │
│  │ Claude Code CLI  │  │ Strategy Skill   │  │  MCP Server   │ │
│  │ (authenticated)  │  │ (Cold Email v2)  │  │ (DB interface)│ │
│  └────────┬─────────┘  └────────┬─────────┘  └───────┬───────┘ │
│           │                     │                     │         │
│           └─────────────────────┼─────────────────────┘         │
│                                 │                               │
│                    ┌────────────▼────────────┐                  │
│                    │  /generate-strategy     │                  │
│                    │  client_id=X job_id=Y   │                  │
│                    └────────────┬────────────┘                  │
│                                 │                               │
└─────────────────────────────────┼───────────────────────────────┘
                                  │
                                  ▼
                        PostgreSQL (Supabase)
                   strategy_suggestions table
```

## Deployment Details

| Property | Value |
|----------|-------|
| **Coolify App UUID** | `n008gg4c88kgw4g48wcckk0k` |
| **Image Name** | `n008gg4c88kgw4g48wcckk0k:latest` |
| **VPS IP** | `31.97.142.123` |
| **Base Image** | `debian:bookworm-slim` |
| **Claude CLI Path** | `/usr/local/bin/claude` |
| **Claude CLI Version** | `2.1.9` |
| **Account** | `Opus 4.5 · Claude Max · elliott@laviefatigue.com's Organization` |

## Container Contents

| Component | Path | Purpose |
|-----------|------|---------|
| Claude Code CLI | `/usr/local/bin/claude` | Executes strategy skill |
| Strategy Skill | `/app/.claude/skills/generate-strategy.md` | Cold Email v2.0 instructions |
| MCP Server | `/app/strategy_mcp/server.py` | Database interface tools |
| MCP Config | `/app/strategy_mcp_config.json` | Server configuration |
| Entrypoint | `/app/docker-entrypoint.sh` | Invokes Claude with args |
| Auth Credentials | `/root/.claude/` (volume mount) | Persisted Claude login |

## Volume Mount Architecture

**Critical Fix**: The Claude CLI binary is copied to `/usr/local/bin/` to avoid volume mount shadowing.

```dockerfile
# Install Claude Code CLI (installs to ~/.local/bin/claude on Linux)
RUN curl -fsSL https://claude.ai/install.sh | bash

# CRITICAL: Copy to /usr/local/bin to avoid volume mount shadowing
# The volume mount (-v /root/.claude:/root/.claude) for credentials
# would otherwise hide any binaries in ~/.claude/bin/
RUN cp /root/.local/bin/claude /usr/local/bin/claude && \
    chmod +x /usr/local/bin/claude
```

### Why This Matters

| Layer | Without Fix | With Fix |
|-------|-------------|----------|
| Build time | Claude at `~/.local/bin/claude` | Claude copied to `/usr/local/bin/claude` |
| Runtime mount | `-v /root/.claude:/root/.claude` shadows nothing | Mount only contains credentials |
| Result | `claude: command not found` | Claude CLI accessible |

## Authentication

Authentication was performed on **2026-01-16** via Coolify Server Terminal.

### One-Time Setup Process

1. **Run container interactively**:
   ```bash
   docker run -it --rm \
     -v /root/.claude:/root/.claude \
     --entrypoint bash \
     n008gg4c88kgw4g48wcckk0k:latest
   ```

2. **Inside container, run login**:
   ```bash
   claude /login
   ```

3. **Select login method**: `1. Claude account with subscription`

4. **Complete OAuth flow**:
   - Open the provided URL in browser
   - Log in with Claude Max account
   - Copy the authorization code (includes `#` fragment)
   - Paste into terminal

5. **Trust workspace**: Select `Yes, proceed` for `/app` directory

6. **Exit container**: Credentials persist at `/root/.claude/` on host

### Verification

```bash
# Check credentials exist on VPS host
ls -la /root/.claude/
# Should contain: .credentials.json, settings.json, etc.
```

## Usage

### Basic Invocation

```bash
docker run --rm \
  -e POSTGRES_HOST=aws-0-us-east-1.pooler.supabase.com \
  -e POSTGRES_PORT=6543 \
  -e POSTGRES_DB=postgres \
  -e POSTGRES_USER=postgres.lhnzdotfevttijwyfcib \
  -e POSTGRES_PASSWORD=<password> \
  -v /root/.claude:/root/.claude \
  n008gg4c88kgw4g48wcckk0k:latest \
  <client_id> <job_id> [submission_id]
```

### Arguments

| Argument | Required | Description |
|----------|----------|-------------|
| `client_id` | Yes | UUID of the client |
| `job_id` | Yes | UUID of the generation job |
| `submission_id` | No | UUID of specific onboarding submission |

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `POSTGRES_HOST` | Yes | - | Supabase host |
| `POSTGRES_PORT` | No | `5432` | Database port |
| `POSTGRES_DB` | No | `postgres` | Database name |
| `POSTGRES_USER` | Yes | - | Database user |
| `POSTGRES_PASSWORD` | Yes | - | Database password |

## MCP Tools

The container exposes these tools to Claude Code via MCP server:

| Tool | Purpose |
|------|---------|
| `get_client_context(client_id)` | Fetch client info, onboarding data, personas, segments |
| `get_feedback_summary(client_id)` | Get approved/denied variants, revision requests |
| `save_campaign_variant(...)` | Save generated email variant to DB |
| `complete_job(job_id)` | Mark generation job as complete |

## Data Flow

```
1. Trigger creates job in strategy_generation_jobs table
                    │
                    ▼
2. Container runs: claude -p "/generate-strategy client_id=X job_id=Y"
                    │
                    ▼
3. Claude reads client context via MCP: get_client_context()
                    │
                    ▼
4. Claude generates 3 variants using Cold Email v2.0 skill
                    │
                    ▼
5. Each variant saved via MCP: save_campaign_variant()
                    │
                    ▼
6. Job marked complete: complete_job()
                    │
                    ▼
7. Frontend displays variants for human review
```

## Files

| File | Location | Purpose |
|------|----------|---------|
| `Dockerfile.strategy-ai` | Project root | Container definition |
| `docker-entrypoint.sh` | Project root | Entry script |
| `requirements-mcp.txt` | Project root | Python MCP deps |
| `strategy_mcp/server.py` | Project root | MCP server implementation |
| `strategy_mcp_config.json` | Project root | MCP configuration |
| `.claude/skills/generate-strategy.md` | Project root | Strategy generation skill |

## Troubleshooting

### `claude: command not found`

**Cause**: Volume mount shadowing the Claude binary.

**Fix**: Ensure Dockerfile copies Claude to `/usr/local/bin/`:
```dockerfile
RUN cp /root/.local/bin/claude /usr/local/bin/claude
```

### OAuth Error 400

**Cause**: Authorization code expired or already used.

**Fix**: Get a fresh OAuth URL by running `claude /login` again. Codes expire quickly.

### Terminal Disconnection During Auth

**Cause**: Coolify terminal timeout or network issue.

**Fix**: Reconnect, restart container, run `claude /login` again with fresh code.

### Container Exits Immediately

**Cause**: Missing arguments or environment variables.

**Fix**: Ensure all required args (`client_id`, `job_id`) and env vars are provided.

## Related

- [[infrastructure]] - VPS and deployment infrastructure
- [[campaigns]] - Campaign management
- [[workflows]] - Generation workflow
- [[health-monitoring]] - System monitoring

---
Tags: #infrastructure #docker #claude-code #ai #vps #deployment
