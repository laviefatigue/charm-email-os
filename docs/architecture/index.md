---
title: Architecture Overview
created: 2026-01-16
updated: 2026-01-16
tags: [hub, architecture]
---

# Architecture

System architecture for Charm Email OS.

## Components

- [[data-flow]] - How data moves through the system
- [[api-endpoints]] - REST API documentation
- [[claude-code-worker]] - AI worker architecture (domain + strategy generation)
- [[purchase-worker]] - Purchase worker architecture (Hypertide browser automation)

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              USER LAYER                                     │
│  ┌─────────────────────────┐    ┌──────────────────────────────────────┐   │
│  │   Onboarding Form       │    │          Charm Email OS UI           │   │
│  │ onboard.laviefatigue.com│    │  charm-frontend (Next.js)            │   │
│  └───────────┬─────────────┘    └──────────────────┬───────────────────┘   │
└──────────────┼──────────────────────────────────────┼───────────────────────┘
               │                                      │
               ↓                                      ↓
┌─────────────────────────────────────────────────────────────────────────────┐
│                              API LAYER                                      │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │                    charm-api (FastAPI)                                │  │
│  │                                                                       │  │
│  │  /api/clients     /api/onboarding     /api/domain-sourcing           │  │
│  │  /api/domains     /api/inboxes        /api/strategy (NEW)            │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────┬──────────────────────────────────┘
                                           │
               ┌───────────────────────────┼───────────────────────────┐
               │                           │                           │
               ↓                           ↓                           ↓
┌─────────────────────────┐  ┌─────────────────────────┐  ┌─────────────────────────┐
│    PostgreSQL           │  │   Domain Worker         │  │   Strategy Worker       │
│    (Supabase)           │  │   (Claude Code)         │  │   (Claude Code)         │
│                         │  │                         │  │                         │
│  clients                │  │  Polls domain_          │  │  Polls strategy_        │
│  domains                │  │  generation_jobs        │  │  generation_jobs        │
│  sender_accounts        │  │                         │  │                         │
│  *_generation_jobs      │  │  Uses domain_mcp        │  │  Uses strategy_mcp      │
│  strategy_suggestions   │  │  tools                  │  │  tools                  │
└─────────────────────────┘  └─────────────────────────┘  └─────────────────────────┘

               ┌─────────────────────────────────────────────────┐
               │   Purchase Worker (Claude Code + Playwright)    │
               │                                                 │
               │  Polls inbox_purchase_jobs                      │
               │  Browser automation on Hypertide                │
               │  Uses purchase_mcp tools                        │
               └─────────────────────────────────────────────────┘
```

## Key Design Decisions

1. **Decoupled Workers**: Workers poll database independently, spawn Claude Code subprocesses
2. **MCP Protocol**: Claude Code communicates with database via MCP tools
3. **Atomic Suggestions**: Each suggestion is independently reviewable
4. **Feedback Loop**: Human feedback shapes next generation round

## Technology Choices

| Component | Technology | Rationale |
|-----------|------------|-----------|
| Frontend | Next.js 14 | Server components, app router |
| Backend | FastAPI | Async, Python, type hints |
| Database | PostgreSQL | Relational, JSONB support |
| AI | Claude Code | Skill-based, MCP integration |
| Deployment | Coolify | Self-hosted, Docker-based |

## Related

- [[../index]] - Main documentation hub
- [[../infrastructure/index]] - Infrastructure details
