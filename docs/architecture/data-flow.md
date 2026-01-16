---
title: Data Flow
created: 2026-01-16
updated: 2026-01-16
tags: [architecture, data-flow]
---

# Data Flow

How data moves through Charm Email OS.

## Overview Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           CHARM EMAIL OS DATA FLOW                          │
└─────────────────────────────────────────────────────────────────────────────┘

                    ┌──────────────────────────────────────┐
                    │     External Onboarding Form         │
                    │  https://onboard.laviefatigue.com    │
                    └──────────────────┬───────────────────┘
                                       │ POST form data
                                       ↓
┌─────────────────────────────────────────────────────────────────────────────┐
│                         SUPABASE (PostgreSQL)                               │
│  Host: aws-0-us-east-1.pooler.supabase.com:6543                            │
│                                                                             │
│  ┌─────────────────┐    ┌─────────────────────────────┐                    │
│  │     clients     │◄───│ client_onboarding_submissions│                    │
│  │  (basic info)   │    │    (detailed form data)      │                    │
│  └────────┬────────┘    └─────────────────────────────┘                    │
│           │                                                                 │
│  ┌────────▼────────┐    ┌─────────────────────────────┐                    │
│  │   workspaces    │◄───│          domains            │                    │
│  │  (from OwnRBL)  │    │  (generated + approved)     │                    │
│  └─────────────────┘    └─────────────────────────────┘                    │
│                                                                             │
│  ┌─────────────────────────────────────┐                                   │
│  │     domain_generation_jobs          │                                   │
│  │  (tracks Claude Code runs)          │                                   │
│  └─────────────────────────────────────┘                                   │
└────────────────────────────────┬────────────────────────────────────────────┘
                                 │
            ┌────────────────────┼────────────────────┐
            │                    │                    │
            ↓                    ↓                    ↓
┌───────────────────┐  ┌─────────────────┐  ┌─────────────────────┐
│   charm-api       │  │ charm-frontend  │  │  domain_worker.py   │
│   (FastAPI)       │  │   (Next.js)     │  │  (Claude Code)      │
│                   │  │                 │  │                     │
│ Coolify UUID:     │  │ Coolify UUID:   │  │ Spawns subprocess:  │
│ ccssgc4gowsog...  │  │ jskswosswg...   │  │ claude -p "..."     │
└───────────────────┘  └─────────────────┘  └─────────────────────┘
         ↑                      ↑                     │
         │                      │                     │
         └──────────────────────┴─────────────────────┘
                    User Browser / MCP Tools
```

## Data Flows by Feature

### 1. Client Onboarding

```
User fills form → POST to onboard.laviefatigue.com
                        ↓
              client_onboarding_submissions table
                        ↓
              client_segments, client_personas tables
                        ↓
              Strategy tab displays submission
```

**Tables involved:**
- `clients` - Basic client info
- `client_onboarding_submissions` - Form data
- `client_segments` - Customer segments
- `client_personas` - Buyer personas

### 2. Domain Generation

```
User clicks "Generate Domains" → POST /api/domain-sourcing/generate
                                        ↓
                              INSERT domain_generation_jobs
                                        ↓
                              Worker polls, picks up job
                                        ↓
                              Claude Code generates domains
                                        ↓
                              MCP tools INSERT into domains table
                                        ↓
                              Frontend fetches pending candidates
                                        ↓
                              User approves/denies
                                        ↓
                              UPDATE domains.approval_status
```

**Tables involved:**
- `domain_generation_jobs` - Job queue
- `domains` - Generated domains

### 3. Strategy Generation (NEW)

```
Onboarding form submitted → Webhook triggers job
                                    ↓
                          INSERT strategy_generation_jobs
                                    ↓
                          Worker polls, picks up job
                                    ↓
                          Claude Code + Cold Email Skill v2.0
                                    ↓
                          MCP tools INSERT strategy_suggestions
                                    ↓
                          Frontend displays variants
                                    ↓
                          User approves/denies/revises
                                    ↓
                          Revision requests → new job → loop
```

**Tables involved:**
- `strategy_generation_jobs` - Job queue
- `strategy_suggestions` - Generated variants
- `strategy_revision_requests` - Human feedback

## Data Sources Summary

| Data | Source | Storage |
|------|--------|---------|
| Client info | User input / API | `clients` table |
| Onboarding data | External form | `client_onboarding_submissions` |
| Domains | AI generated | `domains` table |
| Inboxes | HyperTide API | `sender_accounts` table |
| Strategy suggestions | Claude Code | `strategy_suggestions` table |

## Related

- [[api-endpoints]] - API route documentation
- [[claude-code-worker]] - Worker architecture
- [[../database/schema]] - Database schema
