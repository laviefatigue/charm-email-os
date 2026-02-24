---
title: Client Dashboard - Operations View (Internal Context)
created: 2026-02-23
tags: [dashboard, operations, capacity, internal-view]
---

# Client Dashboard: Operations View (Internal Context)

## Key Clarification

**Dashboard Purpose:** Client visibility into infrastructure health + **YOUR team's operational response**

**NOT:** Client self-service purchasing
**YES:** Transparency showing "we detected the gap and already ordered replacements"

---

## Reframed Capacity Chart: Operations Response View

### What Clients See

```
SENDING CAPACITY & OPERATIONS RESPONSE (90-day view)
┌─────────────────────────────────────────────────────────────────────────┐
│  Volume                                                                  │
│  100K ┃                                                                  │
│       ┃                  ╱╲        ╱╲                                    │
│   75K ┃     ╱─────╲    ╱  ╲      ╱  ╲   ← Sending volume (actual)      │
│       ┃   ╱         ╲╱      ╲  ╱      ╲                                 │
│   50K ┃ ╱                    ╲╱         ╲                               │
│       ┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ ← 100% capacity      │
│   25K ┃                                                                  │
│       ┃                                     ▼ Incubating (warming)      │
│     0 ┗━━━━━━━━┯━━━━━━━━┯━━━━━━━━┯━━━━━━━━┯━━━━━━━━┯━━━━━━━━━━━━━━━  │
│               Jan     Feb     Mar     Apr     May    Now   Forecast     │
│                                                                          │
│  OPERATIONAL STATUS:                                                     │
│  ⚠️ Feb 15: Kill spike (50 inboxes lost, capacity -30%)                 │
│  ✅ Feb 16: RESPONSE → Ordered 2 Hypertide packs (200 inboxes)          │
│  🟢 Feb 23: 120 inboxes warming (ready March 2)                         │
│  ✅ PROACTIVE → Additional order placed for March expansion             │
│  💚 Status: MANAGED - Capacity maintained at 100%                       │
└─────────────────────────────────────────────────────────────────────────┘
```

### Key Messaging Shift

**OLD (Self-Service Framing):**
- ❌ "Need +150 inboxes by March 15"
- ❌ "Recommendation: Order 2 Hypertide packs"
- ❌ Implies client should take action

**NEW (Operations Response Framing):**
- ✅ "Kill spike detected Feb 15 (-50 inboxes)"
- ✅ "RESPONSE: Ordered 2 Hypertide packs Feb 16"
- ✅ "Status: 120 inboxes warming, ready March 2"
- ✅ "Proactive order placed for Q2 expansion"
- ✅ Shows YOU are already handling it

---

## Updated Dashboard Components

### 1. Capacity Status Card (KPI)

**OLD:**
```
┌─────────────────────────────┐
│ Capacity Gap                │
│ Need +150 inboxes by 3/15   │
└─────────────────────────────┘
```

**NEW:**
```
┌─────────────────────────────┐
│ Operations Status           │
│ ✅ MANAGED                  │
│ 120 warming (ready 3/2)     │
└─────────────────────────────┘
```

**Color Coding:**
- 🟢 **MANAGED** - Gap detected, order placed, pipeline refilling
- 🟡 **MONITORING** - Small dip, watching trend, may order soon
- 🟠 **RESPONDING** - Active kill spike, order in progress
- 🔴 **CRITICAL** - Unexpected spike, emergency order needed

### 2. Operations Timeline (New Component)

Shows YOUR team's response chronology:

```
OPERATIONS RESPONSE TIMELINE
┌─────────────────────────────────────────────────────────────────────────┐
│  Feb 15, 9:30 AM  │ ⚠️ Kill spike detected (50 inboxes, bounce rate)   │
│  Feb 15, 10:45 AM │ 🔍 Root cause: Bad lead list from Campaign X        │
│  Feb 16, 8:00 AM  │ ✅ Ordered 2 Hypertide packs (200 inboxes)          │
│  Feb 16, 2:00 PM  │ 🚫 Campaign X quarantined, lead source flagged      │
│  Feb 18, 9:00 AM  │ 📦 Hypertide order fulfilled (200 inboxes created)  │
│  Feb 18-Mar 2     │ 🔥 Warming phase (14 days)                          │
│  Mar 2            │ 🟢 120 inboxes ready for deployment                 │
│  Mar 5 (planned)  │ 📈 Proactive order for Q2 campaign expansion        │
└─────────────────────────────────────────────────────────────────────────┘
```

**Purpose:**
- Shows incident → response → resolution flow
- Demonstrates proactive management
- Builds client confidence ("they're on top of it")

### 3. Capacity Annotations (Enhanced)

Capacity chart now shows **response annotations**, not just problems:

```
│  Volume
│  100K ┃                 ⚠️ Kill spike
│       ┃                  ╱╲  │      ╱╲
│   75K ┃     ╱─────╲    ╱  ╲ │     ╱  ╲
│       ┃   ╱         ╲╱      ╲│   ╱      ╲
│   50K ┃ ╱                    ╲╱           ╲
│       ┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ ← 100% capacity
│   25K ┃                     ✅ Order placed
│       ┃                       │    🟢 Warming complete
│     0 ┗━━━━━━━━━━━━━━━━━━━━━━┿━━━━━┿━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
│               Jan     Feb 15  Feb 16  Mar 2     Now
│                         │       │       │
│                         └───────┴───────┘
│                         Response cycle: 15 days
```

**Annotation Types:**
- ⚠️ **Problem detected** (kill spike, capacity drop)
- ✅ **Order placed** (infrastructure team response)
- 🔥 **Warming phase** (inboxes incubating)
- 🟢 **Ready to deploy** (capacity restored)
- 📈 **Proactive order** (planned expansion)

---

## Messaging Framework

### Client-Facing Language

**Scenario 1: Kill Spike Happens**

❌ **OLD (Blame/Gap Focus):**
> "You lost 50 inboxes. You need to order more."

✅ **NEW (Response/Management Focus):**
> "Kill spike detected on Feb 15 (50 inboxes, bad lead list). We immediately:
> - Quarantined the campaign
> - Ordered 2 Hypertide packs (200 inboxes)
> - 120 inboxes now warming, ready March 2
> - Capacity will be restored to 100%"

**Scenario 2: Proactive Planning**

❌ **OLD (Gap Alert):**
> "You'll run out of capacity by March 15. Order now."

✅ **NEW (Proactive Management):**
> "Based on your Q2 campaign plans, we've proactively ordered additional capacity.
> No action needed on your end - we're ahead of the curve."

**Scenario 3: Healthy State**

❌ **OLD (Dry Status):**
> "Capacity: 85%"

✅ **NEW (Confidence Building):**
> "Status: MANAGED
> - Current capacity: 85% (healthy)
> - 120 inboxes in warming pipeline
> - Proactive order placed for Q2 expansion
> - Your campaigns are fully supported"

### Alert Hierarchy (Operations View)

**🟢 MANAGED (Green):**
- Capacity >70%
- Pipeline healthy (>50% target)
- Proactive orders placed
- Message: "All systems normal. We're ahead of demand."

**🟡 MONITORING (Yellow):**
- Capacity 50-70%
- Small kill spike detected
- Evaluating if order needed
- Message: "Watching trend. May order additional capacity soon."

**🟠 RESPONDING (Orange):**
- Capacity 30-50%
- Active kill spike
- Order placed, waiting for delivery
- Message: "Active response. Order placed [date], warming in progress."

**🔴 CRITICAL (Red):**
- Capacity <30%
- Unexpected massive spike
- Emergency order needed
- Message: "Emergency response. Expedited order in progress."

---

## Updated Data Model

### Operations Events Table

**New Table: `operations_events`**
```sql
CREATE TABLE operations_events (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    workspace_id UUID NOT NULL REFERENCES workspaces(id),
    event_date TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Event classification
    event_type VARCHAR(50) NOT NULL,  -- 'kill_spike', 'order_placed', 'order_fulfilled', 'warming_complete', 'proactive_order'
    severity VARCHAR(20) NOT NULL,    -- 'info', 'warning', 'critical'

    -- Event details
    title TEXT NOT NULL,              -- "Kill spike detected"
    description TEXT,                 -- "50 inboxes lost due to bad lead list"

    -- Response tracking
    response_type VARCHAR(50),        -- 'immediate', 'planned', 'proactive'
    response_action TEXT,             -- "Ordered 2 Hypertide packs"
    response_status VARCHAR(20),      -- 'pending', 'in_progress', 'complete'

    -- Quantitative impact
    inboxes_affected INTEGER,         -- 50 (killed)
    inboxes_ordered INTEGER,          -- 200 (replacement order)
    capacity_impact_pct DECIMAL(5,2), -- -30% (drop)

    -- Related entities
    campaign_id UUID,                 -- If kill spike related to campaign
    domain_id UUID,                   -- If domain-level event
    order_id VARCHAR(100),            -- Hypertide order ID

    -- Visibility
    show_on_dashboard BOOLEAN DEFAULT TRUE,
    show_on_timeline BOOLEAN DEFAULT TRUE,

    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_operations_events_workspace_date
ON operations_events(workspace_id, event_date DESC);

CREATE INDEX idx_operations_events_dashboard
ON operations_events(workspace_id, show_on_dashboard, event_date DESC)
WHERE show_on_dashboard = TRUE;
```

**Example Records:**

```sql
-- Kill spike detected
INSERT INTO operations_events (
    workspace_id, event_date, event_type, severity,
    title, description,
    response_type, response_action, response_status,
    inboxes_affected, capacity_impact_pct,
    campaign_id, show_on_dashboard, show_on_timeline
) VALUES (
    'acme-workspace-id',
    '2026-02-15 09:30:00',
    'kill_spike',
    'critical',
    'Kill spike detected',
    '50 inboxes killed due to bounce rate spike from Campaign X bad lead list',
    'immediate',
    'Quarantined campaign, ordered 2 Hypertide packs',
    'complete',
    50,
    -30.0,
    'campaign-x-id',
    TRUE,
    TRUE
);

-- Order placed (response)
INSERT INTO operations_events (
    workspace_id, event_date, event_type, severity,
    title, description,
    response_type, response_action, response_status,
    inboxes_ordered, order_id,
    show_on_dashboard, show_on_timeline
) VALUES (
    'acme-workspace-id',
    '2026-02-16 08:00:00',
    'order_placed',
    'info',
    'Replacement order placed',
    'Ordered 2 Hypertide packs (200 inboxes) to restore capacity',
    'immediate',
    'Hypertide order HYP-123456',
    'in_progress',
    200,
    'HYP-123456',
    TRUE,
    TRUE
);

-- Proactive order (planned expansion)
INSERT INTO operations_events (
    workspace_id, event_date, event_type, severity,
    title, description,
    response_type, response_action, response_status,
    inboxes_ordered, order_id,
    show_on_dashboard, show_on_timeline
) VALUES (
    'acme-workspace-id',
    '2026-03-05 10:00:00',
    'proactive_order',
    'info',
    'Proactive capacity expansion',
    'Ordered additional capacity for Q2 campaign expansion (planned growth)',
    'proactive',
    'Hypertide order HYP-123789',
    'pending',
    300,
    'HYP-123789',
    TRUE,
    TRUE
);
```

### Capacity Status Calculation

**New Function: `get_operations_status(workspace_id)`**
```sql
CREATE OR REPLACE FUNCTION get_operations_status(p_workspace_id UUID)
RETURNS TABLE (
    status VARCHAR(20),           -- 'managed', 'monitoring', 'responding', 'critical'
    status_message TEXT,          -- Human-readable status
    capacity_pct DECIMAL(5,2),    -- Current capacity percentage
    warming_count INTEGER,        -- Inboxes in warming pipeline
    days_until_ready INTEGER,     -- Days until warming complete
    recent_orders INTEGER,        -- Orders placed in last 14 days
    next_action TEXT              -- What happens next
) AS $$
BEGIN
    RETURN QUERY
    WITH capacity_data AS (
        SELECT
            COUNT(*) FILTER (WHERE inbox_state = 'live') as live_count,
            COUNT(*) FILTER (WHERE created_at > NOW() - INTERVAL '14 days' AND warmup_enabled) as warming_count,
            SUM(daily_limit) FILTER (WHERE inbox_state = 'live') as total_capacity,
            (SELECT COALESCE(SUM(sent), 0) FROM campaign_snapshots WHERE snapshot_date = CURRENT_DATE) as today_sends
        FROM sender_accounts
        WHERE workspace_id = p_workspace_id
    ),
    recent_orders AS (
        SELECT COUNT(*) as order_count
        FROM operations_events
        WHERE workspace_id = p_workspace_id
        AND event_type IN ('order_placed', 'proactive_order')
        AND event_date > NOW() - INTERVAL '14 days'
    ),
    oldest_warming AS (
        SELECT MIN(created_at) as oldest
        FROM sender_accounts
        WHERE workspace_id = p_workspace_id
        AND created_at > NOW() - INTERVAL '14 days'
        AND warmup_enabled = TRUE
    )
    SELECT
        CASE
            WHEN cd.total_capacity > 0 AND cd.today_sends::FLOAT / cd.total_capacity < 0.3 THEN 'critical'
            WHEN cd.total_capacity > 0 AND cd.today_sends::FLOAT / cd.total_capacity < 0.5 THEN 'responding'
            WHEN cd.total_capacity > 0 AND cd.today_sends::FLOAT / cd.total_capacity < 0.7 THEN 'monitoring'
            ELSE 'managed'
        END::VARCHAR(20) as status,

        CASE
            WHEN cd.total_capacity > 0 AND cd.today_sends::FLOAT / cd.total_capacity < 0.3 THEN 'CRITICAL - Emergency order needed'
            WHEN cd.total_capacity > 0 AND cd.today_sends::FLOAT / cd.total_capacity < 0.5 THEN 'RESPONDING - Order placed, warming in progress'
            WHEN cd.total_capacity > 0 AND cd.today_sends::FLOAT / cd.total_capacity < 0.7 THEN 'MONITORING - Watching trend'
            ELSE 'MANAGED - Capacity maintained'
        END::TEXT as status_message,

        CASE
            WHEN cd.total_capacity > 0 THEN (cd.today_sends::FLOAT / cd.total_capacity * 100)
            ELSE 0
        END::DECIMAL(5,2) as capacity_pct,

        cd.warming_count::INTEGER,

        CASE
            WHEN ow.oldest IS NOT NULL THEN 14 - EXTRACT(DAY FROM NOW() - ow.oldest)::INTEGER
            ELSE NULL
        END::INTEGER as days_until_ready,

        ro.order_count::INTEGER as recent_orders,

        CASE
            WHEN ro.order_count > 0 AND cd.warming_count > 0 THEN cd.warming_count::TEXT || ' inboxes ready in ' || (14 - EXTRACT(DAY FROM NOW() - ow.oldest))::TEXT || ' days'
            WHEN ro.order_count > 0 THEN 'Order placed, awaiting delivery'
            WHEN cd.warming_count > 0 THEN cd.warming_count::TEXT || ' inboxes warming'
            ELSE 'Proactive monitoring'
        END::TEXT as next_action

    FROM capacity_data cd
    CROSS JOIN recent_orders ro
    LEFT JOIN oldest_warming ow ON TRUE;
END;
$$ LANGUAGE plpgsql;
```

---

## Updated Frontend Components

### 1. OperationsStatusCard (New)

Replaces "Capacity Gap" KPI card with operations status:

```tsx
interface OperationsStatus {
  status: 'managed' | 'monitoring' | 'responding' | 'critical';
  statusMessage: string;
  capacityPct: number;
  warmingCount: number;
  daysUntilReady: number | null;
  recentOrders: number;
  nextAction: string;
}

export function OperationsStatusCard({ status }: { status: OperationsStatus }) {
  const statusColors = {
    managed: 'bg-green-50 border-green-200 text-green-700',
    monitoring: 'bg-yellow-50 border-yellow-200 text-yellow-700',
    responding: 'bg-orange-50 border-orange-200 text-orange-700',
    critical: 'bg-red-50 border-red-200 text-red-700',
  };

  const statusIcons = {
    managed: '✅',
    monitoring: '🟡',
    responding: '🟠',
    critical: '🔴',
  };

  return (
    <Card className={statusColors[status.status]}>
      <CardHeader>
        <CardTitle className="text-sm font-medium">Operations Status</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="space-y-2">
          <div className="flex items-center gap-2">
            <span className="text-2xl">{statusIcons[status.status]}</span>
            <span className="text-lg font-bold">{status.status.toUpperCase()}</span>
          </div>
          <p className="text-sm">{status.statusMessage}</p>
          {status.warmingCount > 0 && (
            <div className="mt-2 pt-2 border-t">
              <p className="text-xs">
                <strong>{status.warmingCount}</strong> inboxes warming
                {status.daysUntilReady && ` (ready in ${status.daysUntilReady} days)`}
              </p>
            </div>
          )}
          {status.recentOrders > 0 && (
            <div className="text-xs">
              <strong>{status.recentOrders}</strong> order(s) placed in last 14 days
            </div>
          )}
          <p className="text-xs mt-2 italic">{status.nextAction}</p>
        </div>
      </CardContent>
    </Card>
  );
}
```

### 2. OperationsTimeline (New)

Shows chronological response events:

```tsx
interface OperationsEvent {
  id: string;
  eventDate: Date;
  eventType: string;
  severity: string;
  title: string;
  description: string;
  responseAction: string | null;
  responseStatus: string | null;
  inboxesAffected: number | null;
  inboxesOrdered: number | null;
}

export function OperationsTimeline({ events }: { events: OperationsEvent[] }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Operations Response Timeline</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="space-y-4">
          {events.map((event, idx) => (
            <div key={event.id} className="flex gap-3">
              <div className="flex flex-col items-center">
                <div className={cn(
                  'w-3 h-3 rounded-full',
                  event.severity === 'critical' ? 'bg-red-500' :
                  event.severity === 'warning' ? 'bg-orange-500' :
                  'bg-green-500'
                )} />
                {idx < events.length - 1 && (
                  <div className="w-0.5 h-full bg-gray-200 flex-grow" />
                )}
              </div>
              <div className="flex-1 pb-4">
                <div className="flex items-start justify-between">
                  <div>
                    <p className="font-medium">{event.title}</p>
                    <p className="text-sm text-muted-foreground">{event.description}</p>
                    {event.responseAction && (
                      <p className="text-sm text-green-600 mt-1">
                        ✅ Response: {event.responseAction}
                      </p>
                    )}
                  </div>
                  <time className="text-xs text-muted-foreground">
                    {format(event.eventDate, 'MMM d, h:mm a')}
                  </time>
                </div>
              </div>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}
```

### 3. Enhanced Capacity Chart Annotations

Add response annotations to capacity chart:

```tsx
// In SendingCapacityChart component
const annotations = events.map(event => ({
  x: event.eventDate,
  label: event.eventType === 'kill_spike' ? '⚠️ Kill spike' :
         event.eventType === 'order_placed' ? '✅ Order placed' :
         event.eventType === 'warming_complete' ? '🟢 Ready' :
         '📈 Proactive',
  severity: event.severity,
  description: event.description
}));

// Render annotations as vertical lines + tooltips on chart
```

---

## API Endpoints (New/Enhanced)

### GET /api/health/operations-status/{client_id}

Returns current operations status:

```json
{
  "status": "managed",
  "statusMessage": "MANAGED - Capacity maintained",
  "capacityPct": 82.5,
  "warmingCount": 120,
  "daysUntilReady": 9,
  "recentOrders": 2,
  "nextAction": "120 inboxes ready in 9 days"
}
```

### GET /api/health/operations-timeline/{client_id}

Returns operations response timeline (last 90 days):

```json
{
  "events": [
    {
      "id": "event-1",
      "eventDate": "2026-02-15T09:30:00Z",
      "eventType": "kill_spike",
      "severity": "critical",
      "title": "Kill spike detected",
      "description": "50 inboxes killed due to bounce rate spike from Campaign X",
      "responseAction": "Quarantined campaign, ordered 2 Hypertide packs",
      "responseStatus": "complete",
      "inboxesAffected": 50,
      "inboxesOrdered": 200
    },
    {
      "id": "event-2",
      "eventDate": "2026-02-16T08:00:00Z",
      "eventType": "order_placed",
      "severity": "info",
      "title": "Replacement order placed",
      "description": "Ordered 2 Hypertide packs (200 inboxes) to restore capacity",
      "responseAction": "Hypertide order HYP-123456",
      "responseStatus": "in_progress",
      "inboxesOrdered": 200
    }
  ]
}
```

---

## Summary: Key Changes

### Before (Self-Service Framing)
- ❌ "You need to order X inboxes"
- ❌ Gap alerts imply client should act
- ❌ Dashboard shows problems, not solutions

### After (Operations Response Framing)
- ✅ "We detected gap, already ordered replacements"
- ✅ Timeline shows YOUR team's response
- ✅ Dashboard shows **managed operations**, not just health

### Client Perception Shift
- **Before:** "There's a problem, what do I do?"
- **After:** "There was a problem, they already fixed it"

---

**Document Version:** 1.0
**Created:** 2026-02-23
**Context:** Internal operations view, not client self-service
**Key Insight:** Dashboard is transparency tool showing "we're proactively managing your infrastructure"
