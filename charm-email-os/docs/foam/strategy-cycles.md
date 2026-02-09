---
title: Strategy Cycles
created: 2026-02-09
updated: 2026-02-09
tags: [feature, strategy, campaigns, cycles]
---

# Strategy Cycles

Campaign organization hierarchy: **Strategy → Cycles → Campaigns**

## Overview

Cycles are 14-day periods that group campaigns together for performance tracking and iterative improvement. The system uses a 6-cycle model with odd/even evolution groups.

## Cycle Model

| Cycle | Target Campaigns | Evolution Group |
|-------|------------------|-----------------|
| 1     | 4                | Odd (1→3→5)     |
| 2     | 8                | Even (2→4→6)    |
| 3     | 12               | Odd (1→3→5)     |
| 4     | 16               | Even (2→4→6)    |
| 5     | 20               | Odd (1→3→5)     |
| 6     | 24               | Even (2→4→6)    |

### Evolution Groups

Campaigns in the same evolution group share lineage:
- **Odd cycles (1→3→5)**: Campaign A v1 in Cycle 1 evolves to Campaign A v2 in Cycle 3
- **Even cycles (2→4→6)**: Separate evolution track

This allows A/B testing between evolution groups while maintaining campaign continuity within a group.

## Strategy Page Layout

The Strategy page uses inner tabs to organize content:

```
Strategy Page
├── ClientHeader
├── TabNavigation
└── Inner Tabs
    ├── [Campaigns] (default)
    │   ├── CycleNavigator (horizontal pills)
    │   ├── ActiveCycleCard (cycle metadata + campaign grid)
    │   └── CampaignSequences (existing component)
    │
    └── [Profile Context]
        └── ComprehensiveOnboarding (collapsible)
```

## Components

### [[CycleNavigator]]

Horizontal row of cycle pills for selection:

```
[1 Active] [2 Planned] [3] [4] [5] [6] [+ Add]
```

Visual states:
- `planned` - Gray outline
- `active` - Blue/green fill with glow
- `completed` - Checkmark icon

Color coding by evolution group:
- Odd cycles (1,3,5): Blue accent
- Even cycles (2,4,6): Green accent

### [[ActiveCycleCard]]

Displays the selected cycle:

- Cycle metadata (name, dates, duration)
- Progress bar (actual vs target campaigns)
- 2x2 campaign grid using [[CampaignMiniCard]]
- Empty slots for unfilled campaigns
- "Generate More" button when under target

### [[CampaignMiniCard]]

Compact campaign card for the grid view:

- Campaign angle badge (custom_signal, persona_pain, case_study, risk_efficiency)
- Status badge (Pending, Approved, Denied, Sent)
- Version badge (v1, v2, v3)
- Target persona/segment
- Score indicator

### [[CampaignEmptySlot]]

Dashed placeholder for unfilled campaign slots. Clicking triggers generation.

## Campaign Angles

Each cycle generates 4 campaigns with distinct angles:

| Angle | Description | Icon |
|-------|-------------|------|
| `custom_signal` | Research-based trigger signal | Target |
| `persona_pain` | Pain point for specific persona | Users |
| `case_study` | Social proof / success story | TrendingUp |
| `risk_efficiency` | Risk mitigation or efficiency gain | Shield |

## Profile Context Tab

The [[ComprehensiveOnboarding]] component displays the client's strategy profile:

- **Collapsible by default** - saves vertical space
- Click header to expand/collapse
- Edit button opens modal for updates
- Shows submission status and last update date

Sections when expanded:
1. Foundation (company info)
2. Offering (product, target customer, ACV)
3. Market Signals (outreach triggers)
4. Audience (job titles, segments, personas)
5. Process (tools, CRM)
6. Messaging (customer voice, ROI, tone)
7. Goals (GTM objectives, success metrics)

## API Endpoints

```typescript
// Cycle management
strategyApi.getCycles(clientId): Promise<{ cycles: CampaignCycle[] }>
strategyApi.getCycle(cycleId): Promise<CampaignCycle>
strategyApi.createCycle(clientId, data): Promise<CampaignCycle>
strategyApi.updateCycle(cycleId, data): Promise<CampaignCycle>
strategyApi.deleteCycle(cycleId): Promise<{ message: string }>
strategyApi.getCampaignsForCycle(cycleId): Promise<{ campaigns: CampaignSequence[] }>
```

## Database Schema

Cycles are stored in `campaign_cycles` table (Migration 013):

```sql
campaign_cycles (
  id UUID PRIMARY KEY,
  client_id UUID REFERENCES clients(id),
  strategy_id UUID REFERENCES strategies(id),
  cycle_number INTEGER,
  cycle_name VARCHAR(255),
  status VARCHAR(50), -- planned, active, completed
  start_date DATE,
  end_date DATE,
  duration_days INTEGER DEFAULT 14,
  target_campaigns INTEGER,
  actual_campaigns INTEGER DEFAULT 0,
  notes TEXT,
  created_at TIMESTAMP,
  updated_at TIMESTAMP
)
```

Campaigns link to cycles via `cycle_id`, `lineage_id`, and `campaign_version` columns on `strategy_suggestions`.

## Related

- [[campaigns]] - Campaign management
- [[strategy-upgrade]] - Spintax workflow improvements
- [[strategy-ai-container]] - AI generation backend
- [[data-models]] - Type definitions

---
Tags: #strategy #cycles #campaigns #feature
