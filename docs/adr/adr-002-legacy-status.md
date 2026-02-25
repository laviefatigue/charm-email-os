---
title: "ADR-002: Legacy Domain Status"
created: 2026-01-22
updated: 2026-01-22
tags: [adr, status/accepted, domain, legacy]
status: accepted
---

# ADR-002: Legacy Domain Status

## Status

Accepted (2026-01-22)

## Context

When the new domain lifecycle (ADR-001) was introduced, there were already domains in production that:

1. Had been purchased and provisioned before the workflow existed
2. Already had inboxes in EmailBison
3. Were stuck with stale statuses (`purchased`, `pending`, `approved`, or NULL)

These domains didn't fit neatly into the new lifecycle — they weren't "active" (not provisioned through the new workflow) but they were operational.

## Decision

Add a `legacy` status to the domain lifecycle to represent pre-existing infrastructure:

- **Who**: Domains created before 2026-01-22 that already have inboxes
- **Where**: Displayed in the "Current Inventory" tab alongside `active`, `warming`, `flagged`, `dead`
- **How**: A one-time migration endpoint updates matching domains to `legacy`

### Migration Endpoint

```
POST /api/v1/domains/migrate/legacy-domains-with-inboxes
```

Finds domains with existing inboxes in EmailBison but non-inventory statuses and updates them to `legacy`.

## Consequences

- Legacy domains are visible in Current Inventory for monitoring
- They can transition to `flagged` or `dead` like any active domain
- No distinction in health monitoring between `active` and `legacy`
- The migration is idempotent and safe to re-run

## Related

- [[adr-001-domain-status-lifecycle]] - Original lifecycle design
- [[../concepts/domain-lifecycle]] - Full status documentation
