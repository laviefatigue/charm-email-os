---
title: Database Documentation
created: 2026-01-16
updated: 2026-02-13
tags: [hub, database, inventory, views]
---

# Database

PostgreSQL database documentation for Charm Email OS.

## Documentation

- [[README]] - **Database documentation hub** - Start here for overview
- [[schema]] - Full database schema reference
- [[migrations]] - Migration history and changelog
- [[backfill-analysis]] - **Data availability and backfill requirements**
  - Current state: 95% schema, 70% data
  - Critical gaps: RBL data, daily snapshots, campaign burns
  - Ready-to-run SQL scripts
  - Time to full data: 13-19 hours

## Connection

See [[../infrastructure/supabase]] for connection details.

## Table Categories

### Core Tables
- `clients` - Client accounts
- `workspaces` - OwnRBL workspaces (read-only)
- `domains` - Email domains
- `sender_accounts` - Email inboxes

### Health & Inventory Tables
- `kill_queue` - Inboxes pending deletion (kill trigger system)
- `kill_trigger_events` - Historical kill events
- `inventory_audit_log` - Inventory status change history
- `feature_flags` - System feature toggles (e.g., AUTO_KILL_ENABLED)
- `sender_warmup_snapshots` - Time-series warmup data

### Onboarding Tables
- `client_onboarding_submissions` - Form submissions
- `client_segments` - Customer segments
- `client_personas` - Buyer personas

### Job Tables
- `domain_generation_jobs` - Domain generation queue
- `strategy_generation_jobs` - Strategy generation queue
- `strategy_suggestions` - Generated suggestions
- `strategy_revision_requests` - Human feedback

## Views

### v_inbox_inventory_status

Real-time inventory status view with calculated pool and lifecycle statuses.

**Pool Status Logic** (2026-02-13):
- `deployed` - In active campaigns
- `warning` - Has bounces (1+ in 24h OR 3+ in 7d)
- `reserve` - 14+ days old AND warmup enabled (deployment-ready)
- `incubating` - Under 14 days OR warmup not enabled (still warming)
- `NULL` - Dead inboxes

```sql
-- Example query for inventory counts
SELECT
    COUNT(*) FILTER (WHERE calculated_pool_status = 'deployed') as deployed,
    COUNT(*) FILTER (WHERE calculated_pool_status = 'reserve') as reserve,
    COUNT(*) FILTER (WHERE calculated_pool_status = 'incubating') as incubating,
    COUNT(*) FILTER (WHERE inbox_state = 'dead') as dead
FROM v_inbox_inventory_status
WHERE workspace_id = $1;
```

See migration `029_inventory_segmentation_fix.sql` for full view definition.

## Related

- [[../infrastructure/supabase]] - Database hosting
- [[../architecture/data-flow]] - How data moves through system
