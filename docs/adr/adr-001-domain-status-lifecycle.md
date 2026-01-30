---
title: "ADR-001: Domain Status Lifecycle"
created: 2026-01-16
updated: 2026-01-16
tags: [adr, status/accepted, domain, lifecycle]
status: accepted
---

# ADR-001: Domain Status Lifecycle

## Status

Accepted (2026-01-16)

## Context

Domains in Charm Email OS move through multiple stages — from AI generation through purchase, provisioning, and active use. We needed a clear status model to:

1. Track where each domain sits in the pipeline
2. Drive UI tab filtering (Purchase New vs Current Inventory)
3. Enable automated transitions during purchase and provisioning workflows

## Decision

Domains use a `domain_state` column (VARCHAR) with these values:

| Status | Stage | Description |
|--------|-------|-------------|
| `pending` | Generation | AI-generated, awaiting review |
| `approved` | Review | User approved, ready to purchase |
| `rejected` | Review | User denied |
| `purchasing` | Purchase | Purchase in progress |
| `purchased` | Purchase | Domain bought, no inboxes yet |
| `provisioning` | Setup | HyperTide creating inboxes |
| `active` | Live | Fully provisioned and operational |
| `warming` | Live | In warmup period (< 2 weeks) |
| `flagged` | Live | Health issues detected |
| `dead` | Retired | Disabled/retired |

## Consequences

- UI filters domains into two main views based on status
- Status transitions are enforced by backend logic, not database constraints
- The linear flow allows clear progress tracking per domain

## Related

- [[../concepts/domain-lifecycle]] - Full status flow documentation
- [[adr-002-legacy-status]] - Extension for pre-existing domains
