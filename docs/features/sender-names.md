---
title: Sender Names
created: 2026-01-24
updated: 2026-01-24
tags: [feature, infrastructure, inbox-setup]
---

# Sender Names

Sender name configuration and email prefix variation generation for inbox creation.

## Overview

The Sender Names feature allows clients to define **base names** (real identities) and generate multiple **email prefix variations** from those seeds. This supports the Hypertide inbox provisioning workflow where clients need many unique inboxes but only have 1-2 real sender identities.

## Key Concepts

### Base Names (Seeds)
Real identities provided by the client:
- First name + Last name
- Optional "Founder" flag for prioritization

### Variations
Email prefixes generated from base names:
- `chris.booth` (firstname.lastname)
- `c.booth` (f.lastname)
- `chrisbooth` (firstnamelastname)
- `chris.b` (firstname.l)
- `cbooth` (flastname)
- etc.

## Data Sources

| Source | Description |
|--------|-------------|
| Campaign Documentation | Names extracted when customer submits campaign docs |
| Manual Entry | Added via Names tab in Domains/Inboxes page |

## Variation Patterns

| Pattern | Format | Example |
|---------|--------|---------|
| `firstname.lastname` | f.l | chris.booth |
| `f.lastname` | F.l | c.booth |
| `firstnamelastname` | fl | chrisbooth |
| `firstname.l` | f.L | chris.b |
| `flastname` | Fl | cbooth |
| `lastname.firstname` | l.f | booth.chris |
| `lastname.f` | l.F | booth.c |
| `firstname_lastname` | f_l | chris_booth |
| `numbered` | f.l# | chris.booth1 |

## UI Location

**Path:** `/clients/[clientId]/inboxes` → "Names" tab

### Features
- Add/remove base names
- Mark founder identity
- Select variation patterns via checkboxes
- Generate up to 10 variations
- Approve/reject individual variations
- Save to client profile

## Integration with Inbox Setup

```
Names Tab                    Inbox Purchase Wizard
───────────                  ─────────────────────
Base Names                   ┌─────────────────┐
    │                        │ Step 2: Names   │
    ▼                        │                 │
Generate Variations          │ Auto-loads      │
    │                        │ saved names     │
    ▼                        │                 │
Save to Client    ─────────► │ chris.booth     │
                             │ c.booth         │
                             │ chrisbooth      │
                             └─────────────────┘
                                    │
                                    ▼
                             Hypertide Creates
                             Inboxes
```

## API Endpoints

### Generate Variations
```
POST /api/v1/clients/{client_id}/generate-name-variations
```

### Save Names
```
PUT /api/v1/clients/{client_id}/sender-names
```

## Backend Files

| File | Purpose |
|------|---------|
| `api/data/name_variations.py` | Variation patterns and generation logic |
| `api/routes/clients.py` | API endpoints for name operations |

## Frontend Files

| File | Purpose |
|------|---------|
| `components/inboxes/SenderNamesTab.tsx` | Names tab UI component |
| `lib/types.ts` | TypeScript interfaces |

## Related

- [[ns-verification]] - DNS configuration for purchased domains
- [[domain-purchasing]] - Domain acquisition workflow
- [[../foam/infrastructure]] - Infrastructure overview
- [[../foam/workflows]] - Complete provisioning workflow
