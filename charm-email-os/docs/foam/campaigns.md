# Campaigns

Email campaigns created from approved [[campaign-ideas]].

## Overview

Campaigns are the execution layer for outbound email:

```
CampaignIdea (Strategy)
    ↓ Approve
Campaign (Execution)
    ↓ Upload
Leads (Contacts)
```

## Campaign Idea

### Data Model

```typescript
type CampaignIdeaStatus = 'pending' | 'approved' | 'rejected' | 'editing';
type CampaignType = 'custom_signal' | 'creative_ideas' | 'whole_offer' | 'fallback';

interface CampaignIdea {
  id: string;
  clientId: string;
  industry: string;
  segment: string;
  title: string;
  angle: string;
  campaignType?: CampaignType;
  variables?: ClayVariables;
  email1?: EmailCopy;
  followUps?: FollowUpEmail[];
  qaScore?: QAScore;
  status: CampaignIdeaStatus;
  generatedAt: Date;
}
```

### Clay Variables

Variables for email personalization:

```typescript
interface ClayVariables {
  core: {
    firstName?: string;
    companyName?: string;
    roleTitle?: string;
  };
  highSignal?: {
    tenureYears?: string;
    recentPostTopic?: string;
    competitor?: string;
    // ... more
  };
  aiGenerated?: { /* ... */ };
  custom?: Record<string, string>;
  caseStudy?: { /* ... */ };
}
```

## Campaign

### Data Model

```typescript
type CampaignStatus = 'draft' | 'active' | 'paused' | 'completed';

interface Campaign {
  id: string;
  clientId: string;
  ideaId: string;           // Link to source idea
  name: string;
  industry: string;
  segment: string;
  angle: string;
  status: CampaignStatus;
  leadsTotal: number;
  leadsContacted: number;
  leadsCapacity: number;    // e.g., 3000
  repliesCount: number;
  createdAt: Date;
}
```

## Stores

### [[strategyStore]] - Ideas

```typescript
{
  ideas: CampaignIdea[];
}
```

Actions:
- `generateIdeas(clientId, industry, segment)`
- `approveIdea(id)` / `rejectIdea(id)`
- `getPendingIdeas(clientId)` / `getApprovedIdeas(clientId)`

### [[campaignStore]] - Campaigns

```typescript
{
  campaigns: Campaign[];
  leads: Lead[];
}
```

Actions:
- `createCampaignFromIdea(idea)`
- `runCampaign(id)` / `pauseCampaign(id)`
- `getCampaignsByClient(clientId)`

## Workflow

### 1. Generate Ideas

```
Industry + Segment → AI Generation → Pending Ideas
```

Sample angles generated:
- Pain Point Pivot
- Industry Benchmark
- Case Study Teaser
- Time-Sensitive Opportunity
- Mutual Connection
- Contrarian Take
- Quick Win Offer
- Competitor Gap

### 2. Review & Approve

```
Pending → Review → Approve/Edit/Reject
```

### 3. Create Campaign

```
Approved Idea → Create Campaign → Draft Campaign
```

### 4. Fill Leads

Leads come from two sources:

```
Option A: CSV Upload
  Draft Campaign → Upload CSV → Leads Added

Option B: Lead Refinery (automated)
  Draft Campaign → Extract ICP from strategy goals
    → Query DuckDB reservoir (75.4M leads)
    → Validate through [[lead-refinery-gates|Gates 0-3]]
    → Push verified leads into EmailBison campaign
```

The [[lead-refinery]] connects campaign strategy to the lead reservoir. ICP criteria from [[clients|client onboarding]] (industry, titles, company size, geography) drive the DuckDB query. See [[lead-tam-map]] for the full closed-loop flow where campaign performance feeds back to improve future pulls.

### 5. Execute

```
Draft → Run → Active → Progress → Completed
                         ↓
              Performance data syncs back
              to [[lead-dispositions]] in DuckDB
```

## Components

### Strategy Tab
| Component | Purpose |
|-----------|---------|
| [[IdeaCard]] | Display idea with approve/reject |
| [[IdeaEditModal]] | Edit idea details |
| [[ApprovedCampaignRow]] | Approved ideas list |
| [[CreateCampaignModal]] | Convert to campaign |

### Leads Tab
| Component | Purpose |
|-----------|---------|
| [[CampaignSidebar]] | Campaign selection |
| [[CampaignHeader]] | Campaign info |
| [[LeadsTable]] | Lead data |
| [[UploadModal]] | CSV upload |

## Routes

- `/clients/[clientId]/strategy` - Ideas and campaign creation
- `/clients/[clientId]/leads` - Lead management per campaign

## Status Colors

| Status | Background | Text |
|--------|------------|------|
| pending | yellow-100 | yellow-800 |
| editing | blue-100 | blue-800 |
| approved | blue-100 | blue-800 |
| rejected | red-100 | red-800 |
| draft | gray-100 | gray-800 |
| active | green-100 | green-800 |
| paused | yellow-100 | yellow-800 |
| completed | green-100 | green-800 |

## Related

- [[campaign-ideas]] - Strategy details
- [[leads]] - Lead management
- [[clients]] - Parent entity
- [[strategy]] - Workflow details
- [[lead-refinery]] - Automated lead filling from 75.4M reservoir
- [[lead-tam-map]] - Performance data flows back to build TAM map
- [[lead-dispositions]] - Lead state tracking post-campaign
- [[system-integration]] - How Charm OS, Lead Refinery, and EmailBison connect
- [[infrastructure]] - Sending domains and inboxes

---
Tags: #campaigns #strategy #outbound
