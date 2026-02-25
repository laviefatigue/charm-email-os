---
title: Client Profile Page
created: 2026-01-16
updated: 2026-01-16
tags: [feature, client, profile, phase-1]
---

# Client Profile Page

**Status:** Phase 1 - Planned

Dedicated tab for managing basic client information and onboarding submissions.

## Overview

A new Profile tab alongside existing tabs (Strategy, Leads, Health) that shows:
1. Basic client information (editable)
2. List of onboarding form submissions with View/Edit/Trigger actions

## UI Design

```
┌─────────────────────────────────────────────────────────────────┐
│  [Profile] [Domains/Inboxes] [Strategy] [Leads] [Health]        │
├─────────────────────────────────────────────────────────────────┤
│  BASIC INFORMATION                               [Edit] [Save]  │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │ Company: Checkout Components                                ││
│  │ Contact: John Smith (john@checkoutcomponents.com)           ││
│  │ Website: checkoutcomponents.com                             ││
│  │ Industry: E-commerce / SaaS                                 ││
│  │ Domain Pattern: checkoutcomponents.com                      ││
│  └─────────────────────────────────────────────────────────────┘│
│                                                                  │
│  ONBOARDING SUBMISSIONS                                          │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │ [★] Jan 15, 2026 - Complete          [View] [Edit] [Trigger]││
│  │ [ ] Dec 1, 2025 - Draft              [View] [Edit]          ││
│  └─────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────┘
```

## Database Changes

Add dedicated columns to `clients` table:

```sql
ALTER TABLE clients ADD COLUMN IF NOT EXISTS contact_name VARCHAR(255);
ALTER TABLE clients ADD COLUMN IF NOT EXISTS contact_email VARCHAR(255);
ALTER TABLE clients ADD COLUMN IF NOT EXISTS website VARCHAR(255);
ALTER TABLE clients ADD COLUMN IF NOT EXISTS industry VARCHAR(100);
ALTER TABLE clients ADD COLUMN IF NOT EXISTS domain_pattern VARCHAR(255);
```

## Files to Create/Modify

| File | Action | Purpose |
|------|--------|---------|
| `app/clients/[clientId]/profile/page.tsx` | CREATE | Profile page |
| `components/clients/ClientProfileCard.tsx` | CREATE | Basic info card (editable) |
| `components/clients/SubmissionsList.tsx` | CREATE | List form submissions |
| `api/routes/clients.py` | MODIFY | Add profile fields |
| `api/models/client.py` | MODIFY | Add profile fields |
| `lib/types.ts` | MODIFY | Add profile fields to Client type |

## API Changes

Update `GET /api/clients/{id}` and `PUT /api/clients/{id}` to include:

```json
{
  "contact_name": "John Smith",
  "contact_email": "john@checkoutcomponents.com",
  "website": "checkoutcomponents.com",
  "industry": "E-commerce / SaaS",
  "domain_pattern": "checkoutcomponents.com"
}
```

## Features

### Basic Information Card

- Displays contact name, email, website, industry, domain pattern
- Edit mode with Save/Cancel buttons
- Validation for email format and website URL

### Submissions List

- Shows all `client_onboarding_submissions` for client
- Star icon indicates "active" submission
- Status badge (Complete, Draft, etc.)
- Actions:
  - **View**: Opens read-only modal with full submission
  - **Edit**: Opens editable modal (existing `OnboardingEditModal`)
  - **Trigger**: Creates strategy generation job (Phase 3)

## Related

- [[strategy-generation]] - Trigger button creates strategy jobs
- [[../database/schema]] - Database schema
- [[../architecture/api-endpoints]] - API documentation
