---
title: AI Strategy Generation
created: 2026-01-16
updated: 2026-01-16
tags: [feature, strategy, ai, claude-code, phase-3]
---

# AI Strategy Generation

**Status:** Phase 3 - Planned

AI-powered email campaign variant generation using Claude Code and Cold Email Skill v2.0.

## Overview

When an onboarding form is submitted (or manually triggered), the system:
1. Creates a `strategy_generation_job`
2. Worker spawns Claude Code with Cold Email Skill
3. Claude generates 3 email variants per strategy
4. Variants are saved for human review
5. User approves/denies/requests revisions
6. Feedback loop improves future generations

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  Onboarding Form Submitted                                      │
│  (or Profile page Trigger button clicked)                       │
└────────────────────────┬────────────────────────────────────────┘
                         │ POST /api/strategy/jobs
                         ↓
┌─────────────────────────────────────────────────────────────────┐
│  API: INSERT INTO strategy_generation_jobs (status='pending')   │
└────────────────────────┬────────────────────────────────────────┘
                         │ Worker polls
                         ↓
┌─────────────────────────────────────────────────────────────────┐
│  Strategy Worker (strategy_worker.py)                           │
│  → Spawns Claude Code with Cold Email Skill v2.0                │
│  → claude -p "/generate-strategy client_id=... job_id=..."      │
└────────────────────────┬────────────────────────────────────────┘
                         │ MCP tools
                         ↓
┌─────────────────────────────────────────────────────────────────┐
│  Database: strategy_suggestions (3 variants per job)            │
│  Each variant: subject_line, email_body, score, rationale       │
│  Status: pending → approved | denied | revision_requested       │
└────────────────────────┬────────────────────────────────────────┘
                         │ Frontend fetches
                         ↓
┌─────────────────────────────────────────────────────────────────┐
│  Strategy Tab - Campaign Suggestions Panel                      │
│  [Approve] [Deny] [Request Revision]                            │
└─────────────────────────────────────────────────────────────────┘
```

## Cold Email Skill v2.0

### Location

```
D:\Work\Claude Campaign Copywriting Skill-20251120T015618Z-1-001\
  └── Claude Campaign Copywriting Skill\
      ├── cold_email_v2_skill.txt      ← Core philosophy + workflow
      ├── qa_checklist_md.txt          ← 0-100 scoring rubric
      ├── examples_v2_md.txt           ← 10 annotated examples
      ├── creative_ideas_md.txt        ← Creative ideas campaign
      ├── research_playbook_v2.txt     ← Custom signal research
      ├── followups_md.txt             ← Email sequences
      └── icp_objection_md.txt         ← ICP mapping
```

### 5 Non-Negotiable Principles

1. **Shorter & Punchier** — 50-90 words target
2. **Research IS the personalization** — Custom signals > clever copy
3. **Earn replies, not meetings** — Confirm situation before selling
4. **Two valid paths** — Custom signal research OR whole-offer strategy
5. **Every word earns its place** — Read aloud in under 20 seconds

### QA Scoring Rubric (0-100)

| Dimension | Weight | What's Measured |
|-----------|--------|-----------------|
| Situation Recognition | 25 pts | Specific data about them? |
| Value Clarity | 25 pts | Clear offer + proof? |
| Personalization Quality | 20 pts | Custom signal OR AI insight? |
| CTA Effort | 15 pts | 5 words or less to reply? |
| Punchiness | 10 pts | 50-90 words? No fluff? |
| Subject Line | 5 pts | 2-4 words OR whole offer? |

**Score Thresholds:**
- **85+** = Ship it
- **70-84** = One more pass
- **<70** = Start over

### Campaign Types

| Type | When to Use | Example Opening |
|------|-------------|-----------------|
| Custom Signal | Strong research available | "Noticed you have Starter vs Pro tiers..." |
| Creative Ideas | Feature-constrained format | "3 ideas for {{company_name}}:" |
| Whole Offer | Subject line = full value prop | Subject: "4.7x upgrade increase" |

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
    campaign_type VARCHAR(50),  -- custom_signal, creative_ideas, whole_offer
    status VARCHAR(50) DEFAULT 'pending',
    -- pending, approved, denied, revision_requested
    human_comment TEXT,
    reviewed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);
```

### strategy_revision_requests

```sql
CREATE TABLE strategy_revision_requests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id UUID NOT NULL REFERENCES strategy_generation_jobs(id),
    client_id UUID NOT NULL REFERENCES clients(id),
    variant_id UUID REFERENCES strategy_suggestions(id),
    instruction TEXT NOT NULL,  -- "Make it shorter", "Add more proof"
    processed BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW()
);
```

## MCP Tools

| Tool | Purpose |
|------|---------|
| `get_client_context` | Get onboarding data, personas, segments, case studies |
| `get_feedback_summary` | Get approved/denied variants, revision requests |
| `save_campaign_variant` | Save email variant with score and rationale |
| `complete_job` | Mark generation job as ready for review |

## Frontend Components

### CampaignSuggestions Panel

```
┌─────────────────────────────────────────────────────────────────┐
│  Campaign Variants (Score: 87)           [Generate More]        │
│                                                                  │
│  ┌─ Variant 1 ───────────────────────────────────────────────┐  │
│  │ Subject: Quick q about {{company_name}} pricing            │  │
│  │                                                            │  │
│  │ Hey {{first_name}},                                        │  │
│  │                                                            │  │
│  │ Noticed you have Starter vs Pro tiers on your pricing      │  │
│  │ page. Are upgrades a focus right now?                      │  │
│  │                                                            │  │
│  │ We helped {{case_study_company}} increase upgrades by      │  │
│  │ 4.7x with a single checkout tweak.                         │  │
│  │                                                            │  │
│  │ Worth a look?                                              │  │
│  │                                                            │  │
│  │ [Approve ✓] [Deny ✗] [Request Revision ✏️]                 │  │
│  └────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

## Variable Schema

**Core (always available):**
- `{{first_name}}`, `{{company_name}}`, `{{role_title}}`

**High-Signal (from onboarding):**
- `{{industry}}`, `{{product}}`, `{{target_customer}}`
- `{{case_study_company}}`, `{{case_study_result}}`

**Custom (from research):**
- `{{pricing_tier}}`, `{{competitor}}`, `{{recent_news}}`

## Files to Create

| File | Purpose |
|------|---------|
| `strategy_worker.py` | Polls DB, spawns Claude Code |
| `strategy_mcp/server.py` | MCP tools for Claude |
| `strategy_mcp_config.json` | MCP server config |
| `.claude/skills/generate-strategy.md` | Skill instructions |
| `api/routes/strategy_jobs.py` | API for job management |
| `components/strategy/CampaignSuggestions.tsx` | Main panel |
| `components/strategy/VariantCard.tsx` | Individual variant |
| `components/strategy/RevisionModal.tsx` | Request revision dialog |

## Trigger Mechanisms

### Option A: Webhook from onboarding form

```python
@router.post("/webhook/form-submitted")
async def handle_form_submission(payload: dict):
    # Create strategy generation job
    await execute("""
        INSERT INTO strategy_generation_jobs (client_id, submission_id, status)
        VALUES ($1, $2, 'pending')
    """, payload["client_id"], payload["submission_id"])
```

### Option B: Manual trigger from Profile page

"Trigger" button next to each submission creates a job.

## Related

- [[client-profile]] - Trigger button on Profile page
- [[../architecture/claude-code-worker]] - Worker architecture
- [[../database/schema]] - Database schema
