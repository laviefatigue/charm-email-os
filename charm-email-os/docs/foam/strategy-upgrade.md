# Strategy Component Upgrade

## Overview

The Strategy page is being streamlined to focus purely on campaign generation and approval workflow. Client profile information has been moved to the dedicated Profile page, reducing redundancy and improving user focus.

## Status: Planned

**Target:** Q1 2026

---

## Current Architecture

```
Strategy Page (Before)
├── ClientHeader
├── TabNavigation
├── OnboardingSummary          ← Redundant (exists on Profile)
├── ComprehensiveOnboarding    ← Redundant (exists on Profile)
└── CampaignSequences          ← Core workflow
```

---

## Planned Changes

### 1. Simplified Page Structure

```
Strategy Page (After)
├── ClientHeader
├── TabNavigation
└── CampaignSequences          ← Focused workflow
```

**Removed Components:**
- `OnboardingSummary` - Client profile data already on Profile page
- `ComprehensiveOnboarding` - Full onboarding form already on Profile page

### 2. Enhanced Campaign Workflow

```
Generate → Pending → Approve → Add Spintax → Review Spintax → Push to EmailBison
```

Each step maintains full edit capabilities.

### 3. Spintax Preview Feature

When a sequence is spintaxed, users can toggle between:
- **Original View** - Shows the approved copy before spintax
- **Spintaxed View** - Shows the transformed copy with syntax highlighting

**Syntax Highlighting:**
- Spintax patterns `{Hi|Hello|Hey}` → Purple highlight
- Liquid conditionals `{% if %}{% endif %}` → Blue highlight
- Variables `{{first_name}}` → Green highlight

---

## Sequence Status Flow

| Status | Description | Actions Available |
|--------|-------------|-------------------|
| `pending` | Awaiting review | Approve, Deny, Request Revision, Edit |
| `approved` | Ready for spintax | Add Spintax, Edit |
| `spintax_pending` | Processing spintax | View only |
| `spintaxed` | Ready to push | Toggle view, Push to EmailBison, Edit |
| `sent` | Pushed to EmailBison | View only |

---

## Type Definitions

### CampaignSequence

```typescript
interface CampaignSequence {
  id: string;
  jobId: string;
  clientId: string;
  campaignName: string;
  campaignType?: 'custom_signal' | 'creative_ideas' | 'whole_offer' | 'fallback';
  status: 'pending' | 'approved' | 'denied' | 'revision_requested'
        | 'spintax_pending' | 'spintaxed' | 'sent';
  emails: SequenceEmail[];
  spintaxedEmails?: SequenceEmail[];  // Populated after spintax processing
  // ... other fields
}
```

---

## API Endpoints

### Spintax Processing

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/strategy/sequences/{id}/spintax` | POST | Create spintax job |
| `/api/strategy/spintax-jobs/{id}/status` | GET | Poll job status |
| `/api/strategy/sequences/{id}/push-to-emailbison` | POST | Push spintaxed sequence |

### Response Changes

The `GET /api/strategy/sequences/{clientId}` endpoint now returns:
- `spintaxed_emails` - Transformed email content (when status is `spintaxed`)

---

## Backend Worker

### Spintax Worker

**Container:** `charm-spintax-worker`
**Image:** `charm-spintax-worker:latest`

The spintax worker:
1. Polls for pending spintax jobs
2. Fetches approved sequence content via MCP tools
3. Invokes Claude Code with spintax skill
4. Saves transformed content to `spintaxed_sequence_data`
5. Updates sequence status to `spintaxed`

**Shared Resources:**
- OAuth credentials via `charm-claude-credentials` volume
- Database connection via environment variables

---

## Files Modified

### Already Complete

| File | Change |
|------|--------|
| `lib/api.ts` | Added `spintax_pending`, `spintaxed` to status type; added `spintaxedEmails` field |
| `components/strategy/CampaignSequenceCard.tsx` | Spintax button and status handling |
| `components/strategy/CampaignSequences.tsx` | `handleSpintax` and `pollSpintaxStatus` |
| `api/routes/strategy.py` | Spintax endpoints, push enforcement |

### Planned

| File | Change |
|------|--------|
| `app/clients/[clientId]/strategy/page.tsx` | Remove redundant onboarding components |
| `components/strategy/CampaignSequenceCard.tsx` | Add Original/Spintaxed toggle |
| `components/strategy/EmailStepCard.tsx` | Support viewMode prop |
| `lib/spintax-highlight.tsx` | New syntax highlighting helper |

---

## Visual Design

### Spintax Toggle (Mockup)

```
┌─────────────────────────────────────────────────────┐
│ Campaign: Re: Quick question about {{company}}      │
│ Status: [Spintaxed] ✓                               │
│                                                     │
│ View: [Original] [✨ Spintaxed]  ← Toggle buttons   │
├─────────────────────────────────────────────────────┤
│ Email 1 - Day 0                                     │
│ ──────────────────────────────────────────────────  │
│ {Hi|Hello|Hey} {{first_name}},                      │
│  └── purple ──┘                                     │
│ {% if hour < 12 %}Good morning{% endif %}           │
│ └────────── blue ──────────────┘                    │
│                                                     │
│ [Edit] [Request Revision]                           │
├─────────────────────────────────────────────────────┤
│ [Push to EmailBison]                                │
└─────────────────────────────────────────────────────┘
```

---

## Related Documentation

- [[campaigns]] - Campaign management
- [[components]] - UI component library
- [[state-management]] - Zustand stores
- [[architecture]] - System architecture
