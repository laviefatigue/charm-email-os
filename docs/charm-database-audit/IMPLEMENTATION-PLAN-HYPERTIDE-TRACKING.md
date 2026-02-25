---
title: Implementation Plan - HyperTide Capacity Tracking & Integrity Fixes
created: 2026-02-23
tags: [implementation, hypertide, capacity, domain-health, executive-dashboard]
status: ready-for-review
---

# Implementation Plan: HyperTide Capacity Tracking & Database Integrity

## Executive Summary

This plan addresses two critical areas:
1. **Database Integrity Fixes** - From OpenClaw audit (16 issues, 3 critical)
2. **HyperTide Sending Capacity Tracking** - Per-domain volume monitoring for the executive dashboard

**Estimated Total Effort:** 6-8 development days
**Priority:** High - Required for accurate health monitoring

---

## Part 1: HyperTide Capacity Tracking Schema

### Business Requirements

Per HyperTide pricing model:
- **Entra**: $50/month = 2 domains + 100 inboxes (50/domain) @ 2 emails/inbox/day
- **Google**: $50/month = 5 domains + 15 inboxes (3/domain) @ 15-20 emails/inbox/day

**What We Need to Track:**
1. Expected sending capacity per domain
2. Current sending capacity (based on live inboxes)
3. Capacity impact when inboxes are killed
4. Domain viability (remaining capacity vs. operational threshold)
5. Provider segmentation (Microsoft/Entra vs Google)

### Database Schema Changes

#### Migration 038: Domain Capacity Tracking

```sql
-- File: migrations/038_domain_capacity_tracking.sql

-- =====================================================
-- PART 1: Add capacity tracking columns to domains
-- =====================================================

-- Add HyperTide-specific columns to domains table
ALTER TABLE domains ADD COLUMN IF NOT EXISTS provider_type VARCHAR(20);
-- Values: 'entra', 'google', 'other'

ALTER TABLE domains ADD COLUMN IF NOT EXISTS expected_inbox_count INTEGER DEFAULT 0;
-- Entra: 50 per domain, Google: 3 per domain

ALTER TABLE domains ADD COLUMN IF NOT EXISTS daily_send_limit_per_inbox INTEGER DEFAULT 2;
-- Entra: 2, Google: 15-20

ALTER TABLE domains ADD COLUMN IF NOT EXISTS expected_daily_capacity INTEGER GENERATED ALWAYS AS
    (expected_inbox_count * daily_send_limit_per_inbox) STORED;
-- Calculated: 50 * 2 = 100 for Entra, 3 * 15 = 45 for Google

ALTER TABLE domains ADD COLUMN IF NOT EXISTS current_daily_capacity INTEGER DEFAULT 0;
-- Calculated from live inboxes only

ALTER TABLE domains ADD COLUMN IF NOT EXISTS capacity_utilization NUMERIC(5,2) DEFAULT 0;
-- current_daily_capacity / expected_daily_capacity * 100

ALTER TABLE domains ADD COLUMN IF NOT EXISTS viability_status VARCHAR(20) DEFAULT 'healthy';
-- Values: 'healthy' (>70%), 'warning' (40-70%), 'critical' (<40%), 'deprecated'

ALTER TABLE domains ADD COLUMN IF NOT EXISTS capacity_updated_at TIMESTAMPTZ;

-- =====================================================
-- PART 2: Create domain capacity history table
-- =====================================================

CREATE TABLE IF NOT EXISTS domain_capacity_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    domain_id UUID NOT NULL REFERENCES domains(id) ON DELETE CASCADE,
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,

    -- Snapshot data
    snapshot_date DATE NOT NULL DEFAULT CURRENT_DATE,
    provider_type VARCHAR(20),

    -- Inbox counts at snapshot time
    total_inboxes INTEGER DEFAULT 0,
    live_inboxes INTEGER DEFAULT 0,
    dead_inboxes INTEGER DEFAULT 0,

    -- Capacity metrics
    expected_daily_capacity INTEGER DEFAULT 0,
    current_daily_capacity INTEGER DEFAULT 0,
    capacity_utilization NUMERIC(5,2) DEFAULT 0,

    -- Kill impact (deaths this day)
    inboxes_killed_today INTEGER DEFAULT 0,
    capacity_lost_today INTEGER DEFAULT 0,

    -- Cumulative since domain creation
    total_inboxes_killed INTEGER DEFAULT 0,
    total_capacity_lost INTEGER DEFAULT 0,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE(domain_id, snapshot_date)
);

CREATE INDEX idx_domain_capacity_history_domain ON domain_capacity_history(domain_id, snapshot_date DESC);
CREATE INDEX idx_domain_capacity_history_workspace ON domain_capacity_history(workspace_id, snapshot_date DESC);

-- =====================================================
-- PART 3: Create capacity impact events table
-- =====================================================

-- Records capacity impact when inboxes are killed
CREATE TABLE IF NOT EXISTS capacity_impact_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    domain_id UUID NOT NULL REFERENCES domains(id) ON DELETE CASCADE,
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    inbox_id UUID NOT NULL REFERENCES sender_accounts(id) ON DELETE CASCADE,

    -- Kill trigger info
    kill_trigger VARCHAR(50),  -- spam_complaint, hard_blocked_24h, etc.
    kill_reason TEXT,

    -- Capacity impact
    daily_capacity_lost INTEGER NOT NULL,  -- Single inbox capacity
    domain_capacity_before INTEGER NOT NULL,
    domain_capacity_after INTEGER NOT NULL,
    capacity_utilization_before NUMERIC(5,2),
    capacity_utilization_after NUMERIC(5,2),

    -- Did this kill cross a viability threshold?
    threshold_crossed BOOLEAN DEFAULT FALSE,
    previous_viability VARCHAR(20),
    new_viability VARCHAR(20),

    -- If this triggered domain deprecation consideration
    deprecation_recommended BOOLEAN DEFAULT FALSE,
    deprecation_reason TEXT,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_capacity_impact_domain ON capacity_impact_events(domain_id, created_at DESC);
CREATE INDEX idx_capacity_impact_workspace ON capacity_impact_events(workspace_id, created_at DESC);
CREATE INDEX idx_capacity_impact_threshold ON capacity_impact_events(threshold_crossed, created_at DESC);

-- =====================================================
-- PART 4: Functions for capacity calculation
-- =====================================================

-- Function: Calculate domain's current daily capacity
CREATE OR REPLACE FUNCTION calculate_domain_capacity(p_domain_id UUID)
RETURNS TABLE(
    live_inboxes INTEGER,
    daily_send_limit INTEGER,
    current_capacity INTEGER,
    expected_capacity INTEGER,
    utilization NUMERIC
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        COUNT(sa.id)::INTEGER as live_inboxes,
        COALESCE(d.daily_send_limit_per_inbox, 2)::INTEGER as daily_send_limit,
        (COUNT(sa.id) * COALESCE(d.daily_send_limit_per_inbox, 2))::INTEGER as current_capacity,
        COALESCE(d.expected_daily_capacity, 100)::INTEGER as expected_capacity,
        CASE
            WHEN COALESCE(d.expected_daily_capacity, 0) > 0
            THEN ROUND((COUNT(sa.id) * COALESCE(d.daily_send_limit_per_inbox, 2))::NUMERIC /
                       d.expected_daily_capacity * 100, 2)
            ELSE 0
        END as utilization
    FROM domains d
    LEFT JOIN sender_accounts sa ON SPLIT_PART(sa.email_address, '@', 2) = d.domain_name
        AND sa.workspace_id = d.workspace_id
        AND sa.inbox_state = 'live'
    WHERE d.id = p_domain_id
    GROUP BY d.id;
END;
$$ LANGUAGE plpgsql STABLE;

-- Function: Update domain capacity metrics (call after inbox state changes)
CREATE OR REPLACE FUNCTION update_domain_capacity(p_domain_id UUID)
RETURNS VOID AS $$
DECLARE
    v_cap RECORD;
    v_viability VARCHAR(20);
BEGIN
    -- Calculate current capacity
    SELECT * INTO v_cap FROM calculate_domain_capacity(p_domain_id);

    -- Determine viability status
    IF v_cap.utilization IS NULL OR v_cap.utilization = 0 THEN
        v_viability := 'deprecated';
    ELSIF v_cap.utilization < 40 THEN
        v_viability := 'critical';
    ELSIF v_cap.utilization < 70 THEN
        v_viability := 'warning';
    ELSE
        v_viability := 'healthy';
    END IF;

    -- Update domain record
    UPDATE domains
    SET current_daily_capacity = COALESCE(v_cap.current_capacity, 0),
        capacity_utilization = COALESCE(v_cap.utilization, 0),
        viability_status = v_viability,
        capacity_updated_at = NOW()
    WHERE id = p_domain_id;
END;
$$ LANGUAGE plpgsql;

-- Function: Record capacity impact when inbox is killed
CREATE OR REPLACE FUNCTION record_capacity_impact(
    p_inbox_id UUID,
    p_kill_trigger VARCHAR(50),
    p_kill_reason TEXT DEFAULT NULL
) RETURNS VOID AS $$
DECLARE
    v_domain_id UUID;
    v_workspace_id UUID;
    v_daily_limit INTEGER;
    v_before_cap INTEGER;
    v_after_cap INTEGER;
    v_before_util NUMERIC;
    v_after_util NUMERIC;
    v_before_viability VARCHAR(20);
    v_after_viability VARCHAR(20);
    v_threshold_crossed BOOLEAN := FALSE;
    v_deprecation_recommended BOOLEAN := FALSE;
    v_deprecation_reason TEXT;
BEGIN
    -- Get domain info for this inbox
    SELECT d.id, d.workspace_id, d.daily_send_limit_per_inbox,
           d.current_daily_capacity, d.capacity_utilization, d.viability_status
    INTO v_domain_id, v_workspace_id, v_daily_limit,
         v_before_cap, v_before_util, v_before_viability
    FROM sender_accounts sa
    JOIN domains d ON SPLIT_PART(sa.email_address, '@', 2) = d.domain_name
        AND sa.workspace_id = d.workspace_id
    WHERE sa.id = p_inbox_id;

    IF v_domain_id IS NULL THEN
        RETURN;  -- No domain found
    END IF;

    -- Calculate after-kill capacity
    v_after_cap := GREATEST(0, v_before_cap - COALESCE(v_daily_limit, 2));

    -- Recalculate utilization
    UPDATE domains SET current_daily_capacity = v_after_cap WHERE id = v_domain_id;
    PERFORM update_domain_capacity(v_domain_id);

    SELECT capacity_utilization, viability_status
    INTO v_after_util, v_after_viability
    FROM domains WHERE id = v_domain_id;

    -- Check if threshold was crossed
    IF v_before_viability != v_after_viability THEN
        v_threshold_crossed := TRUE;
    END IF;

    -- Check if deprecation should be recommended
    IF v_after_viability = 'critical' AND v_after_util < 30 THEN
        v_deprecation_recommended := TRUE;
        v_deprecation_reason := 'Domain below 30% capacity utilization. Consider deprecation.';
    ELSIF v_after_viability = 'deprecated' THEN
        v_deprecation_recommended := TRUE;
        v_deprecation_reason := 'Domain has no live inboxes remaining.';
    END IF;

    -- Record the impact event
    INSERT INTO capacity_impact_events (
        domain_id, workspace_id, inbox_id,
        kill_trigger, kill_reason,
        daily_capacity_lost, domain_capacity_before, domain_capacity_after,
        capacity_utilization_before, capacity_utilization_after,
        threshold_crossed, previous_viability, new_viability,
        deprecation_recommended, deprecation_reason
    ) VALUES (
        v_domain_id, v_workspace_id, p_inbox_id,
        p_kill_trigger, p_kill_reason,
        COALESCE(v_daily_limit, 2), v_before_cap, v_after_cap,
        v_before_util, v_after_util,
        v_threshold_crossed, v_before_viability, v_after_viability,
        v_deprecation_recommended, v_deprecation_reason
    );
END;
$$ LANGUAGE plpgsql;

-- =====================================================
-- PART 5: Views for executive dashboard
-- =====================================================

-- View: Domain capacity summary per workspace
CREATE OR REPLACE VIEW v_domain_capacity_summary AS
SELECT
    d.workspace_id,
    d.provider_type,
    COUNT(*) as total_domains,
    SUM(CASE WHEN d.viability_status = 'healthy' THEN 1 ELSE 0 END) as healthy_domains,
    SUM(CASE WHEN d.viability_status = 'warning' THEN 1 ELSE 0 END) as warning_domains,
    SUM(CASE WHEN d.viability_status = 'critical' THEN 1 ELSE 0 END) as critical_domains,
    SUM(CASE WHEN d.viability_status = 'deprecated' THEN 1 ELSE 0 END) as deprecated_domains,
    SUM(d.expected_daily_capacity) as total_expected_capacity,
    SUM(d.current_daily_capacity) as total_current_capacity,
    ROUND(AVG(d.capacity_utilization), 2) as avg_capacity_utilization
FROM domains d
WHERE d.is_active = TRUE
GROUP BY d.workspace_id, d.provider_type;

-- View: Domains needing attention (below 70% capacity)
CREATE OR REPLACE VIEW v_domains_capacity_at_risk AS
SELECT
    d.id as domain_id,
    d.domain_name,
    d.workspace_id,
    d.provider_type,
    d.expected_inbox_count,
    d.live_inbox_count,
    d.dead_inbox_count,
    d.expected_daily_capacity,
    d.current_daily_capacity,
    d.capacity_utilization,
    d.viability_status,
    -- Calculate days until domain is likely deprecated at current kill rate
    CASE
        WHEN d.live_inbox_count > 0 AND d.dead_inbox_count > 0 THEN
            (d.live_inbox_count::NUMERIC /
             (d.dead_inbox_count::NUMERIC /
              GREATEST(1, EXTRACT(days FROM NOW() - d.created_at))))::INTEGER
        ELSE NULL
    END as estimated_days_until_deprecated
FROM domains d
WHERE d.is_active = TRUE
  AND d.viability_status IN ('warning', 'critical')
ORDER BY d.capacity_utilization ASC;

-- View: Capacity impact last 7 days
CREATE OR REPLACE VIEW v_recent_capacity_impact AS
SELECT
    cie.workspace_id,
    d.domain_name,
    d.provider_type,
    COUNT(*) as inboxes_killed,
    SUM(cie.daily_capacity_lost) as total_capacity_lost,
    AVG(cie.capacity_utilization_after) as avg_remaining_utilization,
    COUNT(*) FILTER (WHERE cie.threshold_crossed) as threshold_crossings,
    COUNT(*) FILTER (WHERE cie.deprecation_recommended) as deprecation_recommendations
FROM capacity_impact_events cie
JOIN domains d ON d.id = cie.domain_id
WHERE cie.created_at >= NOW() - INTERVAL '7 days'
GROUP BY cie.workspace_id, d.domain_name, d.provider_type
ORDER BY total_capacity_lost DESC;

-- =====================================================
-- PART 6: Backfill existing data
-- =====================================================

-- Set provider_type based on infrastructure_type or infer from domain count
UPDATE domains d
SET provider_type = CASE
    WHEN d.infrastructure_type = 'google' THEN 'google'
    WHEN d.infrastructure_type = 'entra' THEN 'entra'
    WHEN d.infrastructure_type = 'microsoft' THEN 'entra'
    -- Infer: if domain has ~50 inboxes, it's Entra; if ~3, it's Google
    WHEN (SELECT COUNT(*) FROM sender_accounts sa
          WHERE SPLIT_PART(sa.email_address, '@', 2) = d.domain_name
            AND sa.workspace_id = d.workspace_id) >= 20 THEN 'entra'
    ELSE 'google'
END
WHERE d.provider_type IS NULL;

-- Set expected inbox counts based on provider
UPDATE domains
SET expected_inbox_count = CASE
    WHEN provider_type = 'entra' THEN 50
    WHEN provider_type = 'google' THEN 3
    ELSE 10  -- Default for unknown
END,
daily_send_limit_per_inbox = CASE
    WHEN provider_type = 'entra' THEN 2
    WHEN provider_type = 'google' THEN 15
    ELSE 2  -- Default conservative
END
WHERE expected_inbox_count = 0 OR expected_inbox_count IS NULL;

-- Update current capacity for all domains
DO $$
DECLARE
    domain_rec RECORD;
BEGIN
    FOR domain_rec IN SELECT id FROM domains WHERE is_active = TRUE LOOP
        PERFORM update_domain_capacity(domain_rec.id);
    END LOOP;
END $$;
```

### API Endpoint: Domain Capacity Dashboard

```python
# File: api/routes/capacity.py

"""
Domain capacity tracking routes for executive dashboard.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from uuid import UUID
from datetime import datetime

from database import fetch_all, fetch_one

router = APIRouter()


class DomainCapacityItem(BaseModel):
    """Individual domain capacity metrics."""
    domain_id: UUID
    domain_name: str
    provider_type: str  # 'entra' or 'google'

    # Inbox metrics
    expected_inbox_count: int
    live_inbox_count: int
    dead_inbox_count: int

    # Capacity metrics
    expected_daily_capacity: int  # emails/day
    current_daily_capacity: int
    capacity_utilization: float  # percentage

    # Status
    viability_status: str  # healthy, warning, critical, deprecated
    estimated_days_until_deprecated: Optional[int] = None

    # Recent impact
    inboxes_killed_7d: int = 0
    capacity_lost_7d: int = 0


class CapacitySummary(BaseModel):
    """Workspace-level capacity summary."""
    workspace_id: UUID
    provider_type: str

    # Domain counts by status
    total_domains: int
    healthy_domains: int
    warning_domains: int
    critical_domains: int
    deprecated_domains: int

    # Capacity totals
    total_expected_capacity: int  # emails/day
    total_current_capacity: int
    avg_capacity_utilization: float

    # Capacity lost (last 7 days)
    capacity_lost_7d: int
    inboxes_killed_7d: int


class CapacityDashboardResponse(BaseModel):
    """Full capacity dashboard response."""
    client_id: UUID

    # Summary by provider
    entra_summary: Optional[CapacitySummary] = None
    google_summary: Optional[CapacitySummary] = None

    # Combined metrics
    total_expected_capacity: int
    total_current_capacity: int
    overall_utilization: float

    # Domains needing attention
    at_risk_domains: list[DomainCapacityItem]

    # Impact metrics
    total_capacity_lost_7d: int
    total_inboxes_killed_7d: int
    threshold_crossings_7d: int
    deprecation_recommendations_7d: int

    last_updated: datetime


@router.get("/dashboard/{client_id}", response_model=CapacityDashboardResponse)
async def get_capacity_dashboard(client_id: UUID):
    """
    Get HyperTide capacity dashboard for executive view.

    Shows:
    - Sending capacity per domain (segmented by Microsoft vs Google)
    - Current vs expected capacity utilization
    - Domains at risk (warning/critical)
    - Capacity impact from recent kills
    """
    # Get client workspace
    client = await fetch_one("""
        SELECT c.id, c.workspace_id
        FROM clients c WHERE c.id = $1
    """, client_id)

    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    workspace_id = client["workspace_id"]

    if not workspace_id:
        return CapacityDashboardResponse(
            client_id=client_id,
            total_expected_capacity=0,
            total_current_capacity=0,
            overall_utilization=0,
            at_risk_domains=[],
            total_capacity_lost_7d=0,
            total_inboxes_killed_7d=0,
            threshold_crossings_7d=0,
            deprecation_recommendations_7d=0,
            last_updated=datetime.utcnow()
        )

    # Get capacity summaries by provider
    summaries = await fetch_all("""
        SELECT * FROM v_domain_capacity_summary
        WHERE workspace_id = $1
    """, workspace_id)

    entra_summary = None
    google_summary = None

    for s in (summaries or []):
        summary = CapacitySummary(
            workspace_id=workspace_id,
            provider_type=s["provider_type"] or "unknown",
            total_domains=s["total_domains"],
            healthy_domains=s["healthy_domains"],
            warning_domains=s["warning_domains"],
            critical_domains=s["critical_domains"],
            deprecated_domains=s["deprecated_domains"],
            total_expected_capacity=s["total_expected_capacity"] or 0,
            total_current_capacity=s["total_current_capacity"] or 0,
            avg_capacity_utilization=float(s["avg_capacity_utilization"] or 0),
            capacity_lost_7d=0,  # Will be filled below
            inboxes_killed_7d=0
        )

        if s["provider_type"] == "entra":
            entra_summary = summary
        elif s["provider_type"] == "google":
            google_summary = summary

    # Get at-risk domains
    at_risk_rows = await fetch_all("""
        SELECT * FROM v_domains_capacity_at_risk
        WHERE workspace_id = $1
        ORDER BY capacity_utilization ASC
        LIMIT 20
    """, workspace_id)

    at_risk_domains = [
        DomainCapacityItem(
            domain_id=r["domain_id"],
            domain_name=r["domain_name"],
            provider_type=r["provider_type"] or "unknown",
            expected_inbox_count=r["expected_inbox_count"] or 0,
            live_inbox_count=r["live_inbox_count"] or 0,
            dead_inbox_count=r["dead_inbox_count"] or 0,
            expected_daily_capacity=r["expected_daily_capacity"] or 0,
            current_daily_capacity=r["current_daily_capacity"] or 0,
            capacity_utilization=float(r["capacity_utilization"] or 0),
            viability_status=r["viability_status"],
            estimated_days_until_deprecated=r["estimated_days_until_deprecated"]
        )
        for r in (at_risk_rows or [])
    ]

    # Get impact metrics from last 7 days
    impact = await fetch_one("""
        SELECT
            COALESCE(SUM(daily_capacity_lost), 0) as capacity_lost,
            COUNT(*) as inboxes_killed,
            COUNT(*) FILTER (WHERE threshold_crossed) as threshold_crossings,
            COUNT(*) FILTER (WHERE deprecation_recommended) as deprecation_recs
        FROM capacity_impact_events
        WHERE workspace_id = $1
          AND created_at >= NOW() - INTERVAL '7 days'
    """, workspace_id)

    # Calculate totals
    total_expected = (
        (entra_summary.total_expected_capacity if entra_summary else 0) +
        (google_summary.total_expected_capacity if google_summary else 0)
    )
    total_current = (
        (entra_summary.total_current_capacity if entra_summary else 0) +
        (google_summary.total_current_capacity if google_summary else 0)
    )
    overall_util = (total_current / total_expected * 100) if total_expected > 0 else 0

    return CapacityDashboardResponse(
        client_id=client_id,
        entra_summary=entra_summary,
        google_summary=google_summary,
        total_expected_capacity=total_expected,
        total_current_capacity=total_current,
        overall_utilization=round(overall_util, 2),
        at_risk_domains=at_risk_domains,
        total_capacity_lost_7d=impact["capacity_lost"] if impact else 0,
        total_inboxes_killed_7d=impact["inboxes_killed"] if impact else 0,
        threshold_crossings_7d=impact["threshold_crossings"] if impact else 0,
        deprecation_recommendations_7d=impact["deprecation_recs"] if impact else 0,
        last_updated=datetime.utcnow()
    )
```

---

## Part 2: Database Integrity Fixes

### Priority 1: Critical Fixes (Execute Today)

```sql
-- File: migrations/039_critical_integrity_fixes.sql

-- =====================================================
-- FIX #1: Dead domains marked active (1,475 inboxes at risk)
-- =====================================================

-- Sync domain state to is_active
UPDATE domains SET is_active = false WHERE domain_state = 'dead';

-- Sync inbox status for dead domains
UPDATE sender_accounts sa
SET status = 'Not connected'
FROM domains d
WHERE sa.domain_id = d.id
  AND d.domain_state = 'dead'
  AND sa.status = 'Connected';

-- Add trigger to enforce this going forward
CREATE OR REPLACE FUNCTION sync_domain_state_to_active()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.domain_state = 'dead' THEN
        NEW.is_active = false;
        -- Also update all sender accounts
        UPDATE sender_accounts
        SET status = 'Not connected'
        WHERE domain_id = NEW.id AND status = 'Connected';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS tr_sync_domain_state ON domains;
CREATE TRIGGER tr_sync_domain_state
    BEFORE UPDATE ON domains
    FOR EACH ROW
    WHEN (OLD.domain_state IS DISTINCT FROM NEW.domain_state)
    EXECUTE FUNCTION sync_domain_state_to_active();

-- =====================================================
-- FIX #2: sender_account_count always 0
-- =====================================================

-- Backfill current counts
UPDATE domains d
SET sender_account_count = (
    SELECT COUNT(*) FROM sender_accounts sa WHERE sa.domain_id = d.id
);

-- Add trigger to maintain count
CREATE OR REPLACE FUNCTION update_domain_sender_count()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        UPDATE domains SET sender_account_count = sender_account_count + 1
        WHERE id = NEW.domain_id;
    ELSIF TG_OP = 'DELETE' THEN
        UPDATE domains SET sender_account_count = sender_account_count - 1
        WHERE id = OLD.domain_id;
    ELSIF TG_OP = 'UPDATE' AND OLD.domain_id IS DISTINCT FROM NEW.domain_id THEN
        UPDATE domains SET sender_account_count = sender_account_count - 1
        WHERE id = OLD.domain_id;
        UPDATE domains SET sender_account_count = sender_account_count + 1
        WHERE id = NEW.domain_id;
    END IF;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS tr_sender_account_count ON sender_accounts;
CREATE TRIGGER tr_sender_account_count
    AFTER INSERT OR DELETE OR UPDATE OF domain_id ON sender_accounts
    FOR EACH ROW
    EXECUTE FUNCTION update_domain_sender_count();

-- =====================================================
-- FIX #3: Clean up orphaned campaign inboxes
-- =====================================================

DELETE FROM campaign_inboxes WHERE campaign_id IS NULL;

-- Add NOT NULL constraint with default
ALTER TABLE campaign_inboxes
    ALTER COLUMN campaign_id SET NOT NULL;

-- =====================================================
-- FIX #4: Add priority missing indexes
-- =====================================================

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_response_messages_campaign_event
    ON response_messages(campaign_event_id);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_response_messages_sender_account
    ON response_messages(sender_account_id);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_kill_trigger_events_domain
    ON kill_trigger_events(domain_id);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_kill_trigger_events_replacement
    ON kill_trigger_events(replacement_inbox_id);

-- =====================================================
-- FIX #5: Analyze large table
-- =====================================================

ANALYZE sender_warmup_snapshots;
```

### Priority 2: Rolling Window for Gemini SOP (Week 2)

See `migrations/040_rolling_window_strike_tracking.sql` in the Gemini SOP action items document.

---

## Part 3: Kill Processor Integration

### Modify kill_processor.py to Record Capacity Impact

```python
# Add to sync_modules/kill_processor.py after inbox is marked dead

async def record_capacity_impact_for_kill(
    self,
    inbox_id: UUID,
    trigger_type: str,
    trigger_reason: str = None
):
    """Record the capacity impact when an inbox is killed."""
    await self.db.execute(
        "SELECT record_capacity_impact($1, $2, $3)",
        inbox_id, trigger_type, trigger_reason
    )

    # Check if deprecation was recommended
    impact = await self.db.fetchrow("""
        SELECT deprecation_recommended, deprecation_reason, new_viability
        FROM capacity_impact_events
        WHERE inbox_id = $1
        ORDER BY created_at DESC
        LIMIT 1
    """, inbox_id)

    if impact and impact["deprecation_recommended"]:
        # Alert about potential domain deprecation
        await self.slack_alerter.alert_domain_deprecation_recommended(
            inbox_id,
            impact["deprecation_reason"],
            impact["new_viability"]
        )
```

---

## Part 4: Executive Dashboard Frontend Components

### New Component: Capacity Utilization Card

```typescript
// charm-email-os/components/health/CapacityUtilizationCard.tsx

interface CapacitySummary {
  providerType: "entra" | "google";
  totalDomains: number;
  healthyDomains: number;
  warningDomains: number;
  criticalDomains: number;
  totalExpectedCapacity: number;
  totalCurrentCapacity: number;
  avgCapacityUtilization: number;
}

interface CapacityUtilizationProps {
  entraSummary: CapacitySummary | null;
  googleSummary: CapacitySummary | null;
  overallUtilization: number;
  capacityLost7d: number;
}

export function CapacityUtilizationCard({
  entraSummary,
  googleSummary,
  overallUtilization,
  capacityLost7d,
}: CapacityUtilizationProps) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Sending Capacity</CardTitle>
        <CardDescription>
          HyperTide infrastructure utilization by provider
        </CardDescription>
      </CardHeader>
      <CardContent>
        {/* Provider breakdown */}
        <div className="grid grid-cols-2 gap-4">
          {/* Microsoft/Entra */}
          <ProviderCapacityBlock
            provider="Microsoft"
            icon={<MicrosoftIcon />}
            expected={entraSummary?.totalExpectedCapacity || 0}
            current={entraSummary?.totalCurrentCapacity || 0}
            utilization={entraSummary?.avgCapacityUtilization || 0}
            domainsHealthy={entraSummary?.healthyDomains || 0}
            domainsWarning={entraSummary?.warningDomains || 0}
            domainsCritical={entraSummary?.criticalDomains || 0}
          />

          {/* Google */}
          <ProviderCapacityBlock
            provider="Google"
            icon={<GoogleIcon />}
            expected={googleSummary?.totalExpectedCapacity || 0}
            current={googleSummary?.totalCurrentCapacity || 0}
            utilization={googleSummary?.avgCapacityUtilization || 0}
            domainsHealthy={googleSummary?.healthyDomains || 0}
            domainsWarning={googleSummary?.warningDomains || 0}
            domainsCritical={googleSummary?.criticalDomains || 0}
          />
        </div>

        {/* Capacity lost indicator */}
        {capacityLost7d > 0 && (
          <Alert variant="destructive" className="mt-4">
            <AlertDescription>
              {capacityLost7d} emails/day capacity lost in the last 7 days
            </AlertDescription>
          </Alert>
        )}
      </CardContent>
    </Card>
  );
}
```

---

## Part 5: Implementation Timeline

### Week 1: Foundation + Critical Fixes

| Day | Task | Owner | Dependencies |
|-----|------|-------|--------------|
| 1 | Execute critical integrity fixes (039) | DBA | None |
| 2 | Create capacity tracking schema (038) | DBA | After 039 |
| 3 | Backfill provider_type and capacity data | DBA | After 038 |
| 3 | Add capacity API endpoint | Backend | After 038 |
| 4 | Integrate capacity tracking into kill_processor | Backend | After API |
| 5 | Add Slack alerts for deprecation | Backend | After integration |

### Week 2: Dashboard + Monitoring

| Day | Task | Owner | Dependencies |
|-----|------|-------|--------------|
| 1-2 | Build CapacityUtilizationCard component | Frontend | API ready |
| 3 | Integrate into health page | Frontend | Component done |
| 4 | Add domain viability table | Frontend | Component done |
| 5 | Testing + deployment | All | All tasks |

### Week 3: Gemini SOP Rolling Window

Follow the Gemini SOP action items for 48-hour rolling window implementation.

---

## Part 6: Success Metrics

Track these after implementation:

| Metric | Target | Measurement |
|--------|--------|-------------|
| Capacity utilization visibility | 100% domains tracked | `SELECT COUNT(*) FROM domains WHERE capacity_updated_at IS NOT NULL` |
| Impact tracking coverage | 100% kills recorded | `SELECT COUNT(*) FROM capacity_impact_events` vs `kill_queue` |
| Warning accuracy | >80% of at-risk domains identified before death | Compare predicted vs actual deaths |
| Dashboard latency | <500ms | API response time |

---

## Summary

This implementation plan delivers:

1. **HyperTide Capacity Tracking**
   - Per-domain expected vs. current sending capacity
   - Provider segmentation (Microsoft vs Google)
   - Viability scoring and deprecation recommendations
   - Capacity impact tracking when inboxes die

2. **Database Integrity Fixes**
   - Fix 1,475 inboxes at risk in dead domains
   - Correct sender_account_count (currently all 0)
   - Clean up 446 orphaned campaign inboxes
   - Add critical missing indexes

3. **Executive Dashboard**
   - Capacity utilization by provider
   - Domains at risk visualization
   - Capacity loss trend tracking
   - Deprecation alert system

**Total Estimated Effort:** 6-8 development days across 2 weeks
