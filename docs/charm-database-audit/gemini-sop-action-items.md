---
title: Gemini SOP Implementation - Quick Action Items
created: 2026-02-23
tags: [action-items, gemini-sop, kill-switch, priorities]
---

# Gemini Kill Switch SOP - Implementation Action Items

## 🎯 Executive Summary

**Verdict:** Charm Email OS has **superior infrastructure** but is **missing the graduated strike system** that makes the Gemini SOP effective.

**Critical Gap:** No 48-hour rolling window logic = can't implement Strike 2/3 system

**Effort Required:** 3-4 weeks of development

---

## ✅ What Charm Already Has (Better than SOP)

1. **SMTP Error Code Tracking** - ✅ EXCEEDS SOP
   - Tracks ALL 550 codes + extended classification
   - Differentiates hard_blocked vs hard_unknown
   - Stores in `response_messages` table

2. **Inbox-Level Automation** - ✅ EXCEEDS SOP
   - Instant inbox pausing on error
   - Tag-based flagging (preserves history)
   - Slack alerts on kills

3. **Warmup Tracking** - ✅ EXCEEDS SOP
   - 544 MB warmup snapshots table
   - Time-series warmup metrics
   - Automated warmup enable/disable

4. **Audit Logging** - ✅ EXCEEDS SOP
   - `inbox_rotation_history` table
   - `campaign_burn_events` table
   - `kill_triggers` table

---

## ❌ Critical Missing Features (Must Build)

### 1. 48-Hour Rolling Window Strike Tracking ⚠️ **URGENT**

**What's Missing:**
- Can't detect "2 errors within 48 hours"
- Daily counter resets (not rolling)
- No timestamp-based window logic

**SQL to Create:**
```sql
CREATE TABLE inbox_error_window (
    id UUID PRIMARY KEY,
    inbox_id UUID NOT NULL,
    domain_id UUID NOT NULL,
    error_code VARCHAR(20),
    detected_at TIMESTAMPTZ NOT NULL,
    window_expires_at TIMESTAMPTZ  -- detected_at + 48 hours
);

CREATE FUNCTION count_domain_strikes(p_domain_id UUID, p_hours INT DEFAULT 48)
RETURNS INTEGER AS $$
    SELECT COUNT(DISTINCT inbox_id)
    FROM inbox_error_window
    WHERE domain_id = p_domain_id
    AND detected_at >= NOW() - (p_hours || ' hours')::INTERVAL
$$ LANGUAGE SQL;
```

**Estimated Effort:** 2-3 days

---

### 2. Domain-Level Pausing (Strike 2) ⚠️ **HIGH PRIORITY**

**What's Missing:**
- No domain pause on 2 strikes
- No campaign reassignment automation
- No bench domain rotation

**Code to Write:**
```python
# In health_checks.py
async def execute_strike_2(self, domain_id: UUID):
    """Pause domain and rotate bench."""
    # 1. Pause all campaigns
    await self.pause_domain_campaigns(domain_id)

    # 2. Get bench domain
    bench = await self.get_bench_domain(workspace_id)

    # 3. Rotate
    await self.rotate_domain(source=domain_id, target=bench.id)

    # 4. Enable warmup
    await self.set_domain_warmup(domain_id, days=14)

    # 5. Alert
    await self.slack.notify_strike_2(domain_id)
```

**Estimated Effort:** 3-5 days

---

### 3. Bench Domain Management ⚠️ **MEDIUM PRIORITY**

**What's Missing:**
- No "bench" pool tier for domains
- No pre-warmed backup domains
- Manual domain management

**SQL to Create:**
```sql
ALTER TABLE domains ADD COLUMN pool_tier VARCHAR(20) DEFAULT 'active';
-- Values: 'active', 'bench', 'warming', 'retired'

CREATE TABLE domain_rotation_history (
    id UUID PRIMARY KEY,
    source_domain_id UUID,
    target_domain_id UUID,
    rotation_reason TEXT,
    campaigns_affected UUID[],
    rotated_at TIMESTAMPTZ
);
```

**UI to Build:**
- Bench domains dashboard
- Manual rotation controls
- Health monitoring per pool tier

**Estimated Effort:** 4-6 days

---

## 📋 Sprint Planning

### Sprint 1: Foundation (Week 1-2)

**Week 1: Critical Fixes**
- [ ] Fix dead domain sync bug (1,475 inboxes at risk)
- [ ] Backfill sender_account_count
- [ ] Clean up 446 orphaned campaign_inboxes
- [ ] Create missing indexes

**Week 2: Rolling Window**
- [ ] Create `inbox_error_window` table
- [ ] Write `count_domain_strikes()` function
- [ ] Modify sync worker to record errors
- [ ] Add cleanup job for expired windows

---

### Sprint 2: Strike System (Week 3-5)

**Week 3: Strike 2 Logic**
- [ ] Implement domain strike detection
- [ ] Build domain pause function
- [ ] Create campaign reassignment logic
- [ ] Add Slack alerts for Strike 2

**Week 4: Strike 3 Logic**
- [ ] Implement domain kill workflow
- [ ] Add domain swap automation
- [ ] Create incubator period tracking
- [ ] Build UI for killed domains

**Week 5: Testing**
- [ ] Write strike scenario tests
- [ ] Load testing (simulate errors)
- [ ] Validate campaign reassignment
- [ ] Create rollback plan

---

### Sprint 3: Bench Management (Week 6-8)

**Week 6: Database Schema**
- [ ] Add `pool_tier` to domains
- [ ] Create `domain_rotation_history` table
- [ ] Build bench domain views
- [ ] Write migration scripts

**Week 7: Backend API**
- [ ] GET /domains?pool_tier=bench
- [ ] POST /domains/:id/rotate
- [ ] POST /domains/:id/promote-to-active
- [ ] Add warmup automation for bench

**Week 8: Frontend UI**
- [ ] Bench domains page
- [ ] Rotation controls
- [ ] Health monitoring dashboard
- [ ] Strike history timeline

---

## 🔧 Technical Decisions Required

### Decision #1: Instant Kill vs Graduated Strikes

**Recommendation:** **HYBRID APPROACH**

```python
# Instant kill for catastrophic errors
INSTANT_KILL_CODES = ['550 5.7.705']  # Tenant threshold

# Graduated strikes for escalating issues
STRIKE_CODES = ['550 5.7.1', '550 5.4.1']

if error_code in INSTANT_KILL_CODES:
    kill_domain_immediately()
elif error_code in STRIKE_CODES:
    record_strike()
    if count_strikes() >= 3:
        kill_domain()
    elif count_strikes() == 2:
        pause_domain()
```

---

### Decision #2: Domain-Level vs Inbox-Level Rotation

**Recommendation:** **IMPLEMENT BOTH**

**Use Domain-Level When:**
- Strike 2 or 3 triggered
- Systemically bad domain reputation
- Microsoft/Google marks entire domain

**Use Inbox-Level When:**
- Single inbox technical issue
- Individual quota exceeded
- Isolated flags

---

### Decision #3: 24h vs 48h vs 7d Windows

**Current Charm:** 24h counters (daily reset)
**Gemini SOP:** 48h rolling window
**Recommendation:** **Support multiple windows**

```python
# Allow configurable windows per trigger
TRIGGER_WINDOWS = {
    'hard_blocked': 24,   # 24 hours for critical
    'spam_filter': 48,    # 48 hours for escalating
    'domain_reputation': 168  # 7 days for trends
}
```

---

## 📊 Success Metrics

**Track these after implementation:**

1. **Time to Detection**
   - Current: Instant (threshold-based)
   - Target: <2 hours for Strike 2 detection

2. **False Positive Rate**
   - Target: <5% of domains falsely flagged
   - Measure: Domains killed then manually reinstated

3. **Domain Burn Rate**
   - Current: Unknown (not tracked)
   - Target: <2% domains burned per month

4. **Bench Utilization**
   - Target: 80%+ of bench domains rotated in within 30 days
   - Measure: `domain_rotation_history` table

5. **Campaign Uptime**
   - Target: 99.5%+ campaigns have healthy inboxes
   - Measure: `campaign_inboxes` with `inbox_state='live'`

---

## 🚨 Immediate Actions (Today)

### 1. Run Database Fixes (15 minutes)

```sql
-- FIX #1: Dead domain sync (CRITICAL)
UPDATE domains SET is_active = false WHERE domain_state = 'dead';

UPDATE sender_accounts sa
SET status = 'Not connected'
FROM domains d
WHERE sa.domain_id = d.id AND d.domain_state = 'dead';

-- FIX #2: Backfill sender_account_count
UPDATE domains d
SET sender_account_count = (
  SELECT COUNT(*) FROM sender_accounts sa WHERE sa.domain_id = d.id
);

-- FIX #3: Clean up orphaned campaign inboxes
DELETE FROM campaign_inboxes WHERE campaign_id IS NULL;

-- FIX #4: Add critical indexes
CREATE INDEX CONCURRENTLY idx_response_messages_campaign_event
  ON response_messages(campaign_event_id);

CREATE INDEX CONCURRENTLY idx_response_messages_sender_account
  ON response_messages(sender_account_id);

CREATE INDEX CONCURRENTLY idx_kill_trigger_events_domain
  ON kill_trigger_events(domain_id);
```

### 2. Create Rolling Window Table (30 minutes)

```sql
-- File: migrations/038_rolling_window_strike_tracking.sql

CREATE TABLE inbox_error_window (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    inbox_id UUID NOT NULL REFERENCES sender_accounts(id) ON DELETE CASCADE,
    domain_id UUID NOT NULL REFERENCES domains(id) ON DELETE CASCADE,
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    error_code VARCHAR(20) NOT NULL,
    error_message TEXT,
    detected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    window_expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_error_window_domain_time
  ON inbox_error_window(domain_id, detected_at DESC);

CREATE INDEX idx_error_window_expiry
  ON inbox_error_window(window_expires_at)
  WHERE window_expires_at > NOW();

CREATE OR REPLACE FUNCTION count_domain_strikes(
    p_domain_id UUID,
    p_window_hours INTEGER DEFAULT 48
) RETURNS INTEGER AS $$
    SELECT COUNT(DISTINCT inbox_id)
    FROM inbox_error_window
    WHERE domain_id = p_domain_id
    AND detected_at >= NOW() - (p_window_hours || ' hours')::INTERVAL
$$ LANGUAGE SQL STABLE;

-- Cleanup job (run daily)
CREATE OR REPLACE FUNCTION cleanup_expired_error_windows()
RETURNS INTEGER AS $$
DECLARE
    deleted_count INTEGER;
BEGIN
    DELETE FROM inbox_error_window
    WHERE window_expires_at < NOW();

    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    RETURN deleted_count;
END;
$$ LANGUAGE plpgsql;
```

### 3. Modify Sync Worker (1 hour)

```python
# File: sync_modules/sync_events.py
# Add after line 452 (after extract_bounce_reason)

async def record_error_in_window(
    self,
    inbox_id: UUID,
    domain_id: UUID,
    workspace_id: UUID,
    error_code: str,
    error_message: str,
    window_hours: int = 48
):
    """Record error in rolling window table."""
    await self.db.execute("""
        INSERT INTO inbox_error_window
        (inbox_id, domain_id, workspace_id, error_code, error_message, window_expires_at)
        VALUES ($1, $2, $3, $4, $5, NOW() + ($6 || ' hours')::INTERVAL)
    """, inbox_id, domain_id, workspace_id, error_code, error_message, window_hours)

# Modify extract_bounce_reason to also record in window
async def process_bounce_event(self, event_data):
    # ... existing code ...

    if bounce_type in ['hard_blocked', 'hard_unknown']:
        # Record in rolling window
        await self.record_error_in_window(
            inbox_id=event_data['inbox_id'],
            domain_id=event_data['domain_id'],
            workspace_id=event_data['workspace_id'],
            error_code=smtp_code,
            error_message=bounce_reason
        )
```

---

## 📝 Verification Queries

**After implementation, run these to verify:**

```sql
-- 1. Verify rolling window tracking works
SELECT
    domain_id,
    count_domain_strikes(domain_id, 48) as strikes_48h,
    COUNT(*) as total_errors
FROM inbox_error_window
WHERE detected_at >= NOW() - INTERVAL '48 hours'
GROUP BY domain_id
HAVING count_domain_strikes(domain_id, 48) >= 2
ORDER BY strikes_48h DESC;

-- 2. Verify dead domains fixed
SELECT COUNT(*) FROM domains
WHERE domain_state = 'dead' AND is_active = true;
-- Should return: 0

-- 3. Verify sender_account_count accurate
SELECT COUNT(*) FROM domains d
WHERE d.sender_account_count != (
  SELECT COUNT(*) FROM sender_accounts WHERE domain_id = d.id
);
-- Should return: 0

-- 4. Verify strike detection working
SELECT
    d.domain_name,
    count_domain_strikes(d.id, 48) as strikes,
    d.domain_state
FROM domains d
WHERE count_domain_strikes(d.id, 48) >= 2
ORDER BY strikes DESC;
```

---

## 🎓 Key Learnings

### What Charm Does Better
1. ✅ More sophisticated error classification
2. ✅ Comprehensive audit logging
3. ✅ Inbox-level granular control
4. ✅ Tag-based system (preserves history)

### What Gemini SOP Teaches Us
1. ⚠️ Graduated strikes prevent overreaction
2. ⚠️ Time windows catch systemic issues
3. ⚠️ Domain-level rotation protects reputation
4. ⚠️ Bench system ensures readiness

### Architectural Takeaways
- **Instant kill** for catastrophic errors
- **Graduated strikes** for escalating issues
- **Both** inbox AND domain rotation
- **Hybrid** approach is best

---

**Next Steps:**
1. ✅ Review this document with team
2. ✅ Get approval for sprint planning
3. ✅ Create Jira tickets for each action item
4. ✅ Assign DBA, Backend, Frontend teams
5. ✅ Start Week 1 critical fixes

**Owner:** Platform Team
**Deadline:** 4 weeks from approval
**Dependencies:** Database audit fixes must complete first
