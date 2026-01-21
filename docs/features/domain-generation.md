---
title: Domain Generation
created: 2026-01-16
updated: 2026-01-21
tags: [feature, domains, generation]
---

# Domain Generation

AI-powered domain name generation for email outreach campaigns.

## Overview

Generates professional, legitimate-sounding domain names for cold email campaigns using either:
1. **Creative Mode**: AI generates domains based on client onboarding data
2. **Pattern Fallback**: Generates variations using existing domain patterns

## User Flow

```
┌─────────────────────────────────────────────────────────────────┐
│  Purchase New Tab → Domain Sourcing Wizard                      │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Step 1: SELECT CANDIDATES                                       │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │ Generation Mode: Pattern Fallback                           ││
│  │ Pattern: checkoutcomponents.com                             ││
│  │                                                             ││
│  │ [Generate Domains]  ← Triggers Claude Code worker           ││
│  │                                                             ││
│  │ Pending Candidates (5):                                     ││
│  │ ☐ launchecheckoutcomponents.com    Score: 0.85              ││
│  │ ☐ primecheckoutcomponents.com      Score: 0.88              ││
│  │ ☐ flowcheckoutcomponents.com       Score: 0.82              ││
│  │                                                             ││
│  │ [Approve Selected]  [Deny Selected]  [Next Step]            ││
│  └─────────────────────────────────────────────────────────────┘│
│                                                                  │
│  Step 2: SEARCH PRICES → registrar availability/pricing         │
│  Step 3: APPROVE PURCHASES → final confirmation                 │
└─────────────────────────────────────────────────────────────────┘
```

## Generation Modes

### Creative Mode (with onboarding)

When client has completed onboarding:
- Uses industry, product, target audience data
- Generates brand-aligned domain names
- Combines action verbs with product concepts

**Examples:**
- `growthcheckout.com` (action + product)
- `smartpayments.com` (positive + industry)
- `scaleecommerce.io` (verb + industry)

### Pattern Fallback (without onboarding)

When client has existing domains:
- Extracts common suffix (e.g., `checkoutcomponents.com`)
- Generates new prefixes from word pools
- Avoids already-used prefixes

**Prefix Categories:**
- Action Verbs: launch, ignite, spark, fuel, drive
- Growth Words: rise, lift, climb, soar, leap
- Positive Words: ace, win, hit, yes, now
- Professional: pro, prime, core, key, main
- Tech/Modern: neo, next, new, fresh, hot

## API Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/domain-sourcing/can-generate/{client_id}` | Check if generation available |
| GET | `/api/domain-sourcing/pending-candidates/{client_id}` | Get pending candidates |
| POST | `/api/domain-sourcing/approve/{domain_id}` | Approve candidate |
| POST | `/api/domain-sourcing/deny/{domain_id}` | Deny candidate |
| POST | `/api/domain-sourcing/jobs/create/{client_id}` | Create generation job |

## Database Tables

- `domains` - Stores generated domain candidates
- `domain_generation_jobs` - Tracks Claude Code worker runs

See [[../database/schema]] for full schema.

## Architecture

See [[../architecture/claude-code-worker]] for worker details.

## Known Issues (Phase 2)

- "Generate Domains" button not wired to API
- Pattern extraction needs improvement for edge cases

## Related

- [[domain-purchasing]] - Registrar integration for availability and purchase
- [[../architecture/claude-code-worker]] - Worker architecture
- [[../architecture/api-endpoints]] - API documentation
- [[client-profile]] - Client profile page (provides onboarding data)
