# Charm Email OS - Backend Integration Guide

This document explains how to connect the Charm Email OS frontend to a backend API and integrate the copywriting skill output.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              BACKEND                                         │
│  ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐          │
│  │   API Routes    │───▶│  Copywriting    │───▶│    Database     │          │
│  │   (Next.js or   │    │  Skill (Claude) │    │  (Postgres/etc) │          │
│  │   Express)      │◀───│                 │◀───│                 │          │
│  └─────────────────┘    └─────────────────┘    └─────────────────┘          │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         FRONTEND (Charm Email OS)                            │
│  ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐          │
│  │  Zustand Stores │───▶│   React Pages   │───▶│   UI Components │          │
│  │  (State Mgmt)   │    │   /clients/     │    │   IdeaEditModal │          │
│  │                 │    │   /strategy/    │    │   UploadModal   │          │
│  └─────────────────┘    └─────────────────┘    └─────────────────┘          │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Core Data Types

All types are defined in `lib/types.ts`. The key types for backend integration:

### CampaignIdea (Primary Type)

This is the main data structure that the copywriting skill outputs and the frontend displays/edits.

```typescript
interface CampaignIdea {
  id: string;
  clientId: string;

  // === STRATEGY TAB ===
  campaignType?: 'custom_signal' | 'creative_ideas' | 'whole_offer' | 'fallback';
  industry: string;
  segment: string;
  title: string;
  angle: string;
  icpDescription?: string;
  valueProposition?: {
    business: string;  // What the company gets
    personal: string;  // What they personally get
  };
  objections?: string[];
  constraintBox?: string[];  // 3-5 features for creative_ideas type only

  // === VARIABLES TAB (Clay columns) ===
  variables?: ClayVariables;

  // === COPY TAB ===
  email1?: EmailCopy;
  creativeIdeas?: CreativeIdea[];  // For creative_ideas campaign type

  // === SEQUENCE TAB ===
  followUps?: FollowUpEmail[];

  // === QA TAB ===
  qaScore?: QAScore;

  // === META ===
  status: 'pending' | 'approved' | 'rejected' | 'editing';
  generatedAt: Date;
}
```

### ClayVariables (Variable Mapping)

Maps to Clay enrichment columns. The frontend displays these as editable fields.

```typescript
interface ClayVariables {
  // Core variables (always present)
  core: {
    firstName?: string;      // {{first_name}}
    companyName?: string;    // {{company}}
    roleTitle?: string;      // {{title}}
  };

  // High-signal variables (from research/enrichment)
  highSignal?: {
    tenureYears?: string;      // {{tenure_years}}
    recentPostTopic?: string;  // {{recent_post_topic}}
    recentPostDate?: string;   // {{recent_post_date}}
    competitor?: string;       // {{competitor_used}}
    stackCrm?: string;         // {{current_crm}}
    hiringRoles?: string;      // {{open_roles}}
    pressHeadline?: string;    // {{press_headline}}
    eventDate?: string;        // {{event_date}}
  };

  // AI-generated variables (from Claygent or similar)
  aiGenerated?: {
    customerDescription?: string;  // {{ai_customer_desc}}
    customerType?: string;         // {{ai_customer_type}}
    customGeneration?: string;     // {{ai_opener}}
  };

  // Case study variables
  caseStudy?: {
    company?: string;     // Reference company name
    result?: string;      // What they achieved
    metric?: string;      // Specific number/percentage
    timeframe?: string;   // How long it took
  };

  // Campaign-specific custom variables
  custom?: Record<string, string>;
}
```

### EmailCopy

```typescript
interface EmailCopy {
  subject: string;  // Can contain {{variables}}
  body: string;     // Can contain {{variables}}
  cta: string;      // Call to action line
}
```

### FollowUpEmail

```typescript
interface FollowUpEmail {
  day: number;        // Days after initial email (3, 7, 14, etc.)
  subject?: string;   // Empty string = threads to previous email
  angle: string;      // Value prop angle for this follow-up
  copy: EmailCopy;
}
```

### CreativeIdea (for creative_ideas campaign type)

```typescript
interface CreativeIdea {
  feature: string;   // Product feature being highlighted
  action: string;    // Specific action/use case
  target: string;    // Who benefits
  benefit: string;   // What they get
}
```

### QAScore

```typescript
interface QAScore {
  total: number;                  // 0-100 overall score
  situationRecognition: number;   // 0-25: Does it recognize their situation?
  valueClarity: number;           // 0-25: Is value proposition clear?
  personalizationQuality: number; // 0-20: Real personalization or templated?
  ctaEffort: number;              // 0-15: Is CTA low-friction?
  length: number;                 // 0-10: Appropriate length?
  subjectLine: number;            // 0-5: Is subject compelling?
}
```

### Lead (for CSV upload/script pull)

```typescript
interface Lead {
  id: string;
  campaignId: string;
  email: string;
  firstName: string;
  lastName: string;
  company: string;
  title: string;
  status: 'queued' | 'contacted' | 'replied' | 'bounced' | 'unsubscribed';
  contactedAt?: Date;

  // Enhanced fields
  linkedInUrl?: string;
  phone?: string;
  website?: string;
  location?: string;
  industry?: string;
  companySize?: string;
  notes?: string;
  tags?: string[];
  source?: 'manual_upload' | 'script_pull' | 'enrichment' | 'manual_entry';
  customFields?: Record<string, string>;
  enrichedAt?: Date;
  rawData?: Record<string, string>;  // Original CSV row
}
```

---

## Required API Endpoints

### Strategy / Campaign Ideas

| Method | Endpoint | Description | Request Body | Response |
|--------|----------|-------------|--------------|----------|
| `POST` | `/api/clients/{clientId}/ideas/generate` | Generate campaign ideas via copywriting skill | `{ industry, segment }` | `CampaignIdea[]` |
| `GET` | `/api/clients/{clientId}/ideas` | List all ideas for a client | - | `CampaignIdea[]` |
| `GET` | `/api/ideas/{ideaId}` | Get single idea | - | `CampaignIdea` |
| `PUT` | `/api/ideas/{ideaId}` | Update idea (from edit modal) | `Partial<CampaignIdea>` | `CampaignIdea` |
| `POST` | `/api/ideas/{ideaId}/approve` | Approve idea → creates Campaign | - | `Campaign` |
| `POST` | `/api/ideas/{ideaId}/reject` | Reject/send back for editing | - | `CampaignIdea` |

### Campaigns & Leads

| Method | Endpoint | Description | Request Body | Response |
|--------|----------|-------------|--------------|----------|
| `GET` | `/api/clients/{clientId}/campaigns` | List campaigns | - | `Campaign[]` |
| `POST` | `/api/campaigns/{campaignId}/leads` | Upload leads | `Lead[]` | `{ imported: number }` |
| `GET` | `/api/campaigns/{campaignId}/leads` | List leads | - | `Lead[]` |
| `POST` | `/api/campaigns/{campaignId}/run` | Start campaign | - | `Campaign` |
| `POST` | `/api/campaigns/{campaignId}/pause` | Pause campaign | - | `Campaign` |

### Clients

| Method | Endpoint | Description | Request Body | Response |
|--------|----------|-------------|--------------|----------|
| `GET` | `/api/clients` | List all clients | - | `Client[]` |
| `POST` | `/api/clients` | Create client | `Client` | `Client` |
| `PUT` | `/api/clients/{clientId}` | Update client | `Partial<Client>` | `Client` |
| `PUT` | `/api/clients/{clientId}/onboarding` | Save onboarding data | `OnboardingData` | `Client` |

---

## Copywriting Skill Output Format

When your backend calls the copywriting skill (Claude), it should return data matching the `CampaignIdea` structure. Here's a complete example:

```json
{
  "id": "idea_abc123",
  "clientId": "client_xyz",
  "campaignType": "custom_signal",
  "industry": "SaaS",
  "segment": "Series A Startups",
  "title": "Stack Migration Play",
  "angle": "Help companies consolidate their fragmented tech stack before it becomes unmanageable",

  "icpDescription": "VP Sales or RevOps at Series A B2B SaaS companies currently using 3+ disconnected sales tools",

  "valueProposition": {
    "business": "Reduce tool sprawl by 60%, cut software costs by $2k/month, eliminate data sync issues",
    "personal": "Less context switching, cleaner pipeline data, faster onboarding for new reps"
  },

  "objections": [
    "We just implemented our current stack 6 months ago",
    "Migration is too risky mid-quarter",
    "Our team is used to the current tools",
    "We don't have bandwidth for another implementation"
  ],

  "constraintBox": null,

  "variables": {
    "core": {
      "firstName": "{{first_name}}",
      "companyName": "{{company}}",
      "roleTitle": "{{title}}"
    },
    "highSignal": {
      "tenureYears": "{{tenure_years}}",
      "recentPostTopic": "{{recent_post_topic}}",
      "competitor": "{{competitor_crm}}",
      "stackCrm": "{{current_crm}}",
      "hiringRoles": "{{sales_roles_hiring}}"
    },
    "aiGenerated": {
      "customerDescription": "{{ai_customer_description}}",
      "customGeneration": "{{ai_personalized_opener}}"
    },
    "caseStudy": {
      "company": "TechFlow",
      "result": "consolidated 5 sales tools into 1 platform",
      "metric": "40% reduction in sales admin time",
      "timeframe": "6 weeks"
    },
    "custom": {
      "stack_size": "{{num_sales_tools}}",
      "pain_signal": "{{detected_pain_point}}"
    }
  },

  "email1": {
    "subject": "{{firstName}}, saw you're scaling sales at {{companyName}}",
    "body": "Hey {{firstName}},\n\nNoticed {{companyName}} is hiring {{hiringRoles}} - congrats on the growth.\n\nQuick question: are you finding it harder to keep your sales stack in sync as the team grows? {{ai_personalized_opener}}\n\nWe helped {{caseStudy.company}} {{caseStudy.result}} in just {{caseStudy.timeframe}}.\n\n{{cta}}",
    "cta": "Worth a 15-min call to see if we can help you avoid the same growing pains?"
  },

  "creativeIdeas": null,

  "followUps": [
    {
      "day": 3,
      "subject": "",
      "angle": "Social proof + specific metric",
      "copy": {
        "subject": "",
        "body": "Quick follow-up on my last note.\n\nOne thing I forgot to mention - {{caseStudy.company}} saw {{caseStudy.metric}} after switching. Their VP Sales said the biggest win was having one source of truth for pipeline data.\n\nWould that kind of result move the needle for {{companyName}}?",
        "cta": "Happy to share exactly how they did it."
      }
    },
    {
      "day": 7,
      "subject": "Quick resource for {{companyName}}",
      "angle": "Value-add breakup",
      "copy": {
        "subject": "Quick resource for {{companyName}}",
        "body": "Hey {{firstName}},\n\nI'll stop filling your inbox after this - I know you're busy scaling.\n\nBut I put together a quick checklist we use internally: '5 Signs Your Sales Stack Needs Consolidation.' Figured it might be useful regardless of whether we chat.\n\nWant me to send it over?",
        "cta": "Either way, best of luck with the growth."
      }
    },
    {
      "day": 14,
      "subject": "",
      "angle": "Timing check + easy out",
      "copy": {
        "subject": "",
        "body": "Last one from me, {{firstName}}.\n\nIf consolidating your sales stack isn't a priority right now, totally get it. But if it becomes one in the next quarter, I'd love to be a resource.\n\nIs there a better time to reconnect, or should I close the loop for now?",
        "cta": ""
      }
    }
  ],

  "qaScore": {
    "total": 84,
    "situationRecognition": 23,
    "valueClarity": 22,
    "personalizationQuality": 17,
    "ctaEffort": 13,
    "length": 6,
    "subjectLine": 3
  },

  "status": "pending",
  "generatedAt": "2024-01-15T10:30:00.000Z"
}
```

---

## Frontend Store Integration Points

The frontend uses Zustand stores. To connect to your backend, modify these files:

### `lib/stores/strategyStore.ts`

Currently mocked. Replace with API calls:

```typescript
// CURRENT (mocked):
generateIdeas: (clientId, industry, segment) => {
  const newIdeas = SAMPLE_ANGLES.map(...);  // Mock data
  set((state) => ({ ideas: [...state.ideas, ...newIdeas] }));
  return newIdeas;
}

// REPLACE WITH:
generateIdeas: async (clientId, industry, segment) => {
  const response = await fetch(`/api/clients/${clientId}/ideas/generate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ industry, segment })
  });
  const newIdeas: CampaignIdea[] = await response.json();
  set((state) => ({ ideas: [...state.ideas, ...newIdeas] }));
  return newIdeas;
}

// Also update:
updateIdea: async (id, data) => {
  await fetch(`/api/ideas/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data)
  });
  set((state) => ({
    ideas: state.ideas.map((idea) =>
      idea.id === id ? { ...idea, ...data } : idea
    ),
  }));
}

approveIdea: async (id) => {
  await fetch(`/api/ideas/${id}/approve`, { method: 'POST' });
  set((state) => ({
    ideas: state.ideas.map((idea) =>
      idea.id === id ? { ...idea, status: 'approved' } : idea
    ),
  }));
}
```

### `lib/stores/campaignStore.ts`

For leads and campaign management:

```typescript
// Replace simulateUploadLeads with:
uploadLeads: async (campaignId, leads: Lead[]) => {
  const response = await fetch(`/api/campaigns/${campaignId}/leads`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(leads)
  });
  const result = await response.json();
  // Refresh leads list
  const leadsResponse = await fetch(`/api/campaigns/${campaignId}/leads`);
  const updatedLeads = await leadsResponse.json();
  set((state) => ({
    leads: { ...state.leads, [campaignId]: updatedLeads }
  }));
  return result;
}
```

---

## Component to Data Mapping

| Component | Data Source | Store Method |
|-----------|-------------|--------------|
| `IdeaCard` | `CampaignIdea` | `strategyStore.getIdeasByClient()` |
| `IdeaEditModal` (Strategy Tab) | `campaignType`, `industry`, `segment`, `title`, `angle`, `icpDescription`, `valueProposition`, `objections`, `constraintBox` | `strategyStore.updateIdea()` |
| `IdeaEditModal` (Variables Tab) | `variables.core`, `variables.highSignal`, `variables.aiGenerated`, `variables.caseStudy`, `variables.custom` | `strategyStore.updateIdea()` |
| `IdeaEditModal` (Copy Tab) | `email1`, `creativeIdeas` | `strategyStore.updateIdea()` |
| `IdeaEditModal` (Sequence Tab) | `followUps[]` | `strategyStore.updateIdea()` |
| `IdeaEditModal` (QA Tab) | `qaScore` (read-only display) | - |
| `CreateCampaignModal` | Same as IdeaEditModal | `strategyStore.setIdeas()` (adds new) |
| `UploadModal` | CSV → `Lead[]` | `campaignStore.uploadLeads()` |
| `LeadsTable` | `Lead[]` | `campaignStore.getLeadsByCampaign()` |

---

## Campaign Types Explained

The `campaignType` field determines which fields are relevant:

### `custom_signal`
- Uses high-signal variables heavily
- Personalization based on specific research (LinkedIn posts, job changes, etc.)
- `constraintBox` is null

### `creative_ideas`
- Uses `constraintBox` (3-5 product features to constrain ideas to)
- `creativeIdeas[]` array is populated with feature/action/target/benefit combos
- Good for product-led outreach

### `whole_offer`
- Full value proposition approach
- Heavy use of `valueProposition.business` and `valueProposition.personal`
- `constraintBox` is null

### `fallback`
- Generic but compelling outreach
- Minimal personalization variables
- Used when research yields limited signals

---

## CSV Upload Flow

1. User clicks "Add Leads" → LeadSourceSelector modal
2. User selects "Manual CSV Upload" → UploadModal opens
3. User uploads CSV file → ColumnMappingStep shows
4. User maps CSV columns to Lead fields:
   - `email` (required)
   - `firstName` (recommended)
   - `lastName`, `company`, `title`, etc.
   - Custom fields supported
5. On confirm, `Lead[]` array is created from mapped data
6. `campaignStore.uploadLeads(campaignId, leads)` sends to backend

### CSVColumnMapping Type

```typescript
interface CSVColumnMapping {
  csvColumn: string;                        // Original CSV header
  leadField: keyof Lead | 'custom' | 'skip'; // Target field
  customFieldName?: string;                  // If leadField is 'custom'
}
```

---

## Script Pull (Future)

The ScriptPullModal is a placeholder for future integration. When implemented:

1. User configures targeting criteria (from campaign's segment/industry)
2. Backend script pulls leads from data sources (Apollo, LinkedIn, etc.)
3. Leads are enriched with Clay variables
4. Returns `Lead[]` with populated `customFields` matching campaign variables

---

## Quick Start Checklist

1. [ ] Implement API endpoints listed above
2. [ ] Modify `strategyStore.ts` to call your API instead of using mock data
3. [ ] Modify `campaignStore.ts` for leads management
4. [ ] Configure your copywriting skill to output the `CampaignIdea` JSON structure
5. [ ] Test the flow: Generate Ideas → Edit → Approve → Upload Leads

---

## File Locations

```
projects/charm-email-os/
├── lib/
│   ├── types.ts              # All TypeScript interfaces
│   └── stores/
│       ├── strategyStore.ts  # Campaign ideas state (MODIFY FOR API)
│       ├── campaignStore.ts  # Campaigns & leads state (MODIFY FOR API)
│       └── clientStore.ts    # Client state (MODIFY FOR API)
├── components/
│   ├── strategy/
│   │   ├── IdeaCard.tsx          # Displays CampaignIdea summary
│   │   ├── IdeaEditModal.tsx     # Full editor with 5 tabs
│   │   └── CreateCampaignModal.tsx # Manual campaign creation
│   └── leads/
│       ├── UploadModal.tsx       # CSV upload with parsing
│       ├── ColumnMappingStep.tsx # CSV column mapper
│       ├── LeadSourceSelector.tsx # Upload vs Script Pull choice
│       └── ScriptPullModal.tsx   # Placeholder for script integration
└── app/
    └── clients/
        └── [clientId]/
            ├── strategy/page.tsx # Strategy page
            └── leads/page.tsx    # Leads page
```
