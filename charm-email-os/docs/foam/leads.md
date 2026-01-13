# Leads

Contact records managed per [[campaigns|campaign]].

## Overview

Leads are the contacts targeted by outbound campaigns:

```
Campaign
└── Leads (many)
    - Queued → Contacted → Replied/Bounced
```

## Data Model

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
  // Extended fields
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
  enrichedAt?: Date;
  rawData?: Record<string, string>;
}
```

## Lead Status Flow

```
queued → contacted → replied
                  → bounced
                  → unsubscribed
```

| Status | Description |
|--------|-------------|
| queued | Waiting to be contacted |
| contacted | Email sent |
| replied | Response received |
| bounced | Delivery failed |
| unsubscribed | Opted out |

## CSV Upload

### Column Mapping

Map CSV columns to lead fields:

```typescript
interface CSVColumnMapping {
  csvColumn: string;
  leadField: keyof Lead | 'custom' | 'skip';
  customFieldName?: string;
}
```

### Available Fields

```typescript
const LEAD_FIELD_OPTIONS = [
  'skip',           // Ignore column
  'email',          // Required
  'firstName',
  'lastName',
  'company',
  'title',          // Job title
  'linkedInUrl',
  'phone',
  'website',
  'location',
  'industry',
  'companySize',
  'notes',
  'custom',         // Custom field
];
```

### Upload Flow

1. Select CSV file
2. Preview columns
3. Map columns to fields
4. Validate data
5. Import leads

## Store: [[campaignStore]]

### State
```typescript
{
  campaigns: Campaign[];
  leads: Lead[];
}
```

### Lead Actions
- `uploadLeads(campaignId, leads)` - Add leads from CSV
- `simulateUploadLeads(campaignId, count)` - Generate mock leads
- `updateLeadStatus(id, status)`
- `getLeadsByCampaign(campaignId)`
- `simulateCampaignProgress(campaignId)` - Demo simulation

## Components

| Component | Purpose |
|-----------|---------|
| [[CampaignSidebar]] | Select campaign |
| [[CampaignHeader]] | Campaign info + stats |
| [[LeadsTable]] | Lead data table |
| [[StatsRow]] | Status breakdown |
| [[UploadModal]] | CSV upload flow |
| [[ColumnMappingStep]] | Map CSV columns |
| [[LeadSourceSelector]] | Choose lead source |
| [[ScriptPullModal]] | Script-based import |

## Route

`/clients/[clientId]/leads`

## Lead Sources

| Source | Description |
|--------|-------------|
| manual_upload | CSV file upload |
| script_pull | Automated script import |
| enrichment | Data enrichment service |
| manual_entry | Individual entry |

## Status Colors

| Status | Background | Text |
|--------|------------|------|
| queued | gray-100 | gray-800 |
| contacted | blue-100 | blue-800 |
| replied | green-100 | green-800 |
| bounced | red-100 | red-800 |
| unsubscribed | gray-100 | gray-800 |

## Campaign Stats

The leads table shows aggregated stats:

```
Total: 1,500 | Queued: 1,200 | Contacted: 250 | Replied: 45 | Bounced: 5
```

## Simulation

For demo purposes, `simulateCampaignProgress(campaignId)` simulates:
- Contact 5-10 random queued leads
- 70% marked contacted
- 20% marked replied
- 10% marked bounced

## Related

- [[campaigns]] - Parent entity
- [[health-monitoring]] - Bounce impact on health
- [[data-models]] - Full type definitions

---
Tags: #leads #contacts #csv
