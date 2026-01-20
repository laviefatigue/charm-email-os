---
title: Original vs Current UI Comparison
created: 2026-01-20
updated: 2026-01-20
tags: [comparison, ui, history]
---

# Charm Email OS: Original vs Current UI Comparison

Side-by-side comparison of the original UI concept and current implementation.

## Navigation Structure

### Original (Commit bd34574)
```
┌─────────────────────────────────────────────────────────────┐
│  Charm Email OS              │  Clients                     │
│  ─────────────              ├──────────────────────────────│
│  [Clients]                   │  ┌─────┐ ┌─────┐ ┌─────┐    │
│                              │  │ C1  │ │ C2  │ │ C3  │    │
│                              │  └─────┘ └─────┘ └─────┘    │
│  ─────────────              │                               │
│  JD                          │  Simple grid of client cards │
│  john@agency.com             │  [+ Add Client] button       │
└──────────────────────────────┴──────────────────────────────┘
```

### Current (2026-01-20)
```
┌─────────────────────────────────────────────────────────────┐
│  Charm Email OS              │  Clients                     │
│  ─────────────              ├──────────────────────────────│
│  [Clients]                   │  ┌─────┐ ┌─────┐ ┌─────┐    │
│                              │  │ C1  │ │ C2  │ │ C3  │    │
│  ─────────────              │  └─────┘ └─────┘ └─────┘    │
│  ⚙️ Settings                 │                               │
│  JD                          │  Same grid layout            │
│  john@agency.com             │  [+ Add Client] button       │
└──────────────────────────────┴──────────────────────────────┘
```

**Changes:** Minimal - Added settings gear icon

---

## Client Workspace Tabs

### Original
```
┌────────────────────────────────────────────────────────────┐
│  ← Back to Clients   [C] Charm                             │
├────────────────────────────────────────────────────────────┤
│  [Profile] [Domains/Inboxes] [Strategy] [Leads] [Health]  │
└────────────────────────────────────────────────────────────┘

5 tabs, manual workflows only
```

### Current
```
┌────────────────────────────────────────────────────────────┐
│  ← Back to Clients   [C] Charm                             │
├────────────────────────────────────────────────────────────┤
│  [Profile] [Domains/Inboxes] [Strategy] [Leads] [Health]  │
└────────────────────────────────────────────────────────────┘

Same 5 tabs, but with AI-powered features
```

**Changes:** Same tab structure, different functionality inside

---

## Profile Tab

### Original
```
┌────────────────────────────────────────────────────────────┐
│  Profile                                                    │
├────────────────────────────────────────────────────────────┤
│                                                             │
│  Client Name: Charm                                         │
│  Website: usecharm.com                                      │
│  Status: Active                                             │
│                                                             │
│  [Edit Profile]                                             │
│                                                             │
│  ─────────────────────────────────────────────────────────  │
│                                                             │
│  Onboarding: Not Started                                    │
│  [Start Onboarding Form]  ← In-app multi-step wizard       │
│                                                             │
└────────────────────────────────────────────────────────────┘
```

### Current
```
┌────────────────────────────────────────────────────────────┐
│  Profile                                                    │
├────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─ Onboarding Summary ─────────────────────────────────┐  │
│  │  No client profile data available                     │  │
│  │  (or shows quick stats from onboarding)              │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                             │
│  ┌─ Comprehensive Profile ──────────────────────────────┐  │
│  │  Submitted: Jan 16, 2026                    [submitted] │
│  │                                                        │  │
│  │  ┌─ Foundation ─────────────────────────────────────┐ │  │
│  │  │ Company: Charm                                    │ │  │
│  │  │ Website: usecharm.com                             │ │  │
│  │  │ Contact: Elliott LaVieFatigue                     │ │  │
│  │  │ Employees: 11-50                                  │ │  │
│  │  │ Funding: Series A                                 │ │  │
│  │  └──────────────────────────────────────────────────┘ │  │
│  │                                                        │  │
│  │  [Offering ▼] [Market Signals ▼] [Audience ▼]        │  │
│  │  [Current Process ▼] [Messaging ▼] [Goals ▼]         │  │
│  │                                                        │  │
│  │  [Edit]                                                │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                             │
└────────────────────────────────────────────────────────────┘
```

**Changes:**
| Aspect | Original | Current |
|--------|----------|---------|
| Onboarding | In-app wizard | External form (onboard.laviefatigue.com) |
| Data display | Flat fields | Collapsible accordion sections |
| Sections | None | 7 expandable sections |
| Edit mode | Edit button | Edit button opens ComprehensiveOnboarding |

---

## Strategy Tab

### Original
```
┌────────────────────────────────────────────────────────────┐
│  Strategy                                                   │
├────────────────────────────────────────────────────────────┤
│                                                             │
│  Campaign Ideas                               [+ Add Idea]  │
│                                                             │
│  ┌─ Idea Card ──────────────────────────────────────────┐  │
│  │  B2B SaaS → Enterprise → Custom Signal                │  │
│  │  "Founder CEO Rotation Angle"                         │  │
│  │                                                        │  │
│  │  Quick Stats: 12 variables, 3 templates, Score: 85    │  │
│  │                                                        │  │
│  │  [Approve] [Reject] [Edit]                            │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                             │
│  ─────────────────────────────────────────────────────────  │
│                                                             │
│  Approved Campaigns                                         │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  "Founder Angle" - Ready   [Create Campaign →]        │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                             │
└────────────────────────────────────────────────────────────┘

Manual idea creation and approval
No AI generation
```

### Current
```
┌────────────────────────────────────────────────────────────┐
│  Strategy                                                   │
├────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─ Onboarding Summary ─────────────────────────────────┐  │
│  │  No client profile data available                     │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                             │
│  ┌─ Comprehensive Profile ──────────────────────────────┐  │
│  │  (Collapsed accordion view of onboarding data)        │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                             │
│  ┌─ Campaign Suggestions ───────────────────────────────┐  │
│  │  AI-generated email variants       [Generate More]    │  │
│  │                                                        │  │
│  │  Pending: 7  Approved: 1  Denied: 1  Revisions: 0    │  │
│  │                                                        │  │
│  │  ┌─ V1 ─────────────────────────────────────────────┐ │  │
│  │  │ Pending Review | custom_signal | Score: 86        │ │  │
│  │  │                                                    │ │  │
│  │  │ Subject: Quick q about {{company_name}}           │ │  │
│  │  │                                                    │ │  │
│  │  │ Hey {{first_name}},                               │ │  │
│  │  │                                                    │ │  │
│  │  │ Noticed {{company_name}} is scaling outbound...   │ │  │
│  │  │                                                    │ │  │
│  │  │ Rationale: Strong custom signal opening...        │ │  │
│  │  │ Variables: {{first_name}}, {{company_name}}       │ │  │
│  │  │                                                    │ │  │
│  │  │ [Approve] [Deny] [Request Revision]               │ │  │
│  │  └──────────────────────────────────────────────────┘ │  │
│  │                                                        │  │
│  │  ┌─ V2 ─────────────────────────────────────────────┐ │  │
│  │  │ ... more variants ...                              │ │  │
│  │  └──────────────────────────────────────────────────┘ │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                             │
└────────────────────────────────────────────────────────────┘

AI-powered generation via Claude Code
Cold Email Skill v2.0 integration
QA scoring (0-100)
```

**Changes:**
| Aspect | Original | Current |
|--------|----------|---------|
| Generation | Manual idea creation | AI-powered via Claude Code |
| Content type | Campaign "Ideas" | Email "Variants" with full copy |
| Scoring | Quality score (generic) | QA rubric (0-100, 6 dimensions) |
| Actions | Approve/Reject/Edit | Approve/Deny/Request Revision |
| Trigger | Manual | "Generate More" button → background job |
| Context | Minimal | Shows onboarding data for reference |

---

## Domains/Inboxes Tab

### Original
```
┌────────────────────────────────────────────────────────────┐
│  Domains / Inboxes                                          │
├────────────────────────────────────────────────────────────┤
│                                                             │
│  Infrastructure Status: 5 Domains, 23 Inboxes              │
│                                     [Generate] [+ Domain]   │
│                                                             │
│  ┌─ Tree View ──────────────────────────────────────────┐  │
│  │                                                        │  │
│  │  ▼ getcc.com               [approved] [healthy]       │  │
│  │    ├─ inbox1@getcc.com     [live]     Score: 95      │  │
│  │    ├─ inbox2@getcc.com     [warming]  Progress: 60%  │  │
│  │    └─ inbox3@getcc.com     [live]     Score: 88      │  │
│  │                                                        │  │
│  │  ► trycc.com               [pending]  [Approve][Reject]│ │
│  │                                                        │  │
│  │  ► usecc.com               [approved] [healthy]       │  │
│  │                                                        │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                             │
└────────────────────────────────────────────────────────────┘

Manual domain/inbox management
Tree view hierarchy
Expand to see child inboxes
```

### Current
```
┌────────────────────────────────────────────────────────────┐
│  Domains / Inboxes                                          │
├────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─ Domain Sourcing ────────────────────────────────────┐  │
│  │  AI-generated domain suggestions    [Generate More]   │  │
│  │                                                        │  │
│  │  Pending: 5  Approved: 3  Denied: 2                   │  │
│  │                                                        │  │
│  │  ┌───────────────────────────────────────────────────┐│  │
│  │  │ launchcc.com    Score: 0.85    $12/yr (Porkbun)  ││  │
│  │  │ Rationale: Action verb 'launch'...               ││  │
│  │  │ [Approve] [Deny]                                  ││  │
│  │  └───────────────────────────────────────────────────┘│  │
│  └──────────────────────────────────────────────────────┘  │
│                                                             │
│  ┌─ Domain Purchasing ──────────────────────────────────┐  │
│  │  Buy approved domains via Porkbun/Dynadot            │  │
│  │  [Purchase Selected]                                  │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                             │
│  ┌─ Inbox Inventory ────────────────────────────────────┐  │
│  │  Tree view similar to original                        │  │
│  │  + HyperTide purchasing integration                   │  │
│  │  + OwnRBL health checking                            │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                             │
└────────────────────────────────────────────────────────────┘

AI-powered domain generation
Registrar price comparison
Purchasing wizards
OwnRBL health integration
```

**Changes:**
| Aspect | Original | Current |
|--------|----------|---------|
| Domain sourcing | Manual add only | AI-generated suggestions |
| Domain pricing | Not shown | Porkbun/Dynadot price comparison |
| Purchasing | Manual (external) | In-app purchase wizards |
| Health data | Mock scores | Real OwnRBL integration |
| Inbox creation | Manual form | HyperTide automation |

---

## Health Tab

### Original
```
┌────────────────────────────────────────────────────────────┐
│  Health Dashboard                                           │
├────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐      │
│  │ Health   │ │ Live     │ │ Live     │ │ Active   │      │
│  │ Score    │ │ Domains  │ │ Inboxes  │ │ Monitors │      │
│  │   87%    │ │    5     │ │   23     │ │    3     │      │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘      │
│                                                             │
│  ┌─ Kill Triggers ──────────┐ ┌─ Backup Capacity ───────┐  │
│  │                           │ │                          │  │
│  │  [Warning] Gmail bounce   │ │  ████████░░  80%        │  │
│  │  inbox1@cc.com            │ │  5 backup inboxes ready │  │
│  │  [Acknowledge] [Mute]     │ │                          │  │
│  │                           │ │                          │  │
│  └───────────────────────────┘ └──────────────────────────┘  │
│                                                             │
│  ┌─ Domain Health Grid ─────────────────────────────────┐  │
│  │  ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐           │  │
│  │  │ D1  │ │ D2  │ │ D3  │ │ D4  │ │ D5  │           │  │
│  │  │ ✓   │ │ ✓   │ │ ⚠   │ │ ✓   │ │ ✗   │           │  │
│  │  └─────┘ └─────┘ └─────┘ └─────┘ └─────┘           │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                             │
│  ┌─ Campaign Attribution ───┐ ┌─ List Contamination ────┐  │
│  │  Impact by campaign      │ │  Bounce rate tracking   │  │
│  └───────────────────────────┘ └──────────────────────────┘  │
│                                                             │
│  ┌─ ESP Health Summary ─────────────────────────────────┐  │
│  │  Gmail: 95%  │  Microsoft: 88%  │  Yahoo: 92%        │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                             │
└────────────────────────────────────────────────────────────┘

Mock data
Widget-based dashboard
```

### Current
```
┌────────────────────────────────────────────────────────────┐
│  Health Dashboard                        [↻ Refresh]       │
├────────────────────────────────────────────────────────────┤
│                                                             │
│  (Similar layout to original)                              │
│                                                             │
│  + Real-time data from OwnRBL                              │
│  + Auto-refresh capability                                  │
│  + Enhanced kill trigger handling                          │
│  + Live inbox health scores                                │
│                                                             │
└────────────────────────────────────────────────────────────┘

Real data from OwnRBL API
Same widget layout
Auto-refresh added
```

**Changes:**
| Aspect | Original | Current |
|--------|----------|---------|
| Data source | Mock data | Real OwnRBL API |
| Refresh | Manual only | Auto-refresh option |
| Kill triggers | Mock alerts | Real alerting |
| Health scores | Static | Live from API |

---

## Data Flow Comparison

### Original
```
User Action
    ↓
React Component
    ↓
Zustand Store (in-memory)
    ↓
Mock Data (hardcoded)
    ↓
UI Re-render
```

### Current
```
User Action
    ↓
React Component
    ↓
API Client (lib/api.ts)
    ↓
FastAPI Backend
    ↓
PostgreSQL Database
    ↓
Response → UI Re-render

+ Background Workers:
  Strategy Worker (Claude Code) → DB → Frontend polls
```

---

## Component Evolution Summary

| Component | Original | Current | Change Level |
|-----------|----------|---------|--------------|
| Sidebar | Basic nav | Same + settings | Minor |
| TabNavigation | 5 tabs | Same 5 tabs | None |
| ClientCard | Avatar + stats | Same | None |
| DomainCard | Status + health | + AI sourcing | Major |
| InboxCard | State + score | + purchasing | Major |
| IdeaCard | Manual ideas | → CampaignSuggestions | Replaced |
| LeadsTable | CSV upload | Same | Minor |
| HealthDashboard | Mock widgets | Real data | Major |
| OnboardingForm | In-app wizard | External form | Moved |

---

## Key Takeaways

1. **UI Structure Preserved** - Tab layout and navigation unchanged
2. **Data Backend Added** - From mock Zustand to real FastAPI/PostgreSQL
3. **AI Integration Added** - Claude Code powers strategy and domain generation
4. **External Integrations Added** - Porkbun, Dynadot, HyperTide, OwnRBL
5. **Approval Workflow Maintained** - Same pattern (pending → approved/denied)
6. **Onboarding Externalized** - Moved to separate hosted form

---

## Related

- [[../features/strategy-generation]] - Current strategy implementation
- [[../architecture/claude-code-worker]] - AI worker architecture
- [[../deployment/local-docker]] - Current deployment setup
