---
title: Client Dashboard Implementation Plan
created: 2026-02-23
updated: 2026-05-18
project: Charm Email OS
repository: /home/claw/work/charm-email-os
status: superseded-in-parts
tags: [implementation-plan, dashboard, client-facing]
---

> **2026-05-18 NOTE — Partially superseded.** The internal operator Infrastructure dashboard (under [charm-email-os/app/workspaces/[id]/infrastructure](../../charm-email-os/app/workspaces/[id]/infrastructure)) has shipped and supersedes the chart sections of this plan. Specific corrections:
>
> - The "emails_sent stored as daily total" framing in this doc is **wrong** — the value is cumulative-to-date. Real semantics: [docs/architecture/daily-volume-semantics.md](../architecture/daily-volume-semantics.md).
> - The "capacity_utilization_pct" column shown here is mathematically broken under the actual semantics. Don't build on it.
> - The "daily_capacity_available = SUM(daily_limit) for all live inboxes" description is incomplete: in reality it's filtered to `status='Connected'` AND includes incubating inboxes whose quota mostly goes to warmup. The operator dashboard splits this into "production capacity" vs "total daily quota" — see the semantics doc.
>
> Sections of this plan still useful as reference: backfill script design (worked correctly), the high-level chart shape, the dashboard layout sketches. The implementation specifics for data model + column semantics are obsolete.

# Client Dashboard Implementation Plan

## Project Overview

**Goal:** Build external-facing client dashboard showing infrastructure health with sending volume trends, capacity tracking, and incubating pipeline visibility.

**Repository:** `/home/claw/work/charm-email-os`

**Timeline:** 2 weeks (80 hours engineering time)

**Status:** Database is 100% ready. Historical data backfilled. Frontend components needed.

---

## Table of Contents

1. [Database Changes](#1-database-changes)
2. [Backend API Changes](#2-backend-api-changes)
3. [Frontend Components](#3-frontend-components)
4. [Background Workers](#4-background-workers)
5. [Testing](#5-testing)
6. [Deployment](#6-deployment)

---

## 1. Database Changes

### 1.1 New Migration: Daily Volume Snapshots

**File:** `/home/claw/work/charm-email-os/migrations/040_daily_volume_snapshots.sql`

**Purpose:** Track historical sending volume per day for time-series chart

**Schema:**
```sql
-- Migration 040: Daily Volume Snapshots
-- Created: 2026-02-23
-- Purpose: Track daily sending volume for client dashboard capacity chart

CREATE TABLE daily_volume_snapshots (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    workspace_id UUID NOT NULL REFERENCES workspaces(id),
    snapshot_date DATE NOT NULL,

    -- Volume metrics (aggregated from EmailBison campaigns that day)
    emails_sent INTEGER NOT NULL DEFAULT 0,
    emails_delivered INTEGER NOT NULL DEFAULT 0,
    emails_bounced INTEGER NOT NULL DEFAULT 0,
    emails_complained INTEGER NOT NULL DEFAULT 0,

    -- Capacity metrics (snapshot as of end of day)
    live_inboxes INTEGER NOT NULL DEFAULT 0,
    incubating_inboxes INTEGER NOT NULL DEFAULT 0,
    dead_inboxes INTEGER NOT NULL DEFAULT 0,
    daily_capacity_available INTEGER NOT NULL DEFAULT 0,  -- SUM(daily_limit WHERE live)

    -- Derived metrics
    capacity_utilization_pct DECIMAL(5,2),  -- (emails_sent / daily_capacity_available) * 100

    -- Metadata
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(workspace_id, snapshot_date)
);

-- Indexes for fast querying
CREATE INDEX idx_daily_volume_workspace_date
ON daily_volume_snapshots(workspace_id, snapshot_date DESC);

CREATE INDEX idx_daily_volume_date
ON daily_volume_snapshots(snapshot_date DESC);

-- Comments for documentation
COMMENT ON TABLE daily_volume_snapshots IS
    'Daily aggregate of sending volume and capacity metrics for client dashboard time-series charts';

COMMENT ON COLUMN daily_volume_snapshots.emails_sent IS
    'Total emails sent across all campaigns in this workspace on this date';

COMMENT ON COLUMN daily_volume_snapshots.daily_capacity_available IS
    'Total daily sending capacity (SUM of daily_limit for all live inboxes) as of end of day';

COMMENT ON COLUMN daily_volume_snapshots.capacity_utilization_pct IS
    'Percentage of available capacity used: (emails_sent / daily_capacity_available) * 100';
```

**Naming Convention Notes:**
- Table name: `daily_volume_snapshots` (matches existing `sender_warmup_snapshots`, `inbox_health_snapshots` pattern)
- Column naming: `snake_case` (consistent with existing schema)
- Timestamp columns: Always `TIMESTAMPTZ` (timezone-aware, consistent with `sender_accounts.created_at`)
- Foreign keys: Always reference by `workspace_id` (consistent with existing patterns)

**Migration Script:**
```bash
# Run migration
cd /home/claw/work/charm-email-os
psql $DATABASE_URL -f migrations/040_daily_volume_snapshots.sql

# Verify
psql $DATABASE_URL -c "\d daily_volume_snapshots"
psql $DATABASE_URL -c "SELECT COUNT(*) FROM daily_volume_snapshots;"
```

---

### 1.2 Modify Existing: Add Hook to campaign_burn_events

**File:** `/home/claw/work/charm-email-os/sync_modules/kill_processor.py`

**Purpose:** Auto-populate `campaign_burn_events` when inboxes are killed (currently only backfilled)

**Location:** Find the `_mark_inbox_dead()` function (around lines 150-250)

**Change:**
```python
# File: /home/claw/work/charm-email-os/sync_modules/kill_processor.py
# Function: _mark_inbox_dead() or execute_kill()

async def _mark_inbox_dead(
    inbox_id: str,
    trigger_type: str,
    trigger_value: float,
    trigger_threshold: float,
    workspace_id: str
):
    """
    Mark an inbox as dead and record the kill event.

    Args:
        inbox_id: UUID of sender_account
        trigger_type: e.g., 'spam_complaint', 'hard_blocked_24h'
        trigger_value: Actual value that triggered kill (e.g., 5 bounces)
        trigger_threshold: Threshold that was exceeded (e.g., 2 bounces)
        workspace_id: UUID of workspace
    """

    # EXISTING CODE: Mark inbox dead in sender_accounts
    await db.execute("""
        UPDATE sender_accounts
        SET
            inbox_state = 'dead',
            killed_at = NOW(),
            kill_trigger = $1,
            kill_reason = $2,
            updated_at = NOW()
        WHERE id = $3
    """,
    trigger_type,
    f"{trigger_value} exceeded threshold {trigger_threshold}",
    inbox_id
    )

    # NEW CODE: Record burn event with campaign attribution
    # Get the campaign this inbox was assigned to (if any)
    campaign_info = await db.fetch_one("""
        SELECT
            ci.campaign_id,
            ec.name as campaign_name,
            sa.domain_id,
            sa.email_address as inbox_email,
            d.domain_name
        FROM sender_accounts sa
        LEFT JOIN campaign_inboxes ci ON ci.inbox_id = sa.id
        LEFT JOIN emailbison_campaigns ec ON ci.campaign_id = ec.id
        LEFT JOIN domains d ON sa.domain_id = d.id
        WHERE sa.id = $1
        ORDER BY ci.created_at DESC
        LIMIT 1
    """, inbox_id)

    if campaign_info:
        # Record burn event
        await db.execute("""
            INSERT INTO campaign_burn_events (
                id,
                workspace_id,
                campaign_id,
                inbox_id,
                domain_id,
                kill_trigger_type,
                trigger_value,
                trigger_threshold,
                campaign_name,
                inbox_email,
                domain_name,
                burned_at,
                created_at
            ) VALUES (
                uuid_generate_v4(),
                $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, NOW(), NOW()
            )
            ON CONFLICT (campaign_id, inbox_id) DO NOTHING
        """,
        workspace_id,
        campaign_info['campaign_id'],
        inbox_id,
        campaign_info['domain_id'],
        trigger_type,
        trigger_value,
        trigger_threshold,
        campaign_info['campaign_name'],
        campaign_info['inbox_email'],
        campaign_info['domain_name']
        )

        logger.info(
            f"Recorded burn event: inbox={inbox_id}, "
            f"campaign={campaign_info['campaign_name']}, "
            f"trigger={trigger_type}"
        )
```

**Testing Hook:**
```python
# Test in Python shell or test file
async def test_burn_event_recording():
    # Trigger a kill
    await _mark_inbox_dead(
        inbox_id="test-inbox-uuid",
        trigger_type="spam_complaint",
        trigger_value=1.0,
        trigger_threshold=1.0,
        workspace_id="test-workspace-uuid"
    )

    # Verify burn event was recorded
    burn_event = await db.fetch_one("""
        SELECT * FROM campaign_burn_events
        WHERE inbox_id = 'test-inbox-uuid'
    """)

    assert burn_event is not None
    assert burn_event['kill_trigger_type'] == 'spam_complaint'
    print("✅ Burn event recorded successfully")
```

---

## 2. Backend API Changes

### 2.1 New API Endpoint: Daily Volume History

**File:** `/home/claw/work/charm-email-os/api/routes/health.py`

**Endpoint:** `GET /api/health/daily-volume/{client_id}`

**Purpose:** Return 90 days of sending volume data for capacity chart

**Add to existing routes/health.py:**
```python
# File: /home/claw/work/charm-email-os/api/routes/health.py
# Add after existing health endpoints (around line 800+)

from datetime import date, timedelta
from typing import List
from api.models.health import DailyVolumeSnapshot  # New model (see 2.2)

@router.get(
    "/daily-volume/{client_id}",
    response_model=DailyVolumeHistoryResponse,
    summary="Get daily volume history for client dashboard",
    tags=["health"]
)
async def get_daily_volume_history(
    client_id: str,
    days: int = Query(90, ge=1, le=365, description="Number of days of history"),
    db: Database = Depends(get_db)
):
    """
    Get daily sending volume and capacity history for client dashboard chart.

    Returns 90 days (default) of:
    - Emails sent per day
    - Available capacity per day
    - Incubating inbox count per day
    - Capacity utilization percentage

    Used by: Client dashboard "Sending Capacity Over Time" chart
    """

    # Get workspace_id from client_id
    workspace = await db.fetch_one(
        "SELECT id FROM workspaces WHERE client_id = $1",
        client_id
    )
    if not workspace:
        raise HTTPException(status_code=404, detail="Client not found")

    workspace_id = workspace['id']
    start_date = date.today() - timedelta(days=days)

    # Query daily snapshots
    snapshots = await db.fetch_all("""
        SELECT
            snapshot_date,
            emails_sent,
            emails_delivered,
            emails_bounced,
            daily_capacity_available,
            live_inboxes,
            incubating_inboxes,
            dead_inboxes,
            capacity_utilization_pct
        FROM daily_volume_snapshots
        WHERE workspace_id = $1
          AND snapshot_date >= $2
        ORDER BY snapshot_date ASC
    """, workspace_id, start_date)

    # Get kill events for annotations
    kill_events = await db.fetch_all("""
        SELECT
            DATE(burned_at) as kill_date,
            COUNT(*) as inboxes_killed,
            STRING_AGG(DISTINCT kill_trigger_type, ', ') as kill_reasons
        FROM campaign_burn_events
        WHERE workspace_id = $1
          AND burned_at >= $2
        GROUP BY DATE(burned_at)
        ORDER BY kill_date ASC
    """, workspace_id, start_date)

    # Build response
    return DailyVolumeHistoryResponse(
        client_id=client_id,
        workspace_id=str(workspace_id),
        start_date=start_date,
        end_date=date.today(),
        snapshots=[
            DailyVolumeSnapshot(
                date=row['snapshot_date'],
                emails_sent=row['emails_sent'],
                emails_delivered=row['emails_delivered'],
                emails_bounced=row['emails_bounced'],
                daily_capacity_available=row['daily_capacity_available'],
                live_inboxes=row['live_inboxes'],
                incubating_inboxes=row['incubating_inboxes'],
                dead_inboxes=row['dead_inboxes'],
                capacity_utilization_pct=row['capacity_utilization_pct']
            )
            for row in snapshots
        ],
        kill_events=[
            KillEventAnnotation(
                date=row['kill_date'],
                inboxes_killed=row['inboxes_killed'],
                kill_reasons=row['kill_reasons']
            )
            for row in kill_events
        ]
    )
```

**API Response Example:**
```json
{
  "client_id": "acme-corp",
  "workspace_id": "b9abd34a-f16a-4b92-bda0-5af10f8c44bd",
  "start_date": "2025-11-25",
  "end_date": "2026-02-23",
  "snapshots": [
    {
      "date": "2025-11-25",
      "emails_sent": 45000,
      "emails_delivered": 43500,
      "emails_bounced": 1500,
      "daily_capacity_available": 80000,
      "live_inboxes": 645,
      "incubating_inboxes": 80,
      "dead_inboxes": 100,
      "capacity_utilization_pct": 56.25
    },
    {
      "date": "2026-02-15",
      "emails_sent": 65000,
      "emails_delivered": 62000,
      "emails_bounced": 3000,
      "daily_capacity_available": 75000,
      "live_inboxes": 595,
      "incubating_inboxes": 120,
      "dead_inboxes": 150,
      "capacity_utilization_pct": 86.67
    }
  ],
  "kill_events": [
    {
      "date": "2026-02-15",
      "inboxes_killed": 50,
      "kill_reasons": "spam_complaint, hard_blocked_24h"
    }
  ]
}
```

---

### 2.2 New API Models

**File:** `/home/claw/work/charm-email-os/api/models/health.py`

**Purpose:** Pydantic models for API response validation

**Add to existing models/health.py:**
```python
# File: /home/claw/work/charm-email-os/api/models/health.py
# Add after existing health models (around line 300+)

from datetime import date
from typing import List, Optional
from pydantic import BaseModel, Field
from decimal import Decimal

class DailyVolumeSnapshot(BaseModel):
    """Single day's volume and capacity snapshot."""

    date: date = Field(description="Snapshot date (YYYY-MM-DD)")
    emails_sent: int = Field(description="Total emails sent this day")
    emails_delivered: int = Field(description="Emails successfully delivered")
    emails_bounced: int = Field(description="Emails bounced")
    daily_capacity_available: int = Field(description="Total daily capacity (sum of inbox limits)")
    live_inboxes: int = Field(description="Count of live inboxes as of end of day")
    incubating_inboxes: int = Field(description="Count of incubating inboxes")
    dead_inboxes: int = Field(description="Count of dead inboxes")
    capacity_utilization_pct: Optional[Decimal] = Field(
        None,
        description="Percentage of capacity used (0-100)"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "date": "2026-02-23",
                "emails_sent": 65000,
                "emails_delivered": 62000,
                "emails_bounced": 3000,
                "daily_capacity_available": 80000,
                "live_inboxes": 645,
                "incubating_inboxes": 120,
                "dead_inboxes": 100,
                "capacity_utilization_pct": 81.25
            }
        }


class KillEventAnnotation(BaseModel):
    """Kill event for chart annotation."""

    date: date = Field(description="Date of kill event")
    inboxes_killed: int = Field(description="Number of inboxes killed this day")
    kill_reasons: str = Field(description="Comma-separated list of kill trigger types")

    class Config:
        json_schema_extra = {
            "example": {
                "date": "2026-02-15",
                "inboxes_killed": 50,
                "kill_reasons": "spam_complaint, hard_blocked_24h"
            }
        }


class DailyVolumeHistoryResponse(BaseModel):
    """Response containing daily volume history for dashboard chart."""

    client_id: str = Field(description="Client identifier")
    workspace_id: str = Field(description="Workspace UUID")
    start_date: date = Field(description="First date in range")
    end_date: date = Field(description="Last date in range (today)")
    snapshots: List[DailyVolumeSnapshot] = Field(
        description="Daily snapshots ordered by date ascending"
    )
    kill_events: List[KillEventAnnotation] = Field(
        description="Kill events for chart annotations"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "client_id": "acme-corp",
                "workspace_id": "b9abd34a-f16a-4b92-bda0-5af10f8c44bd",
                "start_date": "2025-11-25",
                "end_date": "2026-02-23",
                "snapshots": [
                    {
                        "date": "2025-11-25",
                        "emails_sent": 45000,
                        "daily_capacity_available": 80000,
                        "live_inboxes": 645,
                        "incubating_inboxes": 80,
                        "capacity_utilization_pct": 56.25
                    }
                ],
                "kill_events": [
                    {
                        "date": "2026-02-15",
                        "inboxes_killed": 50,
                        "kill_reasons": "spam_complaint, hard_blocked_24h"
                    }
                ]
            }
        }
```

**Model Naming Convention:**
- Model names: `PascalCase` (e.g., `DailyVolumeSnapshot`)
- Field names: `snake_case` (e.g., `emails_sent`)
- Response models: Suffix with `Response` (e.g., `DailyVolumeHistoryResponse`)

---

## 3. Frontend Components

### 3.1 New Component: SendingCapacityChart

**File:** `/home/claw/work/charm-email-os/charm-email-os/components/health/SendingCapacityChart.tsx`

**Purpose:** Main time-series chart showing volume, capacity, and incubating pipeline

**Component:**
```tsx
'use client';

import { useMemo } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Line, LineChart, CartesianGrid, XAxis, YAxis, Tooltip, Legend, ReferenceLine, ResponsiveContainer } from 'recharts';
import { format, parseISO } from 'date-fns';
import { TrendingUp, TrendingDown, Minus } from 'lucide-react';
import { cn } from '@/lib/utils';

interface DailySnapshot {
  date: string;  // ISO date string
  emails_sent: number;
  daily_capacity_available: number;
  incubating_inboxes: number;
  capacity_utilization_pct: number;
}

interface KillEvent {
  date: string;  // ISO date string
  inboxes_killed: number;
  kill_reasons: string;
}

interface SendingCapacityChartProps {
  snapshots: DailySnapshot[];
  killEvents: KillEvent[];
  className?: string;
}

export function SendingCapacityChart({
  snapshots,
  killEvents,
  className
}: SendingCapacityChartProps) {

  // Format data for chart
  const chartData = useMemo(() => {
    return snapshots.map(snapshot => {
      // Find kill events on this date
      const killEvent = killEvents.find(k => k.date === snapshot.date);

      return {
        date: snapshot.date,
        dateFormatted: format(parseISO(snapshot.date), 'MMM d'),
        emailsSent: snapshot.emails_sent,
        capacity: snapshot.daily_capacity_available,
        incubating: snapshot.incubating_inboxes * 100, // Scale for visibility
        utilizationPct: snapshot.capacity_utilization_pct,

        // Kill event annotation
        hasKillEvent: !!killEvent,
        killCount: killEvent?.inboxes_killed || 0,
        killReasons: killEvent?.kill_reasons || ''
      };
    });
  }, [snapshots, killEvents]);

  // Calculate trend
  const trend = useMemo(() => {
    if (chartData.length < 2) return 'stable';

    const recent = chartData.slice(-7);  // Last 7 days
    const avgRecent = recent.reduce((sum, d) => sum + d.emailsSent, 0) / recent.length;

    const previous = chartData.slice(-14, -7);  // Previous 7 days
    const avgPrevious = previous.reduce((sum, d) => sum + d.emailsSent, 0) / previous.length;

    const change = ((avgRecent - avgPrevious) / avgPrevious) * 100;

    if (change > 5) return 'up';
    if (change < -5) return 'down';
    return 'stable';
  }, [chartData]);

  // Calculate insights
  const insights = useMemo(() => {
    const latest = chartData[chartData.length - 1];
    const utilizationPct = latest?.utilizationPct || 0;
    const incubatingCount = latest?.incubating / 100 || 0;

    const messages: string[] = [];

    if (utilizationPct > 80) {
      messages.push('🟢 Your infrastructure is healthy and fully supports current campaigns');
    } else if (utilizationPct > 60) {
      messages.push('📈 Your sending volume is growing - capacity is well-managed');
    } else {
      messages.push('✅ Plenty of capacity headroom available');
    }

    if (incubatingCount > 0) {
      const daysUntilReady = 14 - 5; // Placeholder - calculate from warmup_started_at
      messages.push(`🔄 Pipeline: ${incubatingCount} inboxes warming (ready in ~${daysUntilReady} days)`);
    }

    const recentKills = killEvents.filter(k => {
      const daysAgo = (Date.now() - new Date(k.date).getTime()) / (1000 * 60 * 60 * 24);
      return daysAgo <= 7;
    });

    if (recentKills.length > 0) {
      const totalKilled = recentKills.reduce((sum, k) => sum + k.inboxes_killed, 0);
      messages.push(`✅ Recent maintenance: ${totalKilled} inboxes retired and replaced`);
    }

    return messages;
  }, [chartData, killEvents]);

  return (
    <Card className={cn('', className)}>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle className="text-lg font-semibold">
            Your Sending Capacity (90 days)
          </CardTitle>
          <div className="flex items-center gap-2 text-sm">
            {trend === 'up' && (
              <div className="flex items-center gap-1 text-green-600">
                <TrendingUp className="h-4 w-4" />
                <span>Growing</span>
              </div>
            )}
            {trend === 'down' && (
              <div className="flex items-center gap-1 text-orange-600">
                <TrendingDown className="h-4 w-4" />
                <span>Declining</span>
              </div>
            )}
            {trend === 'stable' && (
              <div className="flex items-center gap-1 text-gray-600">
                <Minus className="h-4 w-4" />
                <span>Stable</span>
              </div>
            )}
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Chart */}
        <div className="h-[300px]">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
              <XAxis
                dataKey="dateFormatted"
                stroke="#6b7280"
                fontSize={12}
                tickLine={false}
              />
              <YAxis
                stroke="#6b7280"
                fontSize={12}
                tickLine={false}
                tickFormatter={(value) => `${(value / 1000).toFixed(0)}K`}
              />
              <Tooltip
                content={({ active, payload }) => {
                  if (!active || !payload || !payload.length) return null;

                  const data = payload[0].payload;

                  return (
                    <div className="bg-white border rounded-lg shadow-lg p-3 space-y-1">
                      <p className="font-semibold">{format(parseISO(data.date), 'MMM d, yyyy')}</p>
                      <p className="text-sm">
                        <span className="text-blue-600 font-medium">Sent:</span> {data.emailsSent.toLocaleString()} emails
                      </p>
                      <p className="text-sm">
                        <span className="text-gray-600">Capacity:</span> {data.capacity.toLocaleString()} emails/day
                      </p>
                      <p className="text-sm">
                        <span className="text-gray-600">Utilization:</span> {data.utilizationPct.toFixed(1)}%
                      </p>
                      {data.hasKillEvent && (
                        <div className="pt-2 border-t mt-2">
                          <p className="text-xs text-orange-600 font-medium">
                            ⚠️ {data.killCount} inboxes retired
                          </p>
                          <p className="text-xs text-gray-500">{data.killReasons}</p>
                        </div>
                      )}
                    </div>
                  );
                }}
              />
              <Legend
                wrapperStyle={{ fontSize: '12px', paddingTop: '10px' }}
              />

              {/* 100% Capacity Line */}
              <Line
                type="monotone"
                dataKey="capacity"
                stroke="#9ca3af"
                strokeWidth={2}
                strokeDasharray="5 5"
                dot={false}
                name="Available Capacity"
              />

              {/* Actual Volume Line */}
              <Line
                type="monotone"
                dataKey="emailsSent"
                stroke="#3b82f6"
                strokeWidth={3}
                dot={{ fill: '#3b82f6', r: 3 }}
                name="Daily Sends"
              />

              {/* Incubating Pipeline (scaled) */}
              <Line
                type="monotone"
                dataKey="incubating"
                stroke="#f59e0b"
                strokeWidth={2}
                strokeDasharray="3 3"
                dot={false}
                name="Warming Pipeline (×100)"
              />

              {/* Kill event markers */}
              {killEvents.map((event, idx) => (
                <ReferenceLine
                  key={idx}
                  x={format(parseISO(event.date), 'MMM d')}
                  stroke="#ef4444"
                  strokeWidth={1}
                  strokeDasharray="3 3"
                />
              ))}
            </LineChart>
          </ResponsiveContainer>
        </div>

        {/* Insights */}
        <div className="space-y-2 pt-2 border-t">
          <h4 className="text-sm font-semibold text-gray-700">📊 INSIGHTS</h4>
          {insights.map((insight, idx) => (
            <p key={idx} className="text-sm text-gray-600">{insight}</p>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}
```

**Component Naming Convention:**
- Component name: `PascalCase` + suffix (e.g., `SendingCapacityChart`)
- Props interface: `{ComponentName}Props`
- File name: Same as component name (e.g., `SendingCapacityChart.tsx`)

---

### 3.2 Update Existing: Health Page Integration

**File:** `/home/claw/work/charm-email-os/charm-email-os/app/clients/[clientId]/health/page.tsx`

**Change:** Add new SendingCapacityChart component to existing dashboard

**Modification:**
```tsx
// File: /home/claw/work/charm-email-os/charm-email-os/app/clients/[clientId]/health/page.tsx
// Add to existing imports (around line 10-20)

import { SendingCapacityChart } from '@/components/health/SendingCapacityChart';

// In the component (around line 100+), add data fetching:

const [dailyVolumeData, setDailyVolumeData] = useState(null);

useEffect(() => {
  const fetchDailyVolume = async () => {
    try {
      const response = await fetch(`/api/health/daily-volume/${clientId}?days=90`);
      const data = await response.json();
      setDailyVolumeData(data);
    } catch (error) {
      console.error('Failed to fetch daily volume:', error);
    }
  };

  fetchDailyVolume();
}, [clientId]);

// In the JSX (around line 200+), add to Dashboard tab BEFORE existing charts:

<div className="space-y-6">
  {/* NEW: Sending Capacity Chart */}
  {dailyVolumeData && (
    <SendingCapacityChart
      snapshots={dailyVolumeData.snapshots}
      killEvents={dailyVolumeData.kill_events}
    />
  )}

  {/* EXISTING: Capacity Planning */}
  <CapacityPlanning ... />

  {/* EXISTING: Inventory Segmentation */}
  <InventorySegmentationChart ... />

  {/* ... rest of existing components ... */}
</div>
```

---

## 4. Background Workers

### 4.1 New Worker: Daily Snapshot Worker

**File:** `/home/claw/work/charm-email-os/sync_modules/daily_snapshot_worker.py`

**Purpose:** Run nightly at 00:05 UTC to snapshot yesterday's volume and capacity

**Worker:**
```python
"""
Daily Volume Snapshot Worker

Runs nightly at 00:05 UTC to create daily snapshots of sending volume
and capacity metrics for client dashboard charts.

Schedule: Cron expression "5 0 * * *" (00:05 UTC daily)
"""

import asyncio
import logging
from datetime import date, timedelta
from typing import Dict, List
from databases import Database

from api.core.database import get_db
from api.models.workspace import Workspace

logger = logging.getLogger(__name__)

class DailySnapshotWorker:
    """Worker to snapshot daily volume and capacity metrics."""

    def __init__(self, db: Database):
        self.db = db

    async def snapshot_workspace(
        self,
        workspace_id: str,
        snapshot_date: date
    ) -> Dict:
        """
        Create daily snapshot for a single workspace.

        Args:
            workspace_id: UUID of workspace to snapshot
            snapshot_date: Date to snapshot (usually yesterday)

        Returns:
            Dict with snapshot metrics
        """
        logger.info(f"Snapshotting workspace {workspace_id} for {snapshot_date}")

        # Query capacity metrics as of snapshot_date
        capacity = await self.db.fetch_one("""
            SELECT
                COUNT(*) FILTER (WHERE inbox_state = 'live') as live_inboxes,
                COUNT(*) FILTER (WHERE inventory_lifecycle_status = 'incubating') as incubating_inboxes,
                COUNT(*) FILTER (WHERE inbox_state = 'dead') as dead_inboxes,
                COALESCE(SUM(daily_limit) FILTER (WHERE inbox_state = 'live'), 0) as daily_capacity
            FROM sender_accounts
            WHERE workspace_id = $1
        """, workspace_id)

        # Query volume sent on snapshot_date
        # Option 1: If you have campaign_snapshots table with daily data:
        volume = await self.db.fetch_one("""
            SELECT
                COALESCE(SUM(sent), 0) as emails_sent,
                COALESCE(SUM(delivered), 0) as emails_delivered,
                COALESCE(SUM(hard_bounces + soft_bounces), 0) as emails_bounced,
                COALESCE(SUM(spam_complaints), 0) as emails_complained
            FROM campaign_snapshots cs
            JOIN emailbison_campaigns ec ON cs.campaign_id = ec.id
            WHERE ec.workspace_id = $1
              AND DATE(cs.snapshot_date) = $2
        """, workspace_id, snapshot_date)

        # Option 2: If no campaign_snapshots, calculate delta from all-time totals:
        # NOTE: This requires storing yesterday's emails_sent_all_time
        # See "Alternative Approach" section below

        # Calculate utilization
        capacity_available = capacity['daily_capacity'] or 1
        utilization_pct = (volume['emails_sent'] / capacity_available) * 100 if capacity_available > 0 else 0

        # Insert or update snapshot
        await self.db.execute("""
            INSERT INTO daily_volume_snapshots (
                id,
                workspace_id,
                snapshot_date,
                emails_sent,
                emails_delivered,
                emails_bounced,
                emails_complained,
                live_inboxes,
                incubating_inboxes,
                dead_inboxes,
                daily_capacity_available,
                capacity_utilization_pct,
                created_at,
                updated_at
            ) VALUES (
                uuid_generate_v4(),
                $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, NOW(), NOW()
            )
            ON CONFLICT (workspace_id, snapshot_date)
            DO UPDATE SET
                emails_sent = EXCLUDED.emails_sent,
                emails_delivered = EXCLUDED.emails_delivered,
                emails_bounced = EXCLUDED.emails_bounced,
                emails_complained = EXCLUDED.emails_complained,
                live_inboxes = EXCLUDED.live_inboxes,
                incubating_inboxes = EXCLUDED.incubating_inboxes,
                dead_inboxes = EXCLUDED.dead_inboxes,
                daily_capacity_available = EXCLUDED.daily_capacity_available,
                capacity_utilization_pct = EXCLUDED.capacity_utilization_pct,
                updated_at = NOW()
        """,
        workspace_id,
        snapshot_date,
        volume['emails_sent'],
        volume['emails_delivered'],
        volume['emails_bounced'],
        volume['emails_complained'],
        capacity['live_inboxes'],
        capacity['incubating_inboxes'],
        capacity['dead_inboxes'],
        capacity['daily_capacity'],
        round(utilization_pct, 2)
        )

        logger.info(
            f"✅ Snapshot complete: {workspace_id} | "
            f"Date: {snapshot_date} | "
            f"Sent: {volume['emails_sent']} | "
            f"Capacity: {capacity['daily_capacity']} | "
            f"Utilization: {utilization_pct:.1f}%"
        )

        return {
            'workspace_id': workspace_id,
            'snapshot_date': snapshot_date,
            'emails_sent': volume['emails_sent'],
            'capacity': capacity['daily_capacity'],
            'utilization_pct': utilization_pct
        }

    async def run_all_workspaces(self) -> List[Dict]:
        """
        Run daily snapshot for all active workspaces.

        Returns:
            List of snapshot results
        """
        yesterday = date.today() - timedelta(days=1)

        logger.info(f"Starting daily snapshot for all workspaces (date: {yesterday})")

        # Get all active workspaces
        workspaces = await self.db.fetch_all("""
            SELECT id, name FROM workspaces WHERE deleted_at IS NULL
        """)

        results = []
        errors = []

        for workspace in workspaces:
            try:
                result = await self.snapshot_workspace(
                    workspace['id'],
                    yesterday
                )
                results.append(result)
            except Exception as e:
                logger.error(f"Failed to snapshot workspace {workspace['id']}: {e}")
                errors.append({
                    'workspace_id': workspace['id'],
                    'error': str(e)
                })

        logger.info(
            f"Daily snapshot complete: "
            f"{len(results)} succeeded, {len(errors)} failed"
        )

        return results


async def main():
    """Entry point for cron job."""
    db = await get_db()
    worker = DailySnapshotWorker(db)

    try:
        results = await worker.run_all_workspaces()
        logger.info(f"Daily snapshot job finished: {len(results)} workspaces processed")
    except Exception as e:
        logger.exception(f"Daily snapshot job failed: {e}")
        raise
    finally:
        await db.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
```

**Cron Schedule:**
```bash
# Add to crontab or systemd timer
# File: /etc/cron.d/charm-daily-snapshot

5 0 * * * cd /home/claw/work/charm-email-os && /usr/bin/python3 sync_modules/daily_snapshot_worker.py >> /var/log/charm/daily-snapshot.log 2>&1
```

**Alternative Approach (if no campaign_snapshots table):**

If you don't have a `campaign_snapshots` table with daily send counts, you'll need to calculate daily volume from all-time totals:

```python
# Add column to sender_accounts:
# ALTER TABLE sender_accounts ADD COLUMN emails_sent_yesterday INTEGER DEFAULT 0;

# In daily_snapshot_worker.py, calculate delta:
async def calculate_daily_sends(workspace_id: str, snapshot_date: date):
    """Calculate emails sent yesterday from all-time totals."""

    # Get today's all-time total
    today_total = await self.db.fetch_one("""
        SELECT COALESCE(SUM(emails_sent_all_time), 0) as total
        FROM sender_accounts
        WHERE workspace_id = $1
    """, workspace_id)

    # Get yesterday's all-time total (stored in emails_sent_yesterday)
    yesterday_total = await self.db.fetch_one("""
        SELECT COALESCE(SUM(emails_sent_yesterday), 0) as total
        FROM sender_accounts
        WHERE workspace_id = $1
    """, workspace_id)

    # Calculate delta
    emails_sent_today = today_total['total'] - yesterday_total['total']

    # Update emails_sent_yesterday for next run
    await self.db.execute("""
        UPDATE sender_accounts
        SET emails_sent_yesterday = emails_sent_all_time
        WHERE workspace_id = $1
    """, workspace_id)

    return max(0, emails_sent_today)  # Prevent negative if sync issues
```

---

### 4.2 Worker Naming Convention

- Worker file name: `{purpose}_worker.py` (e.g., `daily_snapshot_worker.py`)
- Worker class: `{Purpose}Worker` (e.g., `DailySnapshotWorker`)
- Main function: Always `async def main()`
- Log messages: Start with emoji for easy parsing (✅ = success, ⚠️ = warning, ❌ = error)

---

## 5. Testing

### 5.1 Database Migration Testing

```bash
# Test migration on local dev database
cd /home/claw/work/charm-email-os

# Run migration
psql $DATABASE_URL -f migrations/040_daily_volume_snapshots.sql

# Verify table created
psql $DATABASE_URL -c "\d daily_volume_snapshots"

# Expected output:
#   Column                     | Type           | Nullable
# -----------------------------+----------------+----------
#  id                          | uuid           | not null
#  workspace_id                | uuid           | not null
#  snapshot_date               | date           | not null
#  emails_sent                 | integer        | not null
#  daily_capacity_available    | integer        | not null
#  ...

# Verify indexes
psql $DATABASE_URL -c "\di daily_volume_*"

# Expected output:
#  idx_daily_volume_workspace_date
#  idx_daily_volume_date
```

### 5.2 API Endpoint Testing

```bash
# Test daily volume endpoint (after running snapshot worker once)
curl http://localhost:8000/api/health/daily-volume/acme-corp?days=7

# Expected response:
# {
#   "client_id": "acme-corp",
#   "workspace_id": "...",
#   "start_date": "2026-02-16",
#   "end_date": "2026-02-23",
#   "snapshots": [
#     {
#       "date": "2026-02-16",
#       "emails_sent": 45000,
#       "daily_capacity_available": 80000,
#       ...
#     }
#   ],
#   "kill_events": [...]
# }

# Test with invalid client_id
curl http://localhost:8000/api/health/daily-volume/invalid-client

# Expected response:
# {
#   "detail": "Client not found"
# }
```

### 5.3 Background Worker Testing

```bash
# Run worker manually for testing
cd /home/claw/work/charm-email-os
python3 sync_modules/daily_snapshot_worker.py

# Check logs
tail -f /var/log/charm/daily-snapshot.log

# Expected output:
# 2026-02-23 00:05:01 INFO Starting daily snapshot for all workspaces (date: 2026-02-22)
# 2026-02-23 00:05:02 INFO Snapshotting workspace b9abd34a-... for 2026-02-22
# 2026-02-23 00:05:03 INFO ✅ Snapshot complete: ... | Sent: 65000 | Capacity: 80000
# 2026-02-23 00:05:10 INFO Daily snapshot complete: 5 succeeded, 0 failed

# Verify snapshot was created
psql $DATABASE_URL -c "SELECT * FROM daily_volume_snapshots WHERE snapshot_date = '2026-02-22';"
```

### 5.4 Frontend Component Testing

```bash
# Start dev server
cd /home/claw/work/charm-email-os/charm-email-os
npm run dev

# Navigate to health page
# http://localhost:3000/clients/acme-corp/health

# Verify:
# 1. SendingCapacityChart renders at top of Dashboard tab
# 2. Chart shows 90 days of data
# 3. Blue line (actual volume) visible
# 4. Gray dashed line (capacity) visible
# 5. Orange dashed line (incubating) visible
# 6. Red vertical lines on kill event dates
# 7. Insights section shows messages
# 8. Hover tooltip shows details

# Check browser console for errors
# Expected: No errors
```

### 5.5 Integration Testing

**Test Scenario:** Full end-to-end flow

1. **Baseline:** Query current snapshot count
   ```sql
   SELECT COUNT(*) FROM daily_volume_snapshots;
   -- Result: 0 (if fresh install)
   ```

2. **Run Worker:** Execute daily snapshot
   ```bash
   python3 sync_modules/daily_snapshot_worker.py
   ```

3. **Verify Snapshot:** Check snapshot was created
   ```sql
   SELECT COUNT(*) FROM daily_volume_snapshots;
   -- Result: 5 (if 5 workspaces)

   SELECT snapshot_date, emails_sent, daily_capacity_available
   FROM daily_volume_snapshots
   ORDER BY snapshot_date DESC
   LIMIT 5;
   ```

4. **Test API:** Fetch via API endpoint
   ```bash
   curl http://localhost:8000/api/health/daily-volume/acme-corp?days=1
   ```

5. **Test Frontend:** View in browser
   - Navigate to http://localhost:3000/clients/acme-corp/health
   - Verify chart renders
   - Verify data matches API response

6. **Test Kill Event Annotation:**
   - Manually trigger a kill (or use existing kill from campaign_burn_events)
   - Verify red vertical line appears on chart on correct date
   - Hover over kill date, verify tooltip shows kill count and reasons

---

## 6. Deployment

### 6.1 Deployment Checklist

**Pre-Deployment:**
- [ ] Run all tests locally (section 5)
- [ ] Verify migration runs cleanly
- [ ] Verify API endpoints work
- [ ] Verify frontend renders correctly
- [ ] Review code with team
- [ ] Update API documentation (if using Swagger/OpenAPI)

**Deployment Steps:**

1. **Database Migration (Production):**
   ```bash
   # Connect to production database
   psql $PRODUCTION_DATABASE_URL -f migrations/040_daily_volume_snapshots.sql

   # Verify
   psql $PRODUCTION_DATABASE_URL -c "\d daily_volume_snapshots"
   ```

2. **Deploy Backend Changes:**
   ```bash
   # Deploy kill_processor.py changes
   git add sync_modules/kill_processor.py
   git commit -m "feat: auto-populate campaign_burn_events on kill"

   # Deploy API changes
   git add api/routes/health.py api/models/health.py
   git commit -m "feat: add daily-volume endpoint for client dashboard"

   # Deploy worker
   git add sync_modules/daily_snapshot_worker.py
   git commit -m "feat: add daily snapshot worker for volume history"

   # Push and deploy
   git push origin main
   # (trigger deployment pipeline)
   ```

3. **Set Up Cron Job (Production):**
   ```bash
   # Add to crontab
   sudo crontab -e

   # Add line:
   5 0 * * * cd /var/www/charm-email-os && /usr/bin/python3 sync_modules/daily_snapshot_worker.py >> /var/log/charm/daily-snapshot.log 2>&1

   # OR create systemd timer (preferred)
   sudo nano /etc/systemd/system/charm-daily-snapshot.service
   sudo nano /etc/systemd/system/charm-daily-snapshot.timer
   sudo systemctl enable charm-daily-snapshot.timer
   sudo systemctl start charm-daily-snapshot.timer
   ```

4. **Deploy Frontend Changes:**
   ```bash
   # Deploy SendingCapacityChart component
   git add charm-email-os/components/health/SendingCapacityChart.tsx
   git commit -m "feat: add SendingCapacityChart for client dashboard"

   # Deploy health page integration
   git add charm-email-os/app/clients/[clientId]/health/page.tsx
   git commit -m "feat: integrate SendingCapacityChart in health dashboard"

   # Push and deploy
   git push origin main
   # (trigger Vercel/Netlify deployment)
   ```

5. **Backfill Historical Data:**
   ```bash
   # ✅ COMPLETED (2026-02-23): 54,716 emails backfilled
   # Script: scripts/backfill_daily_volume.py
   # Data coverage: Nov 25, 2025 - Feb 22, 2026 (90 days)

   # To extend historical data or re-run:
   python scripts/backfill_daily_volume.py --days 90

   # For specific date range:
   python scripts/backfill_daily_volume.py --start-date 2025-08-01 --end-date 2025-11-24
   ```

   **Backfill Results:**
   | Workspace | Emails | Coverage |
   |-----------|--------|----------|
   | Spout | 29,692 | 39% |
   | SPUI | 8,510 | 54% |
   | EventPanda | 6,277 | 73% |
   | Charm | 6,115 | 34% |
   | Others | 4,122 | varies |

   **Note**: Coverage % is relative to all-time totals. Lower % means most activity predates the 90-day window.

6. **Monitor First Run:**
   ```bash
   # Watch cron job logs
   tail -f /var/log/charm/daily-snapshot.log

   # Check snapshot count increases daily
   psql $PRODUCTION_DATABASE_URL -c "SELECT COUNT(*) FROM daily_volume_snapshots;"

   # Verify API endpoint works
   curl https://app.charmemail.io/api/health/daily-volume/acme-corp?days=7
   ```

**Post-Deployment:**
- [ ] Monitor error logs for 48 hours
- [ ] Verify worker runs nightly at 00:05 UTC
- [ ] Check client dashboard renders correctly in production
- [ ] Verify chart shows data (may take 1 day for first snapshot)
- [ ] Monitor API performance (should be <500ms)

---

### 6.2 Rollback Plan

**If Issues Arise:**

1. **Database Rollback:**
   ```sql
   -- Drop table (safe if no critical data yet)
   DROP TABLE IF EXISTS daily_volume_snapshots CASCADE;
   ```

2. **Backend Rollback:**
   ```bash
   git revert <commit-hash>
   git push origin main
   # Redeploy
   ```

3. **Frontend Rollback:**
   ```bash
   git revert <commit-hash>
   git push origin main
   # Redeploy
   ```

4. **Disable Cron:**
   ```bash
   sudo crontab -e
   # Comment out daily snapshot line

   # OR for systemd:
   sudo systemctl stop charm-daily-snapshot.timer
   sudo systemctl disable charm-daily-snapshot.timer
   ```

---

## 7. Naming Convention Reference

### 7.1 Database Naming

| Type | Convention | Example |
|------|-----------|---------|
| Table name | `snake_case` plural | `daily_volume_snapshots` |
| Column name | `snake_case` | `emails_sent`, `capacity_utilization_pct` |
| Foreign key | `{referenced_table}_id` | `workspace_id`, `campaign_id` |
| Index | `idx_{table}_{columns}` | `idx_daily_volume_workspace_date` |
| Constraint | `{table}_{column}_fkey` | `daily_volume_snapshots_workspace_id_fkey` |
| Timestamp columns | Always `TIMESTAMPTZ` | `created_at TIMESTAMPTZ` |

### 7.2 Backend Naming

| Type | Convention | Example |
|------|-----------|---------|
| File name | `snake_case.py` | `daily_snapshot_worker.py` |
| Class name | `PascalCase` | `DailySnapshotWorker` |
| Function name | `snake_case` | `snapshot_workspace()`, `run_all_workspaces()` |
| Model name | `PascalCase` | `DailyVolumeSnapshot` |
| Model field | `snake_case` | `emails_sent`, `daily_capacity_available` |
| Endpoint path | `kebab-case` | `/api/health/daily-volume/{client_id}` |

### 7.3 Frontend Naming

| Type | Convention | Example |
|------|-----------|---------|
| Component file | `PascalCase.tsx` | `SendingCapacityChart.tsx` |
| Component name | `PascalCase` | `SendingCapacityChart` |
| Props interface | `{Component}Props` | `SendingCapacityChartProps` |
| Hook name | `use{Name}` | `useDailyVolumeData` |
| Variable name | `camelCase` | `dailyVolumeData`, `chartData` |
| Constant | `UPPER_SNAKE_CASE` | `DEFAULT_DAYS`, `CHART_COLORS` |

---

## 8. File Checklist

**New Files to Create:**
- [ ] `/migrations/040_daily_volume_snapshots.sql`
- [ ] `/sync_modules/daily_snapshot_worker.py`
- [ ] `/charm-email-os/components/health/SendingCapacityChart.tsx`

**Files to Modify:**
- [ ] `/sync_modules/kill_processor.py` (add campaign_burn_events INSERT)
- [ ] `/api/routes/health.py` (add daily-volume endpoint)
- [ ] `/api/models/health.py` (add DailyVolumeSnapshot, DailyVolumeHistoryResponse)
- [ ] `/charm-email-os/app/clients/[clientId]/health/page.tsx` (integrate SendingCapacityChart)

**Configuration Files:**
- [ ] `/etc/cron.d/charm-daily-snapshot` (cron job)
- [ ] OR `/etc/systemd/system/charm-daily-snapshot.{service,timer}` (systemd timer)

**Total Files:** 3 new + 4 modified = **7 files**

---

## 9. Success Criteria

**Definition of Done:**

✅ Migration 040 deployed to production without errors
✅ `daily_volume_snapshots` table created with correct schema
✅ Daily snapshot worker runs nightly at 00:05 UTC
✅ API endpoint `/api/health/daily-volume/{client_id}` returns data
✅ SendingCapacityChart component renders on client health page
✅ Chart shows 90 days of historical data
✅ Chart displays actual volume, capacity, incubating pipeline, and kill annotations
✅ Kill events auto-populate `campaign_burn_events` when inboxes die
✅ No performance degradation (API response <500ms)
✅ No errors in logs for 48 hours post-deployment

---

## 10. Timeline

| Phase | Duration | Tasks |
|-------|----------|-------|
| **Week 1: Database & Backend** | 5 days | |
| Day 1 | 4 hours | Create migration 040, test locally |
| Day 2 | 4 hours | Write daily snapshot worker, test locally |
| Day 3 | 4 hours | Add kill_processor hook, test kill flow |
| Day 4 | 4 hours | Create API endpoint, add models, test API |
| Day 5 | 4 hours | Integration testing, fix bugs |
| **Week 2: Frontend & Deployment** | 5 days | |
| Day 6 | 6 hours | Build SendingCapacityChart component |
| Day 7 | 4 hours | Integrate chart in health page, test UI |
| Day 8 | 4 hours | Deploy to staging, QA testing |
| Day 9 | 4 hours | Deploy to production, set up cron |
| Day 10 | 2 hours | Monitor, documentation, retrospective |

**Total:** 40 hours (1 engineer, 2 weeks at 4 hours/day)

---

## 11. Support & Troubleshooting

**Common Issues:**

**Issue:** Snapshot worker fails with "No volume data found"
- **Cause:** No campaign_snapshots data or EmailBison API returned no data
- **Fix:** Check if campaign_snapshots table exists. If not, use "Alternative Approach" (delta from all-time totals)

**Issue:** Chart shows no data for recent days
- **Cause:** Worker hasn't run yet or failed to create snapshots
- **Fix:** Run worker manually: `python3 sync_modules/daily_snapshot_worker.py`

**Issue:** API endpoint returns 404
- **Cause:** Client not found or workspace_id mapping incorrect
- **Fix:** Verify client_id exists: `SELECT * FROM workspaces WHERE client_id = 'acme-corp'`

**Issue:** Chart renders but is blank
- **Cause:** No snapshots in date range or data format mismatch
- **Fix:** Check API response: `curl /api/health/daily-volume/{client_id}?days=7`. Verify snapshots array is populated.

**Issue:** Kill events don't show on chart
- **Cause:** campaign_burn_events table empty or kill_processor hook not deployed
- **Fix:** Verify burn events exist: `SELECT COUNT(*) FROM campaign_burn_events`. Deploy kill_processor.py changes.

---

## 12. Documentation

**Update These Docs After Implementation:**

- [ ] `/docs/api/health-endpoints.md` - Add daily-volume endpoint documentation
- [ ] `/docs/database/schema.md` - Add daily_volume_snapshots table documentation
- [ ] `/docs/workers/daily-snapshot.md` - Document daily snapshot worker
- [ ] `/docs/dashboard/client-dashboard.md` - Update client dashboard documentation
- [ ] `/README.md` - Add mention of new client dashboard features

---

**Document Version:** 1.0
**Created:** 2026-02-23
**Project:** Charm Email OS
**Repository:** `/home/claw/work/charm-email-os`
**Status:** Ready for Implementation
**Estimated Effort:** 40 hours (2 weeks)
**Files Changed:** 7 files (3 new, 4 modified)
