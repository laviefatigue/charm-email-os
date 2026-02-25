---
title: AI Strategy Generation
created: 2026-01-16
updated: 2026-01-20
tags: [feature, strategy, ai, claude-code, implemented]
---

# AI Strategy Generation

**Status:** Implemented and Working (2026-01-20)
**Skill Version:** v2.0 Enhanced (429 lines) - Updated 2026-01-20

AI-powered email campaign variant generation using Claude Code and Cold Email Skill v2.0.

## Current State

| Component | Status | Location |
|-----------|--------|----------|
| Strategy Worker | Running | Local Docker (`charm-strategy-test`) |
| MCP Server | Working | `/app/strategy_mcp/server.py` |
| Frontend Component | Deployed | `CampaignSuggestions.tsx` |
| API Endpoints | Working | `/api/strategy/jobs`, `/api/strategy/suggestions` |

### Live Statistics (as of 2026-01-20)

| Metric | Value |
|--------|-------|
| Total Suggestions Generated | 9 |
| Pending Review | 7 |
| Approved | 1 |
| Denied | 1 |
| Average Score | 82-86 |

## Overview

When the "Generate More" button is clicked (or a job is created via API), the system:
1. Creates a `strategy_generation_job` with `status='pending'`
2. Local Docker worker polls DB, picks up the job
3. Worker spawns Claude Code with Cold Email Skill embedded in prompt
4. Claude calls MCP tools to read context and save variants
5. 3 email variants are saved to `strategy_suggestions` table
6. Frontend displays variants with Approve/Deny/Request Revision buttons
7. Human feedback is stored for future generation improvements

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  Frontend: "Generate More" Button Clicked                       │
│  Strategy Tab - CampaignSuggestions Component                   │
└────────────────────────┬────────────────────────────────────────┘
                         │ POST /api/strategy/jobs/{client_id}
                         ↓
┌─────────────────────────────────────────────────────────────────┐
│  API: INSERT INTO strategy_generation_jobs (status='pending')   │
│  Returns: job_id (e.g., f2b1f401-8d92-4b07-8abc-631dc01c3ad2)  │
└────────────────────────┬────────────────────────────────────────┘
                         │ Frontend polls job status
                         │ GET /api/strategy/jobs/{job_id}/status
                         │
                         │ Meanwhile, worker polls DB...
                         ↓
┌─────────────────────────────────────────────────────────────────┐
│  Strategy Worker (Local Docker: charm-strategy-test)            │
│  Location: strategy_worker.py                                   │
│                                                                 │
│  while True:                                                    │
│    job = get_pending_job()  # Poll every 5 seconds             │
│    if job:                                                      │
│      subprocess.run(["claude", "-p", prompt, ...])             │
│    else:                                                        │
│      sleep(5)                                                   │
└────────────────────────┬────────────────────────────────────────┘
                         │ Claude Code subprocess
                         ↓
┌─────────────────────────────────────────────────────────────────┐
│  Claude Code CLI                                                │
│                                                                 │
│  claude -p "{embedded skill + parameters}"                     │
│         --dangerously-skip-permissions                          │
│         --mcp-config /app/strategy_mcp_config.json             │
│                                                                 │
│  Executes steps:                                                │
│  1. Call get_client_context(client_id)                         │
│  2. Call get_feedback_summary(client_id)                       │
│  3. Generate 3 email variants using Cold Email Skill v2.0      │
│  4. QA score each variant (0-100)                              │
│  5. Call save_campaign_variant() for each                      │
│  6. Call complete_job(job_id)                                  │
└────────────────────────┬────────────────────────────────────────┘
                         │ MCP Protocol (stdio)
                         ↓
┌─────────────────────────────────────────────────────────────────┐
│  MCP Server (strategy_mcp/server.py)                            │
│                                                                 │
│  Tools:                                                         │
│  - get_client_context → Returns onboarding data, personas      │
│  - get_feedback_summary → Returns approved/denied history      │
│  - save_campaign_variant → INSERT INTO strategy_suggestions    │
│  - complete_job → UPDATE job status='review'                   │
└────────────────────────┬────────────────────────────────────────┘
                         │ Database writes
                         ↓
┌─────────────────────────────────────────────────────────────────┐
│  PostgreSQL (VPS: 31.97.142.123)                               │
│                                                                 │
│  strategy_suggestions table:                                    │
│  - variant_number: 1, 2, 3                                     │
│  - subject_line, email_body                                    │
│  - score: 82-86 (from QA rubric)                              │
│  - rationale, used_variables, campaign_type                    │
│  - status: pending | approved | denied | revision_requested    │
└────────────────────────┬────────────────────────────────────────┘
                         │ Frontend fetches
                         │ GET /api/strategy/suggestions/{client_id}
                         ↓
┌─────────────────────────────────────────────────────────────────┐
│  Strategy Tab - CampaignSuggestions Panel                       │
│                                                                 │
│  Pending: 7  Approved: 1  Denied: 1  Revisions: 0              │
│                                                                 │
│  [Approve] [Deny] [Request Revision]                           │
└─────────────────────────────────────────────────────────────────┘
```

## Implementation Files

### Created and Working

| File | Purpose | Status |
|------|---------|--------|
| `strategy_worker.py` | Polls DB, spawns Claude Code | Working |
| `strategy_mcp/server.py` | MCP tools for Claude | Working |
| `strategy_mcp_config.json` | MCP server config | Working |
| `.claude/skills/generate-strategy.md` | Skill instructions | Working |
| `api/routes/strategy_jobs.py` | API for job management | Working |
| `charm-email-os/components/strategy/CampaignSuggestions.tsx` | Main panel | Deployed |
| `charm-email-os/lib/api.ts` | strategyApi methods | Deployed |
| `Dockerfile.strategy-worker` | Docker image definition | Working |

### Skill Integration

The Cold Email Skill v2.0 is **embedded directly in the prompt** (not loaded via `/skill-name` syntax) because the worker runs non-interactively. The full skill content is included in `strategy_worker.py`.

## Cold Email Skill v2.0 Enhanced

### Skill Location

**Active Skill:** `.claude/skills/generate-strategy.md` (429 lines)
**Backup:** `backups/strategy-ai-v1-working-2026-01-20/` (original 234-line version)

### Key Enhancements (2026-01-20)

The skill was enhanced with techniques from the Claude Campaign Copywriting Skill to produce higher-quality output:

| Enhancement | Purpose |
|-------------|---------|
| **3-Pass Cutting Method** | Pass 1: Delete fluff (20%), Pass 2: Compress (15%), Pass 3: Cut adjectives (10%) |
| **11-Point QA Checklist** | Actionable pass/fail checks before saving each variant |
| **Recipient:Sender Ratio** | Track 3:1 minimum (sentences about THEM vs US) |
| **7 "Poke the Bear" Openers** | Proven opener patterns for engagement |
| **Value-Exchange CTAs** | Framework for low-effort CTAs (5-word reply test) |
| **Before/After Examples** | Annotated cutting examples (94 → 52 words) |
| **ICP Role-Play Step** | 4 questions before writing any email |

### 5 Non-Negotiable Principles

1. **50-90 Words Maximum** — Read aloud in under 20 seconds
2. **Recipient:Sender Ratio >= 3:1** — Count sentences about THEM vs US
3. **Research IS the Personalization** — Custom signals > clever copy
4. **Earn Replies, Not Meetings** — Confirm situation before selling
5. **Two Valid Paths** — Custom signal research OR whole-offer strategy

### 11-Point QA Checklist

All must pass before saving a variant:

1. First line = specific signal
2. No hallucinations
3. Variables formatted {{correctly}}
4. No banned phrases
5. Recipient:sender ratio >= 3:1
6. 50-90 words (strict)
7. CTA = low-effort (5 words to reply)
8. Reads in under 20 seconds
9. Em dashes consistent (—)
10. Subject line = 2-4 words OR whole offer
11. "Would I reply?" = YES

### Enhanced Rationale Format

The skill now instructs Claude to include quality metrics in rationale:
```
"Ratio: 3:1. Words: 72. Cuts: removed greeting, compressed value prop. Pattern: Status Pressure opener."
```

### Campaign Types Generated

| Type | When Used | Example Subject |
|------|-----------|-----------------|
| `custom_signal` | Strong research available | "Quick q about {{company_name}}" |
| `whole_offer` | Lead with proof | "4.7x upgrade increase" |
| `creative_ideas` | Feature-constrained format | "3 ideas for {{company_name}}" |
| `fallback` | Low research available | Redirect or problem-aware |

## Database Schema

### strategy_generation_jobs

```sql
CREATE TABLE strategy_generation_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id UUID NOT NULL REFERENCES clients(id),
    submission_id UUID REFERENCES client_onboarding_submissions(id),
    status VARCHAR(50) DEFAULT 'pending',
    -- pending → processing → review → completed | failed
    generation_round INTEGER DEFAULT 1,
    error_message TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    started_at TIMESTAMP,
    completed_at TIMESTAMP
);
```

### strategy_suggestions

```sql
CREATE TABLE strategy_suggestions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id UUID NOT NULL REFERENCES strategy_generation_jobs(id),
    client_id UUID NOT NULL REFERENCES clients(id),
    variant_number INTEGER NOT NULL,  -- 1, 2, or 3
    subject_line TEXT NOT NULL,
    email_body TEXT NOT NULL,
    score INTEGER,  -- 0-100 from QA scoring
    rationale TEXT,
    used_variables JSONB,
    campaign_type VARCHAR(50),  -- custom_signal, whole_offer, etc.
    status VARCHAR(50) DEFAULT 'pending',
    -- pending, approved, denied, revision_requested
    human_comment TEXT,
    reviewed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);
```

## MCP Tools

| Tool | Purpose | Implemented |
|------|---------|-------------|
| `get_client_context` | Get onboarding data, personas, segments, case studies | Yes |
| `get_feedback_summary` | Get approved/denied variants, revision requests | Yes |
| `save_campaign_variant` | Save email variant with score and rationale | Yes |
| `complete_job` | Mark generation job as ready for review | Yes |

## API Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/strategy/jobs/{client_id}` | Create new generation job |
| GET | `/api/strategy/jobs/{job_id}/status` | Poll job status |
| GET | `/api/strategy/suggestions/{client_id}` | Get all suggestions for client |
| PUT | `/api/strategy/suggestions/{id}/review` | Approve/Deny/Request revision |

## Frontend Components

### CampaignSuggestions.tsx

Located at: `charm-email-os/components/strategy/CampaignSuggestions.tsx`

Features:
- Displays all suggestions for client
- "Generate More" button creates new job
- Shows loading state while job processes
- Polls job status every 2 seconds during generation
- Approve/Deny/Request Revision buttons per variant
- Shows score, rationale, and variables used

## Variable Schema

**Core (always available):**
- `{{first_name}}`, `{{company_name}}`, `{{role_title}}`

**High-Signal (from onboarding):**
- `{{industry}}`, `{{product}}`, `{{target_customer}}`
- `{{case_study_company}}`, `{{case_study_result}}`

**Custom (from research):**
- `{{outbound_tool}}`, `{{competitor}}`, `{{recent_news}}`

## Running the Worker

See [[../deployment/local-docker]] for complete setup instructions.

### Quick Start

```bash
# Worker should already be running
docker ps --filter "name=charm-strategy"

# View logs
docker logs -f charm-strategy-test

# Re-authenticate if needed
docker exec -it charm-strategy-test claude /login
```

### Triggering Generation

1. **Via Frontend:** Click "Generate More" on Strategy tab
2. **Via API:** `POST /api/strategy/jobs/{client_id}`
3. **Via Database:** Insert row into `strategy_generation_jobs` with `status='pending'`

## Troubleshooting

### "Invalid API key - Please run /login"

OAuth tokens have expired. Re-authenticate:
```bash
docker exec -it charm-strategy-test claude /login
```

Then reset failed jobs:
```bash
docker exec charm-strategy-test python3 -c "
import psycopg2, os
conn = psycopg2.connect(host=os.environ.get('POSTGRES_HOST'), port=os.environ.get('POSTGRES_PORT', '5432'), database=os.environ.get('POSTGRES_DB', 'postgres'), user=os.environ.get('POSTGRES_USER'), password=os.environ.get('POSTGRES_PASSWORD'))
cur = conn.cursor()
cur.execute(\"UPDATE strategy_generation_jobs SET status = 'pending', error_message = NULL WHERE status = 'failed'\")
print(f'Reset {cur.rowcount} jobs')
conn.commit()
conn.close()
"
```

### Job Stuck in "pending"

Check if worker is running:
```bash
docker logs --since 1m charm-strategy-test
```

### No Suggestions Appearing

1. Check job status in database
2. Check worker logs for errors
3. Verify frontend is calling correct API endpoint

## Related

- [[../deployment/local-docker]] - Local Docker setup and authentication
- [[client-profile]] - Trigger button on Profile page
- [[../architecture/claude-code-worker]] - Worker architecture
- [[../database/schema]] - Database schema
