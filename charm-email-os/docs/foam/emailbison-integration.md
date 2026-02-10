---
title: EmailBison Integration
created: 2026-02-09
updated: 2026-02-09
tags: [concept, infrastructure, integration, emailbison]
---

# EmailBison Integration

Real-time inbox metrics from EmailBison API powering the [[infrastructure]] health dashboard.

## Overview

EmailBison is the email sending platform that hosts Charm's sending infrastructure. The integration fetches live data for:

- **Connection status** - Which inboxes are connected vs disconnected
- **Health scores** - Per-inbox health (0-100 scale)
- **Bounce rates** - Hard/soft bounce metrics
- **Provider breakdown** - Microsoft vs Google inbox distribution

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│ Frontend: Active Inventory Tab                                   │
│                                                                  │
│ ┌───────────────────────────────────────────────────────────┐   │
│ │ InventoryHealthDashboard                                   │   │
│ │ • Total Inboxes    • Connection Rate    • Health Score    │   │
│ │ • Provider Cards   • Needs Attention List                 │   │
│ └───────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                              │
                              │ GET /api/health/inventory/{clientId}
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ Backend: FastAPI (api/routes/health.py)                          │
│                                                                  │
│ 1. Get client's workspace name from database                    │
│ 2. Call EmailBisonService.get_workspace_summary()               │
│ 3. Merge with RBL domain data from local DB                     │
│ 4. Return unified InventoryHealthResponse                       │
└─────────────────────────────────────────────────────────────────┘
                              │
                              │ EmailBison API
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ EmailBison API (https://spellcast.hirecharm.com)                 │
│                                                                  │
│ 1. GET /api/workspaces/v1.1      → List workspaces, get team_id │
│ 2. POST /api/workspaces/v1.1/switch-workspace                   │
│ 3. GET /api/sender-emails        → Paginated inbox list         │
└─────────────────────────────────────────────────────────────────┘
```

## API Workflow

EmailBison requires a specific 3-step API workflow:

### Step 1: Find Workspace ID

```python
response = await client.get("/api/workspaces/v1.1")
workspaces = response.json()["data"]
workspace_id = next(ws["id"] for ws in workspaces if ws["name"] == "Charm")
```

### Step 2: Switch Workspace Context

```python
await client.post(
    "/api/workspaces/v1.1/switch-workspace",
    json={"team_id": workspace_id}
)
```

### Step 3: Fetch Inbox Data

```python
response = await client.get("/api/sender-emails", params={"page": 1, "per_page": 100})
inboxes = response.json()["data"]
```

## Response Data Structure

### EmailBison Inbox Fields

| Field | Type | Description |
|-------|------|-------------|
| `email` | string | Inbox email address |
| `connection_status` | string | "connected" or status value |
| `health_score` | int | 0-100 health metric |
| `esp_type` | string | "microsoft" or "google" |
| `bounced` | int | Total hard bounces |
| `emails_sent` | int | Total emails sent |

### Inventory Health Response

```typescript
interface InventoryHealth {
  // Workspace identification
  clientId: string;
  clientName: string;
  workspaceName?: string;

  // EmailBison metrics (real-time)
  totalInboxes: number;
  connectedInboxes: number;
  disconnectedInboxes: number;
  avgHealthScore: number;
  connectionRate: number;

  // Provider breakdown
  providers: {
    name: string;
    count: number;
    connected: number;
    connectionRate: number;
    avgHealth: number;
  }[];

  // Domain metrics (from RBL/database)
  totalDomains: number;
  cleanDomains: number;
  flaggedDomains: number;

  // Issues needing attention
  attentionItems: InventoryAttentionItem[];

  // Data source info
  emailbisonAvailable: boolean;
  emailbisonError?: string;
  rblLastCheck?: Date;
}
```

## Configuration

### Environment Variables

| Variable | Purpose | Default |
|----------|---------|---------|
| `EMAILBISON_API_KEY` | Bearer token for API auth | (required) |
| `EMAILBISON_API_URL` | Base API URL | `https://spellcast.hirecharm.com` |

### Backend Service

```python
# api/services/emailbison.py
class EmailBisonService:
    async with EmailBisonService() as bison:
        summary = await bison.get_workspace_summary("Charm")
```

## UI Components

### [[InventoryHealthDashboard]]

Dashboard component displaying real-time EmailBison data:

| Section | Data Source | Content |
|---------|-------------|---------|
| Stat Cards | EmailBison | Total/Connected/Domains/Health |
| Provider Breakdown | EmailBison | Microsoft vs Google metrics |
| Needs Attention | RBL + EmailBison | Blacklisted domains, high-bounce inboxes |
| Status Indicator | EmailBison | "Live" or error state |

## Data Freshness

| Data Type | Source | Freshness |
|-----------|--------|-----------|
| Inbox count/status | EmailBison API | Real-time (on page load) |
| Health scores | EmailBison API | Real-time |
| Bounce rates | EmailBison API | Real-time |
| Domain blacklists | Local RBL checks | Periodic (2-24 hour lag) |

## Known Limitations

1. **Provider Detection** - Some workspaces may show "Unknown" provider if `esp_type` field is not populated
2. **No Background Sync** - Data is fetched on-demand, not continuously synced to local DB
3. **API Rate Limits** - Large workspaces may hit pagination limits

## Future Enhancements

See [[health-monitoring]] Phase 6C for planned background sync worker that would:
- Periodically pull EmailBison data to local database
- Enable historical trending
- Reduce API calls on page loads

## Related

- [[infrastructure]] - Domain and inbox management
- [[health-monitoring]] - Kill triggers and health tracking
- [[InventoryHealthDashboard]] - UI component
- [[system-integration]] - Full platform data flow

---
Tags: #emailbison #integration #api #real-time
