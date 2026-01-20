---
title: Claude Code Worker Architecture
created: 2026-01-16
updated: 2026-01-20
tags: [architecture, claude-code, worker, mcp]
---

# Claude Code Worker Architecture

How Claude Code workers integrate with Charm Email OS for AI-powered generation.

## Overview

Workers poll the database for pending jobs, then spawn Claude Code subprocesses to execute AI tasks. Claude Code communicates with the database through MCP (Model Context Protocol) tools.

### Fully Autonomous Execution

**Key Design Principle:** Workers run without any human approval during execution.

| Aspect | Design |
|--------|--------|
| MCP Tool Calls | `--dangerously-skip-permissions` allows all calls without confirmation |
| Data Flow | Claude reads context from DB → generates output → writes directly to DB |
| User Interaction | None during processing |
| Human Review | ONLY on frontend (approving/denying generated content) |

**Purpose:** This creates a **restriction layer** for the team:
- Team members interact with Claude's output through the frontend dashboard
- They don't run Claude Code directly
- AI generates suggestions autonomously
- Humans review and approve through the UI

This ensures consistent, auditable workflows where every AI-generated item goes through human review before use.

```
┌─────────────────────────────────────────────────────────────────┐
│                      WORKER ARCHITECTURE                        │
└─────────────────────────────────────────────────────────────────┘

  ┌─────────────────────────────────────────────────────────────┐
  │                   PostgreSQL Database                        │
  │                                                              │
  │  ┌─────────────────┐         ┌─────────────────────┐       │
  │  │ *_generation_   │  READ   │      results        │       │
  │  │     jobs        │◄────────│    (domains /       │       │
  │  │ status=pending  │         │    suggestions)     │       │
  │  └────────┬────────┘         └──────────▲──────────┘       │
  └───────────┼─────────────────────────────┼──────────────────┘
              │ POLL                        │ INSERT
              ▼                             │
  ┌───────────────────────────────────────────────────────────┐
  │                     Python Worker                          │
  │                   (domain_worker.py)                       │
  │                                                            │
  │  while True:                                               │
  │    job = get_pending_job()      # Poll DB                  │
  │    if job:                                                 │
  │      spawn_claude_code(job)     # Subprocess               │
  │    else:                                                   │
  │      sleep(5)                   # Wait                     │
  └───────────────────────┬────────────────────────────────────┘
                          │ subprocess.run()
                          ▼
  ┌───────────────────────────────────────────────────────────┐
  │                     Claude Code CLI                        │
  │                                                            │
  │  claude -p "/generate-domain-suggestions client_id=..."   │
  │         --dangerously-skip-permissions                     │
  │         --mcp-config mcp_config.json                       │
  │                                                            │
  │  ┌─────────────────────────────────────────────────────┐  │
  │  │  Loads Skill: generate-domain-suggestions.md        │  │
  │  │                                                     │  │
  │  │  1. Call get_client_context() MCP tool              │  │
  │  │  2. Generate domain suggestions                     │  │
  │  │  3. Call save_domain_suggestion() for each          │  │
  │  │  4. Call complete_job() when done                   │  │
  │  └─────────────────────────────────────────────────────┘  │
  └───────────────────────┬────────────────────────────────────┘
                          │ MCP Protocol (stdio)
                          ▼
  ┌───────────────────────────────────────────────────────────┐
  │                    MCP Server                              │
  │                  (domain_mcp/server.py)                    │
  │                                                            │
  │  Tools:                                                    │
  │  - get_client_context(client_id) → client + domains data  │
  │  - save_domain_suggestion(job_id, domain, ...) → INSERT   │
  │  - complete_job(job_id) → UPDATE status='completed'       │
  │  - get_feedback_summary(client_id) → approved/denied      │
  └───────────────────────────────────────────────────────────┘
```

## Domain Generation Worker

### Files

| File | Purpose |
|------|---------|
| [domain_worker.py](../../domain_worker.py) | Main worker daemon |
| [domain_mcp/server.py](../../domain_mcp/server.py) | MCP tools server |
| [mcp_config.json](../../mcp_config.json) | MCP server configuration |
| [.claude/skills/generate-domain-suggestions.md](../../.claude/skills/generate-domain-suggestions.md) | Claude skill instructions |

### Worker Flow

1. **Startup**: Worker connects to database, ensures `domain_generation_jobs` table exists
2. **Poll Loop**: Every 5 seconds, checks for `status='pending'` jobs
3. **Job Pickup**: Updates job to `status='processing'`, `started_at=NOW()`
4. **Spawn Claude**: Runs `claude -p "/generate-domain-suggestions ..."` subprocess
5. **Completion**: MCP tool marks job as `status='completed'`
6. **Error Handling**: Worker marks job as `status='failed'` with error message

### Claude Command

```bash
claude -p "/generate-domain-suggestions client_id={uuid} job_id={uuid} count=10" \
       --dangerously-skip-permissions \
       --mcp-config mcp_config.json
```

| Flag | Purpose |
|------|---------|
| `-p` | Prompt/skill to execute |
| `--dangerously-skip-permissions` | Allow MCP tool calls without confirmation |
| `--mcp-config` | Path to MCP server configuration |

### MCP Tools

#### get_client_context

Get full context for a client including onboarding data and existing domains.

**Input:**
```json
{ "client_id": "uuid" }
```

**Returns:**
```json
{
  "client_id": "uuid",
  "client_name": "Checkout Components",
  "has_onboarding": false,
  "onboarding_data": {},
  "industry": "E-commerce",
  "product": "Checkout optimization",
  "workspace_id": "uuid",
  "total_domains": 5,
  "existing_domains": ["getcc.com", "trycc.com"],
  "approved_domains": ["getcc.com"],
  "denied_domains": ["badcc.com"],
  "domain_pattern": "cc.com",
  "used_prefixes": ["get", "try", "use"],
  "generation_mode": "pattern_fallback"
}
```

#### save_domain_suggestion

Save a single domain suggestion for human review.

**Input:**
```json
{
  "job_id": "uuid",
  "domain_name": "launchcc.com",
  "rationale": "Action verb 'launch' implies starting, professional feel",
  "legitimacy_score": 0.85
}
```

**Returns:** Success message or skip message if domain exists.

#### complete_job

Mark a generation job as complete.

**Input:**
```json
{ "job_id": "uuid" }
```

**Returns:** Success message.

#### get_feedback_summary

Get summary of human feedback on previous suggestions.

**Input:**
```json
{ "client_id": "uuid" }
```

**Returns:**
```json
{
  "approved_count": 5,
  "denied_count": 2,
  "approved_examples": [
    { "domain": "getcc.com", "rationale": "..." }
  ],
  "denied_domains": [
    { "domain": "badcc.com", "reason": "Too generic" }
  ],
  "patterns_to_avoid": ["bad", "spam"]
}
```

### Skill Instructions

The skill file [.claude/skills/generate-domain-suggestions.md](../../.claude/skills/generate-domain-suggestions.md) tells Claude how to:

1. Get client context via MCP tool
2. Determine generation mode (onboarding vs pattern fallback)
3. Generate professional domain names
4. Score each domain for legitimacy (0.7+ is good)
5. Save each suggestion via MCP tool
6. Mark job as complete

**Generation Modes:**

| Mode | Trigger | Strategy |
|------|---------|----------|
| Onboarding | `has_onboarding: true` | Creative domains based on product/industry |
| Pattern Fallback | `has_onboarding: false` | New prefixes + existing `domain_pattern` |

**Prefix Categories (Pattern Fallback):**
- Action Verbs: launch, ignite, spark, fuel, drive
- Growth Words: rise, lift, climb, soar, leap, surge
- Positive Words: ace, win, hit, yes, now, go
- Professional: pro, prime, core, key, main, lead
- Tech/Modern: neo, next, new, fresh, hot, cool

### Environment Variables

| Variable | Purpose | Default |
|----------|---------|---------|
| `POSTGRES_HOST` | Database host | `localhost` |
| `POSTGRES_PORT` | Database port | `5432` |
| `POSTGRES_DB` | Database name | `postgres` |
| `POSTGRES_USER` | Database user | `postgres` |
| `POSTGRES_PASSWORD` | Database password | (empty) |
| `POLL_INTERVAL` | Seconds between polls | `5` |

### Running the Worker

```bash
# Set environment variables
export POSTGRES_HOST=aws-0-us-east-1.pooler.supabase.com
export POSTGRES_PORT=6543
export POSTGRES_DB=postgres
export POSTGRES_USER=postgres.lhnzdotfevttijwyfcib
export POSTGRES_PASSWORD=your_password

# Run worker
python domain_worker.py
```

## Strategy Generation Worker (Implemented)

**Status:** Working (2026-01-20)

The strategy generation worker follows the same pattern for AI-powered email campaign generation. It runs locally via Docker Desktop, connecting to the VPS PostgreSQL database.

### Current Deployment

| Aspect | Configuration |
|--------|---------------|
| Container | `charm-strategy-test` |
| Image | `charm-strategy-worker:local` |
| Database | VPS PostgreSQL (31.97.142.123:5432) |
| Authentication | Claude Max subscription via OAuth |
| Credential Volume | `charm-claude-credentials` |

### Files

| File | Purpose | Status |
|------|---------|--------|
| `strategy_worker.py` | Main worker daemon | Working |
| `strategy_mcp/server.py` | MCP tools server | Working |
| `strategy_mcp_config.json` | MCP server configuration | Working |
| `.claude/skills/generate-strategy.md` | Claude skill instructions | Working |
| `Dockerfile.strategy-worker` | Docker image definition | Working |

### MCP Tools

| Tool | Purpose | Status |
|------|---------|--------|
| `get_client_context` | Get onboarding data, personas, segments | Implemented |
| `get_feedback_summary` | Get approved/denied suggestions | Implemented |
| `save_campaign_variant` | Save email variant for review | Implemented |
| `complete_job` | Mark generation job complete | Implemented |

### Skill Integration

**Important:** The Cold Email Skill v2.0 is **embedded directly in the prompt** (not loaded via `/skill-name` syntax) because the worker runs non-interactively. The full skill content is included in `strategy_worker.py`.

Reference location:
```
D:\Work\Claude Campaign Copywriting Skill-20251120T015618Z-1-001\
  └── Claude Campaign Copywriting Skill\
      ├── cold_email_v2_skill.txt      ← Core philosophy + workflow
      ├── qa_checklist_md.txt          ← 0-100 scoring rubric
      ├── examples_v2_md.txt           ← 10 annotated examples
```

**Key Principles:**
1. Shorter & Punchier (50-90 words)
2. Research IS the personalization
3. Earn replies, not meetings
4. Every word earns its place

**QA Scoring:**
- Situation Recognition: 25 pts
- Value Clarity: 25 pts
- Personalization Quality: 20 pts
- CTA Effort: 15 pts
- Punchiness: 10 pts
- Subject Line: 5 pts

### Running the Strategy Worker

See [[../deployment/local-docker]] for complete setup instructions.

**Quick commands:**
```bash
# Check if running
docker ps --filter "name=charm-strategy"

# View logs
docker logs -f charm-strategy-test

# Re-authenticate (when OAuth expires)
docker exec -it charm-strategy-test claude /login
```

### Authentication Persistence

OAuth credentials persist in the Docker named volume `charm-claude-credentials`:

| Token Type | Lifespan | Behavior |
|------------|----------|----------|
| Access Token | ~1 hour | Auto-refreshes while worker runs |
| Refresh Token | ~30 days | Requires re-auth when expired |

**When "Invalid API key" error appears:**
1. Run `docker exec -it charm-strategy-test claude /login`
2. Complete OAuth in browser
3. Reset failed jobs to pending

## Related

- [[../deployment/local-docker]] - Local Docker setup and authentication
- [[../features/strategy-generation]] - Strategy generation feature details
- [[data-flow]] - How data moves through system
- [[api-endpoints]] - API routes for job management
- [[../database/schema]] - Database tables for jobs
