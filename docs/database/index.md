---
title: Database Documentation
created: 2026-01-16
updated: 2026-01-16
tags: [hub, database]
---

# Database

PostgreSQL database documentation for Charm Email OS.

## Documentation

- [[schema]] - Full database schema
- [[migrations]] - Migration history

## Connection

See [[../infrastructure/supabase]] for connection details.

## Table Categories

### Core Tables
- `clients` - Client accounts
- `workspaces` - OwnRBL workspaces (read-only)
- `domains` - Email domains
- `sender_accounts` - Email inboxes

### Onboarding Tables
- `client_onboarding_submissions` - Form submissions
- `client_segments` - Customer segments
- `client_personas` - Buyer personas

### Job Tables
- `domain_generation_jobs` - Domain generation queue
- `strategy_generation_jobs` - Strategy generation queue (NEW)
- `strategy_suggestions` - Generated suggestions (NEW)
- `strategy_revision_requests` - Human feedback (NEW)

## Related

- [[../infrastructure/supabase]] - Database hosting
- [[../architecture/data-flow]] - How data moves through system
