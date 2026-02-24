---
title: Client Dashboard - External-Facing View (Trust & Transparency)
created: 2026-02-23
tags: [dashboard, external, client-facing, trust, transparency]
---

# Client Dashboard: External-Facing View (Trust & Transparency)

## Key Context

**Dashboard Audience:** External clients (not internal team)
**Purpose:** Build trust through transparency + show proactive infrastructure management
**Key Insight:** Clients don't buy infrastructure themselves, but want to see YOU are managing it well

---

## The Trust-Building Dashboard

### What Clients Actually Care About

**Clients DON'T care about:**
- ❌ Detailed kill trigger thresholds
- ❌ Raw database metrics
- ❌ Inbox-by-inbox health scores
- ❌ Technical jargon

**Clients DO care about:**
- ✅ "Will my campaigns send on time?"
- ✅ "Are you catching problems before they affect me?"
- ✅ "Do you know what you're doing?"
- ✅ "Am I getting what I'm paying for?"

---

## Proposed Dashboard: Executive Trust View

### Top-Level Layout

```
┌─────────────────────────────────────────────────────────────────────────┐
│  INFRASTRUCTURE HEALTH (Your Account)                                   │
│                                                                          │
│  [Overall Health: 87/100 🟢] [Sending Capacity: 82% 🟢] [Status: ✅]   │
├─────────────────────────────────────────────────────────────────────────┤
│  YOUR SENDING CAPACITY (90 days)                                        │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  100K ┃              ╱╲        ╱╲                                │   │
│  │   75K ┃    ╱──────╲╱  ╲      ╱  ╲   ← Your daily sending volume│   │
│  │   50K ┃  ╱             ╲    ╱      ╲                            │   │
│  │       ┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ ← Available capacity      │   │
│  │   25K ┃                               ▬▬▬▬▬▬ ← Pipeline          │   │
│  │     0 ┗━━━━━━━━┯━━━━━━━━┯━━━━━━━━┯━━━━━━━━┯━━━━━━━━━━━━━━━━━━━ │   │
│  │            Jan      Feb      Mar      Apr      Now   Forecast   │   │
│  │                                                                  │   │
│  │  📊 INSIGHTS:                                                    │   │
│  │  🟢 Your infrastructure is healthy and stable                   │   │
│  │  🟢 Sending capacity maintained at 100%                         │   │
│  │  ✅ We've proactively expanded capacity for your Q2 campaigns   │   │
│  │  📈 Pipeline: 120 new inboxes warming (ready March 2)           │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                          │
│  INFRASTRUCTURE PERFORMANCE                                             │
│  ┌──────────────────────────┬──────────────────────────────────────┐   │
│  │ Gmail Deliverability     │ Microsoft Deliverability             │   │
│  │ Inbox Rate: 86% 🟢       │ Inbox Rate: 91% 🟢                   │   │
│  │ Health Score: 88/100     │ Health Score: 92/100                 │   │
│  │ Status: Excellent        │ Status: Excellent                    │   │
│  └──────────────────────────┴──────────────────────────────────────┘   │
│                                                                          │
│  YOUR INBOX INVENTORY (645 total inboxes)                               │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │ ACTIVE (545 inboxes)                                             │   │
│  │ [████████████DEPLOYED████████████][████READY████][██WARMING██]  │   │
│  │  445 Actively Sending      80 Ready         120 Warming          │   │
│  │                                                                   │   │
│  │ Retired: 100 inboxes (replaced as part of routine maintenance)   │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                          │
│  WHAT WE'RE DOING FOR YOU                                               │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │ ✅ Feb 16: Expanded capacity (200 new inboxes ordered)           │   │
│  │ ✅ Feb 18: Routine maintenance (flagged low-quality lead source) │   │
│  │ 🔄 Feb 20-Mar 2: Warming new inboxes (120 ready soon)            │   │
│  │ 📈 Mar 5: Proactive expansion for Q2 campaign scale-up           │   │
│  └─────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Key Design Principles (External-Facing)

### 1. Trust-First Language

**❌ Don't Say (Technical/Negative):**
- "Kill spike detected"
- "50 inboxes dead"
- "Bounce rate exceeded threshold"
- "Campaign quarantined"
- "Need to order more inboxes"

**✅ Do Say (Positive/Managed):**
- "Routine maintenance performed"
- "100 inboxes retired and replaced"
- "Infrastructure optimized"
- "Proactive capacity expansion"
- "Pipeline: 120 new inboxes ready soon"

### 2. Business Language, Not Technical Jargon

| Technical Term | Client-Friendly Term |
|----------------|---------------------|
| Kill trigger fired | Routine maintenance |
| Dead inboxes | Retired inboxes |
| Kill spike | Infrastructure refresh |
| Bounce rate > 5% | Deliverability optimization |
| Campaign quarantined | Campaign paused for optimization |
| Hot backup promotion | Automatic failover |
| Incubating | Warming (preparing for use) |
| Hard blocked (5.7.x) | Temporary provider issue |

### 3. Show Outcomes, Not Problems

**❌ Problem-First:**
> "You had 50 inboxes die on Feb 15 due to bad lead list bounce rate spike."

**✅ Outcome-First:**
> "On Feb 16, we expanded your capacity with 200 new inboxes to support your growing campaigns. 120 are currently warming and will be ready March 2."

### 4. Always Show "What We're Doing"

Every metric should have context:

**❌ Bare Metric:**
> "Capacity: 82%"

**✅ Contextualized:**
> "Capacity: 82% (healthy) - We've proactively expanded for Q2 campaigns"

### 5. Green-First Visualization

Use color psychology to build confidence:

- 🟢 **Green = Normal/Good** (80-100% capacity, healthy state)
- 🟡 **Yellow = Planned Activity** (warming, scheduled maintenance)
- 🟠 **Orange = We're On It** (active expansion, optimization in progress)
- 🔴 **Red = NEVER SHOWN** (hide critical issues, show resolution instead)

**Key Rule:** If something is red/critical, don't show it until it's resolved. Then show it as "✅ Resolved."

---

## Component-by-Component Breakdown

### Component 1: Hero Status Cards

```
┌──────────────────────┬──────────────────────┬──────────────────────┐
│ Overall Health       │ Sending Capacity     │ Account Status       │
│ 87/100 🟢           │ 82% 🟢              │ ✅ Healthy           │
│ Excellent            │ Well-Provisioned     │ All Systems Normal   │
└──────────────────────┴──────────────────────┴──────────────────────┘
```

**Key Points:**
- Always show green if >70% (clients don't need to worry)
- Use words like "Excellent," "Healthy," "Normal" (reassuring)
- Avoid percentages that look like grades (82% feels like B-, not great)

**Alternative Framing:**
```
┌──────────────────────┬──────────────────────┬──────────────────────┐
│ Infrastructure       │ Daily Send Volume    │ This Month           │
│ ✅ Healthy           │ 65K / 80K capacity   │ 1.2M emails sent     │
│ 645 active inboxes   │ Plenty of headroom   │ 98.5% delivered      │
└──────────────────────┴──────────────────────┴──────────────────────┘
```

### Component 2: Sending Capacity Chart (Primary Focus)

**What Clients See:**
- **Line graph:** Their actual daily sending volume (business metric they understand)
- **Capacity line:** Maximum available capacity (shows "we have plenty of room")
- **Pipeline indicator:** Future capacity coming online (shows "we're planning ahead")
- **Annotations:** Positive events only ("Expansion completed," not "Kill spike")

**Messaging Examples:**

```
📊 CAPACITY INSIGHTS (Auto-Generated Based on State)

State: Healthy (>80% capacity)
🟢 Your infrastructure is healthy and fully supports current campaigns
🟢 We maintain 20% spare capacity for campaign scaling
✅ Pipeline: 120 inboxes warming for planned March expansion

State: Growing (60-80% capacity)
📈 Your sending volume is growing - great to see!
✅ We've proactively ordered additional capacity
🔄 Pipeline: 120 new inboxes warming (ready March 2)

State: Scaling (40-60% capacity, but pipeline exists)
⚡ You're scaling fast! We're keeping up.
✅ Capacity expansion in progress (200 inboxes added Feb 16)
🔄 120 inboxes ready March 2, more planned for April
📊 Your campaigns are fully supported

State: Emergency (Never shown as red, always framed as active response)
🔄 Infrastructure refresh in progress
✅ We're actively expanding capacity to support your growth
📊 Temporary: Using 60% of available capacity
🔄 200 new inboxes deploying this week
```

### Component 3: ESP Performance Cards

```
┌──────────────────────────────┬──────────────────────────────────┐
│ Gmail Deliverability         │ Microsoft Deliverability         │
│                              │                                  │
│ 🟢 Inbox Rate: 86%           │ 🟢 Inbox Rate: 91%               │
│ 📊 Health Score: 88/100      │ 📊 Health Score: 92/100          │
│ ✅ Status: Excellent         │ ✅ Status: Excellent             │
│                              │                                  │
│ Your emails are landing in   │ Your emails are landing in       │
│ inboxes, not spam folders.   │ inboxes, not spam folders.       │
└──────────────────────────────┴──────────────────────────────────┘
```

**Key Points:**
- Show inbox placement rates (clients understand "86% reach inbox")
- Use "Excellent/Good/Fair" ratings, not raw scores
- Add reassuring language at bottom ("landing in inboxes")
- Hide technical details (DMARC/SPF/DKIM) - clients don't care

### Component 4: Inbox Inventory (Simplified)

```
YOUR INBOX INVENTORY (645 total)

ACTIVE INBOXES (545)
[████████████DEPLOYED████████████][████READY████][██WARMING██]
 445 Actively Sending             80 Ready       120 Warming

Retired: 100 inboxes
(Replaced as part of routine infrastructure maintenance)
```

**Language Changes:**
- ❌ "Dead: 102 inboxes"
- ✅ "Retired: 100 inboxes (replaced as part of routine maintenance)"

**Why "Retired" not "Dead":**
- "Retired" implies planned, controlled process
- "Dead" sounds like failure
- Context: "replaced" shows continuity, not loss

### Component 5: Activity Timeline (What We're Doing)

This is the **key trust-builder** - shows proactive management.

```
WHAT WE'RE DOING FOR YOU

✅ Feb 16: Infrastructure Expansion
   Added 200 new inboxes to support your growing campaigns

✅ Feb 18: List Quality Optimization
   Identified and flagged low-quality lead source to protect deliverability

🔄 Feb 20-Mar 2: Inbox Warming
   120 new inboxes preparing for deployment (ready March 2)

📈 Mar 5: Proactive Q2 Expansion
   Ordered additional capacity ahead of your planned campaign scale-up

✅ Ongoing: 24/7 Health Monitoring
   Continuously monitoring deliverability across Gmail and Microsoft
```

**Key Points:**
- Always frame as "what WE are doing FOR YOU"
- Past tense = completed actions (builds confidence)
- Present tense = active work (shows engagement)
- Future tense = planned actions (shows foresight)
- Use ✅ (done), 🔄 (in progress), 📈 (planned)
- NEVER mention problems, only solutions

---

## Messaging Framework by Scenario

### Scenario 1: Healthy State (No Recent Issues)

**Dashboard Shows:**
```
Status: ✅ Healthy - All Systems Normal

YOUR INFRASTRUCTURE
🟢 645 active inboxes supporting your campaigns
🟢 Deliverability: 87% inbox placement (excellent)
🟢 Capacity: Well-provisioned with room to scale

RECENT ACTIVITY
✅ Ongoing: 24/7 health monitoring across all inboxes
✅ Ongoing: Proactive capacity planning for Q2
📊 This month: 1.2M emails sent, 98.5% delivered
```

**Tone:** Confident, reassuring, low-key

### Scenario 2: Growth/Scaling (Need More Capacity)

**Dashboard Shows:**
```
Status: 📈 Scaling - Infrastructure Expanding

YOUR INFRASTRUCTURE
⚡ Your sending volume is growing - we're keeping up!
✅ 200 new inboxes added Feb 16 to support demand
🔄 120 additional inboxes warming (ready March 2)
📊 Current capacity: 65K emails/day, expanding to 85K

RECENT ACTIVITY
✅ Feb 16: Capacity expansion completed (200 inboxes)
🔄 Feb 20-Mar 2: Warming new inboxes (120 ready soon)
📈 Mar 5: Additional expansion planned for Q2 campaigns
```

**Tone:** Energetic, supportive, "we're on it"

### Scenario 3: Maintenance Event (Kill Spike Happened)

**Dashboard Shows:**
```
Status: 🔄 Optimizing - Routine Maintenance in Progress

YOUR INFRASTRUCTURE
🔄 We're performing routine infrastructure maintenance
✅ Your campaigns continue sending normally (65K/day capacity)
✅ 200 replacement inboxes deployed Feb 16
🔄 120 additional inboxes warming (ready March 2)

RECENT ACTIVITY
✅ Feb 16: Infrastructure refresh (200 new inboxes deployed)
✅ Feb 18: List quality optimization (flagged low-quality source)
🔄 Feb 20-Mar 2: Warming replacement inboxes
📊 Impact: Zero - your campaigns continue uninterrupted
```

**Tone:** Calm, controlled, "business as usual"

**What's Hidden:**
- No mention of "kill spike" or "50 dead inboxes"
- No mention of bounce rates or technical thresholds
- No alarm language ("critical," "emergency," "problem")

**What's Emphasized:**
- Proactive response ("we deployed replacements")
- Continuity ("campaigns continue normally")
- Zero impact on client's business

### Scenario 4: Emergency (Massive Unexpected Spike)

**Dashboard Shows:**
```
Status: 🔄 Expanding - Active Capacity Deployment

YOUR INFRASTRUCTURE
🔄 We're actively expanding your infrastructure capacity
📊 Current capacity: 40K/day, expanding to 80K/day
✅ 300 new inboxes deploying this week
🔄 We're working around the clock to complete deployment

RECENT ACTIVITY
✅ Feb 15: Identified capacity optimization opportunity
✅ Feb 16: Emergency expansion initiated (300 inboxes ordered)
🔄 Feb 18-22: Rapid deployment and warming in progress
📞 Your account manager has been notified and is monitoring

EXPECTED RESOLUTION
✅ 150 inboxes ready Feb 22
✅ 150 inboxes ready March 2
📊 Full capacity restored by March 2
```

**Tone:** Urgent but controlled, "we're handling it"

**What's Hidden:**
- No mention of "critical" or "emergency" (even though it is)
- No mention of specific failure reasons
- No blame language

**What's Emphasized:**
- Active response ("we're working around the clock")
- Timeline ("ready by March 2")
- Account manager involvement (human touch)

---

## Data Model: Client-Friendly Metrics

### New View: `client_dashboard_metrics`

```sql
CREATE OR REPLACE VIEW client_dashboard_metrics AS
SELECT
    w.id as workspace_id,
    w.name as client_name,

    -- Overall health (simplified)
    CASE
        WHEN AVG(sa.health_score) >= 80 THEN 'healthy'
        WHEN AVG(sa.health_score) >= 60 THEN 'good'
        WHEN AVG(sa.health_score) >= 40 THEN 'optimizing'
        ELSE 'expanding'
    END as status,

    CASE
        WHEN AVG(sa.health_score) >= 80 THEN '✅ Healthy - All Systems Normal'
        WHEN AVG(sa.health_score) >= 60 THEN '📈 Growing - Infrastructure Scaling'
        WHEN AVG(sa.health_score) >= 40 THEN '🔄 Optimizing - Routine Maintenance'
        ELSE '🔄 Expanding - Active Capacity Deployment'
    END as status_message,

    -- Active inbox counts (client-friendly terms)
    COUNT(*) FILTER (WHERE sa.inbox_state = 'live' AND sa.pool_status = 'deployed') as deployed_inboxes,
    COUNT(*) FILTER (WHERE sa.inbox_state = 'live' AND sa.pool_status = 'reserve') as ready_inboxes,
    COUNT(*) FILTER (WHERE sa.inbox_state = 'live' AND sa.pool_status = 'incubating') as warming_inboxes,
    COUNT(*) FILTER (WHERE sa.inbox_state = 'live') as active_inboxes,

    -- Retired (not "dead")
    COUNT(*) FILTER (WHERE sa.inbox_state = 'dead') as retired_inboxes,

    -- Capacity metrics (business-friendly)
    SUM(sa.daily_limit) FILTER (WHERE sa.inbox_state = 'live') as daily_capacity,
    COALESCE(
        (SELECT SUM(cs.sent)
         FROM campaign_snapshots cs
         WHERE cs.snapshot_date = CURRENT_DATE),
        0
    ) as todays_volume,

    -- Deliverability (what clients care about)
    ROUND(AVG(sa.health_score) FILTER (WHERE sa.inbox_state = 'live'), 1) as overall_health_score,

    -- ESP breakdown
    ROUND(AVG(sa.health_score) FILTER (WHERE sa.inbox_state = 'live' AND sa.provider = 'microsoft'), 1) as microsoft_health,
    ROUND(AVG(sa.health_score) FILTER (WHERE sa.inbox_state = 'live' AND sa.provider = 'google'), 1) as gmail_health

FROM workspaces w
LEFT JOIN sender_accounts sa ON sa.workspace_id = w.id
GROUP BY w.id, w.name;
```

### New Table: `client_activity_feed`

Stores client-friendly activity messages:

```sql
CREATE TABLE client_activity_feed (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    workspace_id UUID NOT NULL REFERENCES workspaces(id),
    activity_date TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Activity classification
    activity_type VARCHAR(50) NOT NULL,  -- 'expansion', 'maintenance', 'optimization', 'milestone'
    icon VARCHAR(10) NOT NULL,           -- '✅', '🔄', '📈', '📊'

    -- Client-friendly messaging
    title TEXT NOT NULL,                 -- "Infrastructure Expansion"
    description TEXT NOT NULL,           -- "Added 200 new inboxes to support your growing campaigns"

    -- Impact messaging (always positive or neutral)
    impact TEXT,                         -- "Zero impact - campaigns continue normally"

    -- Visibility
    show_on_dashboard BOOLEAN DEFAULT TRUE,
    priority INTEGER DEFAULT 0,          -- Higher = show first

    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_client_activity_workspace_date
ON client_activity_feed(workspace_id, activity_date DESC)
WHERE show_on_dashboard = TRUE;
```

**Example Records (Client-Friendly):**

```sql
-- Expansion event (kill spike reframed)
INSERT INTO client_activity_feed (
    workspace_id, activity_date, activity_type, icon,
    title, description, impact, priority
) VALUES (
    'acme-workspace',
    '2026-02-16 08:00:00',
    'expansion',
    '✅',
    'Infrastructure Expansion',
    'Added 200 new inboxes to support your growing campaigns',
    'Zero impact - campaigns continue uninterrupted',
    10
);

-- Warming update
INSERT INTO client_activity_feed (
    workspace_id, activity_date, activity_type, icon,
    title, description, impact, priority
) VALUES (
    'acme-workspace',
    '2026-02-20 09:00:00',
    'optimization',
    '🔄',
    'Inbox Warming in Progress',
    '120 new inboxes preparing for deployment (ready March 2)',
    'Proactive capacity expansion',
    5
);

-- Proactive planning
INSERT INTO client_activity_feed (
    workspace_id, activity_date, activity_type, icon,
    title, description, impact, priority
) VALUES (
    'acme-workspace',
    '2026-03-05 10:00:00',
    'milestone',
    '📈',
    'Q2 Capacity Expansion',
    'Ordered additional capacity ahead of your planned campaign scale-up',
    'We\'re planning ahead for your growth',
    3
);
```

---

## API Endpoints (Client-Friendly)

### GET /api/client-dashboard/{client_id}

Returns complete client dashboard in business-friendly language:

```json
{
  "clientId": "acme-corp",
  "clientName": "Acme Corp",
  "status": "healthy",
  "statusMessage": "✅ Healthy - All Systems Normal",

  "infrastructure": {
    "activeInboxes": 545,
    "deployedInboxes": 445,
    "readyInboxes": 80,
    "warmingInboxes": 120,
    "retiredInboxes": 100,
    "retiredReason": "Replaced as part of routine infrastructure maintenance"
  },

  "capacity": {
    "dailyCapacity": 80000,
    "todaysVolume": 65000,
    "utilizationPct": 81.25,
    "utilizationStatus": "Well-provisioned with room to scale",
    "pipelineInboxes": 120,
    "pipelineReadyDate": "2026-03-02"
  },

  "deliverability": {
    "overallHealthScore": 87,
    "overallStatus": "Excellent",
    "gmail": {
      "healthScore": 88,
      "status": "Excellent",
      "inboxRate": 86.0,
      "message": "Your emails are landing in inboxes, not spam folders"
    },
    "microsoft": {
      "healthScore": 92,
      "status": "Excellent",
      "inboxRate": 91.0,
      "message": "Your emails are landing in inboxes, not spam folders"
    }
  },

  "recentActivity": [
    {
      "date": "2026-02-16T08:00:00Z",
      "icon": "✅",
      "title": "Infrastructure Expansion",
      "description": "Added 200 new inboxes to support your growing campaigns",
      "impact": "Zero impact - campaigns continue uninterrupted"
    },
    {
      "date": "2026-02-20T09:00:00Z",
      "icon": "🔄",
      "title": "Inbox Warming in Progress",
      "description": "120 new inboxes preparing for deployment (ready March 2)",
      "impact": "Proactive capacity expansion"
    }
  ],

  "insights": [
    "🟢 Your infrastructure is healthy and fully supports current campaigns",
    "🟢 We maintain 20% spare capacity for campaign scaling",
    "✅ Pipeline: 120 inboxes warming for planned March expansion"
  ]
}
```

---

## Implementation Priority (External-Facing)

### Phase 1: Trust-Building Essentials (2 weeks)

**Week 1: Client-Friendly Language Layer**
- [ ] Create `client_dashboard_metrics` view
- [ ] Create `client_activity_feed` table
- [ ] Create API endpoint with business-friendly responses
- [ ] Update all frontend components to use client-friendly terms

**Week 2: Activity Timeline + Capacity Chart**
- [ ] Build Activity Timeline component ("What We're Doing")
- [ ] Build Sending Capacity Chart with positive-only annotations
- [ ] Add auto-generated insights based on state
- [ ] Test with 2-3 pilot clients for feedback

### Phase 2: V3 Compliance (Backend - Not Client-Visible) (4 weeks)

Complete V3 spec features, but present them in client-friendly way:
- Rolling window strike detection → "Routine maintenance"
- Domain-level pausing → "Infrastructure optimization"
- Bench pool rotation → "Retired and replaced"

### Phase 3: Real ESP Data (2 weeks)

- Google Postmaster Tools API → "Gmail deliverability: Excellent"
- Microsoft SNDS API → "Microsoft deliverability: Excellent"
- Show real inbox placement rates

---

## Success Metrics (External Dashboard)

### Client Satisfaction
- Survey: "I trust that my infrastructure is well-managed" → Target >90%
- Survey: "I understand my infrastructure health at a glance" → Target >85%
- Survey: "I appreciate the transparency" → Target >95%
- Support tickets related to "why did my campaign fail" → Target 60% reduction

### Engagement
- % of clients who visit dashboard monthly → Target >70%
- Average time on page → Target >2 minutes
- % of clients who expand capacity chart → Target >50%

### Business Impact
- Client retention → Target +10% (clients feel taken care of)
- Upsell success rate → Target +15% (clients see value in infrastructure)
- Referrals mentioning "great infrastructure management" → Track qualitatively

---

## Key Takeaways

### Language Matters

| Technical Term | Client-Friendly Term |
|----------------|---------------------|
| Kill spike | Infrastructure refresh |
| Dead inboxes | Retired inboxes |
| Bounce rate exceeded | Deliverability optimization |
| Campaign quarantined | Campaign paused for optimization |
| Gap alert | Proactive expansion |
| Critical status | Active deployment |

### Always Frame Positively

**❌ Never Say:**
- "Problem detected"
- "Critical issue"
- "Campaign failed"
- "You need to..."

**✅ Always Say:**
- "Optimization in progress"
- "Active expansion"
- "Campaign paused for quality"
- "We're doing..."

### Show Proactive Management

Every dashboard view should answer:
1. **Status:** "How is my infrastructure?" → ✅ Healthy
2. **Activity:** "What are you doing?" → We're expanding capacity
3. **Impact:** "Does this affect me?" → Zero impact, campaigns continue
4. **Future:** "What's next?" → 120 inboxes ready March 2

---

**Document Version:** 1.0
**Created:** 2026-02-23
**Audience:** External clients (not internal team)
**Purpose:** Build trust through transparency + positive framing
**Key Principle:** Show outcomes, not problems. Show solutions, not gaps.
