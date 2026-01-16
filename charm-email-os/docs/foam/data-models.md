# Data Models

Core TypeScript types and interfaces used throughout the application.

## Entity Overview

```
Client
├── Domain (1:many)
│   └── Inbox (1:many)
├── OnboardingSubmission (1:1 active) → see [[onboarding-form]]
│   ├── Segment (1:many)
│   └── Persona (1:many)
├── CampaignIdea (1:many)
│   └── Campaign (1:1 when approved)
│       └── Lead (1:many)
└── HealthMetrics
```

## [[clients|Client]]

```typescript
interface Client {
  id: string;
  name: string;
  domain: string;
  logo?: string;
  onboardingComplete: boolean;
  onboardingData?: OnboardingData;
  createdAt: Date;
}

interface OnboardingData {
  contactFirstNames: string[];
  primaryDomain: string;
  industry: string;
  product: string;
  inboxesNeeded: number;
  notes?: string;
}
```

## [[domains|Domain]]

```typescript
type DomainStatus =
  | 'pending_approval'
  | 'approved'
  | 'rejected'
  | 'purchasing'
  | 'active'
  | 'warming';

interface Domain {
  id: string;
  clientId: string;
  domain: string;
  status: DomainStatus;
  healthScore?: number;
  createdAt: Date;
  healthState?: 'live' | 'flagged' | 'dead';
  flaggedAt?: Date;
  deadAt?: Date;
}
```

## [[inboxes|Inbox]]

```typescript
type InboxStatus =
  | 'pending_approval'
  | 'approved'
  | 'rejected'
  | 'provisioning'
  | 'active'
  | 'warming';

interface Inbox {
  id: string;
  clientId: string;
  domainId: string;
  email: string;
  firstName: string;
  lastName: string;
  status: InboxStatus;
  warmupProgress?: number;
  dailySendLimit?: number;
  createdAt: Date;
  healthState?: 'live' | 'dead';
  killedAt?: Date;
  killReason?: string;
  provider?: 'gmail' | 'microsoft' | 'other';
}
```

## [[campaign-ideas|Campaign Idea]]

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

## [[campaigns|Campaign]]

```typescript
type CampaignStatus = 'draft' | 'active' | 'paused' | 'completed';

interface Campaign {
  id: string;
  clientId: string;
  ideaId: string;
  name: string;
  industry: string;
  segment: string;
  angle: string;
  status: CampaignStatus;
  leadsTotal: number;
  leadsContacted: number;
  leadsCapacity: number;
  repliesCount: number;
  createdAt: Date;
}
```

## [[leads|Lead]]

```typescript
type LeadStatus = 'queued' | 'contacted' | 'replied' | 'bounced' | 'unsubscribed';
type LeadSource = 'manual_upload' | 'script_pull' | 'enrichment' | 'manual_entry';

interface Lead {
  id: string;
  campaignId: string;
  email: string;
  firstName: string;
  lastName: string;
  company: string;
  title: string;
  status: LeadStatus;
  contactedAt?: Date;
  linkedInUrl?: string;
  phone?: string;
  website?: string;
  location?: string;
  industry?: string;
  companySize?: string;
  notes?: string;
  tags?: string[];
  source?: LeadSource;
  customFields?: Record<string, string>;
}
```

## Health Types

See [[health-monitoring]] for detailed health-related types:

- `InboxHealthState`: `'live' | 'dead'`
- `DomainHealthState`: `'live' | 'flagged' | 'dead'`
- `CampaignHealthState`: `'live' | 'quarantined' | 'dead'`
- `DomainLifecyclePhase`: warming → ramping → establishing → peak → monitoring → rotation
- `KillTriggerType`: Various conditions that trigger inbox termination

## Status Colors

Consistent color mappings for status badges:

| Status | Background | Text |
|--------|------------|------|
| pending_approval | yellow-100 | yellow-800 |
| approved | blue-100 | blue-800 |
| rejected | red-100 | red-800 |
| active | green-100 | green-800 |
| warming | orange-100 | orange-800 |

## Related

- [[architecture]] - System structure
- [[state-management]] - How data is managed
- [[health-monitoring]] - Health type details

---
Tags: #types #models #data
