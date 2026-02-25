---
title: Charm Email OS vs Gemini Kill Switch SOP - Comprehensive Analysis
created: 2026-02-23
tags: [comparison, sop, kill-switch, gemini, implementation-gaps]
status: action-required
---

# Charm Email OS vs Gemini "Kill Switch" SOP - Full System Comparison

## Executive Summary

**Bottom Line:** Charm Email OS has **significantly more sophisticated** error tracking and health monitoring infrastructure than the Gemini SOP describes, BUT is missing the **critical 48-hour rolling window logic** and **domain-level strike system** that makes the Gemini SOP effective for Microsoft Entra environments.

### Key Findings

**✅ Charm EXCEEDS Gemini SOP in:**
- Error classification (differentiated bounce types)
- Granular tracking (campaign burn events, rotation history)
- Automation (inbox pool promotion, warmup)
- Visibility (comprehensive audit logs)

**❌ Charm MISSING from Gemini SOP:**
- 48-hour rolling window strike counting
- Domain-level pausing (Strike 2)
- Bench domain rotation system
- Tenant-level protection logic

**⚠️ Architectural Differences:**
- Instant kill vs graduated strike system
- Inbox-level vs domain-level rotation
- Multi-provider vs Entra-specific design

---

## Part 1: Feature-by-Feature Comparison

### 1. SMTP Error Code Monitoring

#### Gemini SOP Requirements
```
Monitor these Microsoft 550 error codes:
- 550 5.1.8 (Access denied, bad outbound sender)
- 550 5.7.1 (Message rejected as spam)
- 550 5.4.1 (Recipient address rejected)
- 550 5.7.705 (Tenant exceeded threshold) ⚠️ CRITICAL
```

#### Charm Implementation
**Status:** ✅ **FULLY IMPLEMENTED - EXCEEDS SOP**

**Database Schema:**
```sql
-- response_messages table
bounce_type VARCHAR(20)  -- hard_blocked, hard_unknown, soft_full, soft_temp
bounce_reason TEXT       -- Stores full SMTP code + message
received_at TIMESTAMPTZ  -- When bounce occurred
```

**Code Implementation:**
- File: `sync_modules/sync_events.py` (lines 331-452)
- Regex patterns extract SMTP codes: `5\.1\.8`, `5\.7\.1`, `5\.7\.705`, etc.
- Classification logic categorizes bounces by severity

**Current Data (Charm Workspace):**
```
bounce_type    | count | affected_inboxes
hard_unknown   | 23    | 20
hard_blocked   | 5     | 5
soft_full      | 1     | 1
```

**Verdict:** Charm **exceeds** the SOP by tracking ALL 550 codes plus extended classification.

---

### 2. Strike System & Time Windows

#### Gemini SOP Requirements

**Strike 1 (1 inbox flagged):**
- Action: Pause that inbox only
- Domain Status: Active (49 inboxes continue)

**Strike 2 (2 inboxes in 48h):**
- Action: Pause ENTIRE domain
- Rotate bench domain into active campaign
- Put sick domain on 100% warmup for 14-21 days

**Strike 3 (3 inboxes in 48h):**
- Action: Kill domain entirely
- Execute domain swap ($15)
- Place new domain in 30-day incubator

#### Charm Implementation
**Status:** ⚠️ **PARTIALLY IMPLEMENTED**

| Strike Level | Gemini SOP | Charm Reality | Status |
|-------------|-----------|---------------|---------|
| Strike 1 | Pause inbox | ✅ `inbox_state='dead'` + tags | ✅ **AUTOMATED** |
| Strike 2 | Pause domain + rotate bench | ❌ No domain pause | ❌ **MISSING** |
| Strike 3 | Kill domain + swap | ⚠️ Marks `domain_state='dead'` only | ⚠️ **PARTIAL** |
| 48h Window | Required for strike counting | ❌ Uses 24h counters (daily reset) | ❌ **MISSING** |

**Current Implementation (health_checks.py):**
```python
# Charm uses INSTANT thresholds, not rolling windows
if inbox.hard_blocked_24h >= 1:
    await self.flag_inbox(inbox.id, 'hard_blocked')
    # This is Strike 1, but instant, not time-windowed
```

**Critical Gap:** Charm cannot detect "2 errors within 48 hours" because:
1. Counters reset daily (not rolling)
2. No timestamp tracking for window logic
3. No strike counting across inboxes on a domain

**Database Evidence:**
```sql
-- No kill triggers fired for Charm workspace
SELECT COUNT(*) FROM kill_triggers
WHERE workspace_id = 'b9abd34a-f16a-4b92-bda0-5af10f8c44bd';
-- Returns: 0

-- All 6 dead domains marked dead WITHOUT trigger history
SELECT domain_name, domain_state, killed_at
FROM domains
WHERE domain_state = 'dead'
  AND workspace_id = 'b9abd34a-f16a-4b92-bda0-5af10f8c44bd';
-- Returns: 6 domains with killed_at = NULL
```

**Verdict:** Charm lacks the **graduated strike system** that defines the Gemini SOP.

---

### 3. Automated Pausing Logic

#### Gemini SOP Requirements
- Inbox-level pause (Strike 1)
- Domain-level pause (Strike 2)
- Campaign reassignment (Strike 2)
- Sequencer integration (EmailBison API)

#### Charm Implementation
**Status:** ✅ **INBOX-LEVEL AUTOMATED** | ❌ **DOMAIN-LEVEL MISSING**

**What Works:**
```python
# kill_processor.py (lines 78-233)
async def process_kill(self, inbox_id):
    # 1. Mark inbox as dead in database
    await self.db.execute(
        "UPDATE sender_accounts SET inbox_state = 'dead' WHERE id = $1",
        inbox_id
    )

    # 2. Tag inbox in EmailBison (doesn't delete)
    await self.emailbison.tag_inbox(inbox_id, f"flagged_{trigger_type}")

    # 3. Send Slack alert
    await self.slack_alerter.notify_inbox_killed(inbox_id, trigger_type)
```

**What's Missing:**
- No domain-level pause function
- No campaign reassignment automation
- No bench domain rotation

**Key Difference:**
- **Gemini**: Pauses campaigns at sequencer level (stops sending)
- **Charm**: Tags inboxes (prevents future assignment, doesn't stop active campaigns)

**Verdict:** Charm's tagging approach is **superior for visibility** but lacks **domain-level pausing**.

---

### 4. Domain Rotation & Bench System

#### Gemini SOP Requirements
```
Bench Domain Pool:
- Pre-warmed domains on standby
- Instant rotation on Strike 2
- Automated campaign reassignment
- 30-day incubator for new domains
```

#### Charm Implementation
**Status:** ⚠️ **DIFFERENT ARCHITECTURE**

**Charm's Approach (Inbox-Level Rotation):**
```sql
-- pool_tier system (inbox-level, not domain-level)
SELECT pool_tier, COUNT(*) FROM sender_accounts
WHERE workspace_id = 'b9abd34a-f16a-4b92-bda0-5af10f8c44bd'
GROUP BY pool_tier;

-- Expected:
pool_tier     | count
primary       | 10-15  (deployed in campaigns)
hot_backup    | 5-10   (ready for promotion)
warming       | 20-30  (in warmup phase)
```

**Inbox Promotion Logic:**
```python
# kill_processor.py (lines 628-736)
async def promote_backup_inbox(self, killed_inbox_id):
    # Find hot_backup inbox on same domain
    backup = await self.get_hot_backup_inbox(domain_id)

    # Promote: hot_backup → primary
    await self.promote_inbox_tier(backup.id, 'primary')

    # Backfill: warming → hot_backup
    warming = await self.get_next_warming_inbox(domain_id)
    await self.promote_inbox_tier(warming.id, 'hot_backup')
```

**What Charm Has:**
- ✅ Inbox-level tiers (primary, hot_backup, warming)
- ✅ Automated inbox promotion on kill
- ✅ `inbox_rotation_history` table for audit

**What Charm Lacks:**
- ❌ Domain-level "bench" concept
- ❌ Domain rotation from bench → active
- ❌ Domain-level campaign reassignment

**Verdict:** Charm's **inbox-level** rotation is more granular but **doesn't address domain-level strikes**.

---

### 5. Warmup Period Tracking

#### Gemini SOP Requirements
```
After Strike 2:
- 14-21 days automated warmup
- 100% warmup traffic (no cold sending)
- Domain remains on bench until warmup complete
```

#### Charm Implementation
**Status:** ✅ **FULLY IMPLEMENTED - EXCEEDS SOP**

**Database Schema:**
```sql
-- sender_accounts table
warmup_enabled BOOLEAN DEFAULT true
warmup_started_at TIMESTAMPTZ
warmup_stopped_at TIMESTAMPTZ
warmup_score NUMERIC(5,2)  -- 0.00 to 100.00

-- sender_warmup_snapshots table (544 MB, 96K rows)
snapshot_date DATE
emails_sent_today INTEGER
warmup_emails_sent INTEGER
bounces_today INTEGER
replies_today INTEGER
```

**Automation:**
- Sync worker (`sync_warmup.py`) auto-enables warmup for connected inboxes
- Tracks warmup progress over time
- Stores time-series data for analysis

**Example Query:**
```sql
SELECT
    email_address,
    warmup_enabled,
    warmup_started_at,
    EXTRACT(days FROM NOW() - warmup_started_at) as warmup_days
FROM sender_accounts
WHERE warmup_enabled = true
  AND workspace_id = 'b9abd34a-f16a-4b92-bda0-5af10f8c44bd'
ORDER BY warmup_days DESC;
```

**Verdict:** Charm **exceeds** the SOP with granular warmup tracking.

---

## Part 2: Database Schema Deep Dive

### Current Charm Schema vs Gemini SOP Needs

| Database Component | Gemini SOP Need | Charm Schema | Gap Analysis |
|-------------------|----------------|--------------|--------------|
| **Error Code Storage** | Track 550 codes | ✅ `response_messages.bounce_reason` | ✅ **ALIGNED** |
| **Strike Counter** | Count errors in 48h | ❌ Only 24h counters | ❌ **MISSING TABLE** |
| **Time Window** | Track timestamps | ⚠️ `received_at` exists, not used | ⚠️ **LOGIC MISSING** |
| **Domain State** | live, bench, dead | ✅ `domain_state` enum | ⚠️ No 'bench' value |
| **Inbox State** | active, paused, dead | ✅ `inbox_state` enum | ✅ **ALIGNED** |
| **Kill Queue** | Track pending kills | ✅ `kill_queue` table | ✅ **IMPLEMENTED** |
| **Kill Triggers** | Track why killed | ✅ `kill_triggers` table | ✅ **IMPLEMENTED** |
| **Rotation History** | Track promotions | ✅ `inbox_rotation_history` | ✅ **EXCEEDS SOP** |
| **Campaign Burn** | Track trigger source | ✅ `campaign_burn_events` | ✅ **EXCEEDS SOP** |

### Missing Tables/Columns Needed

#### 1. Rolling Window Strike Tracking
```sql
CREATE TABLE inbox_error_window (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    inbox_id UUID NOT NULL REFERENCES sender_accounts(id),
    domain_id UUID NOT NULL REFERENCES domains(id),
    workspace_id UUID NOT NULL REFERENCES workspaces(id),
    error_code VARCHAR(20) NOT NULL,  -- e.g., "550 5.7.1"
    error_message TEXT,
    detected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    window_expires_at TIMESTAMPTZ,  -- detected_at + 48 hours
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_error_window_domain ON inbox_error_window(domain_id, detected_at);
CREATE INDEX idx_error_window_expiry ON inbox_error_window(window_expires_at)
    WHERE window_expires_at > NOW();

-- Function to count strikes in window
CREATE OR REPLACE FUNCTION count_domain_strikes(
    p_domain_id UUID,
    p_window_hours INTEGER DEFAULT 48
) RETURNS INTEGER AS $$
    SELECT COUNT(DISTINCT inbox_id)
    FROM inbox_error_window
    WHERE domain_id = p_domain_id
    AND detected_at >= NOW() - (p_window_hours || ' hours')::INTERVAL
$$ LANGUAGE SQL;
```

#### 2. Domain Pool Tier
```sql
-- Add to domains table
ALTER TABLE domains
ADD COLUMN pool_tier VARCHAR(20) DEFAULT 'active';
-- Values: 'active', 'bench', 'warming', 'retired'

-- Add bench rotation tracking
CREATE TABLE domain_rotation_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES workspaces(id),
    source_domain_id UUID REFERENCES domains(id),
    target_domain_id UUID REFERENCES domains(id),
    rotation_reason TEXT,  -- "Strike 2 detected", "Manual rotation"
    campaigns_affected UUID[],
    inboxes_reassigned INTEGER,
    rotated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    rotated_by VARCHAR(100)  -- "system" or user email
);
```

---

## Part 3: Implementation Gaps & Recommendations

### CRITICAL Gaps (Must Fix)

#### Gap #1: 48-Hour Rolling Window ⚠️ **HIGH PRIORITY**

**Problem:**
Charm uses 24-hour counters that reset daily. Cannot detect "2 errors within 48 hours" pattern.

**Impact:**
- Can't implement Strike 2 logic
- Domains may avoid detection by spreading errors over reset periods
- No time-window based analysis

**Solution:**
```python
# New module: sync_modules/strike_tracker.py
class StrikeTracker:
    async def record_error(self, inbox_id: UUID, error_code: str):
        """Record error in rolling window table."""
        await self.db.execute("""
            INSERT INTO inbox_error_window
            (inbox_id, domain_id, error_code, window_expires_at)
            SELECT
                $1,
                domain_id,
                $2,
                NOW() + INTERVAL '48 hours'
            FROM sender_accounts WHERE id = $1
        """, inbox_id, error_code)

    async def check_domain_strikes(self, domain_id: UUID) -> int:
        """Count unique inboxes with errors in 48h window."""
        return await self.db.fetchval(
            "SELECT count_domain_strikes($1, 48)",
            domain_id
        )

    async def cleanup_expired_windows(self):
        """Prune expired window records (run daily)."""
        await self.db.execute(
            "DELETE FROM inbox_error_window WHERE window_expires_at < NOW()"
        )
```

**Estimated Effort:** 2-3 days
- Day 1: Create table, write migration
- Day 2: Implement tracking logic
- Day 3: Add to sync worker, test

---

#### Gap #2: Domain-Level Strike System ⚠️ **HIGH PRIORITY**

**Problem:**
No automated domain pausing or rotation on Strike 2.

**Impact:**
- Entire domain can be burned before detection
- No graduated response to escalating issues
- Manual intervention required for domain swaps

**Solution:**
```python
# Modify: sync_modules/health_checks.py
class HealthChecker:
    async def check_domain_health(self, domain_id: UUID):
        """Check domain for Strike 2 or Strike 3 conditions."""
        strike_count = await self.strike_tracker.check_domain_strikes(domain_id)

        if strike_count == 2:
            # STRIKE 2: Pause domain, rotate bench
            await self.execute_strike_2(domain_id)
        elif strike_count >= 3:
            # STRIKE 3: Kill domain
            await self.execute_strike_3(domain_id)

    async def execute_strike_2(self, domain_id: UUID):
        """Pause domain and rotate bench domain."""
        # 1. Pause all campaigns on this domain
        await self.pause_domain_campaigns(domain_id)

        # 2. Find bench domain
        bench_domain = await self.get_bench_domain(workspace_id)

        # 3. Rotate bench → active
        await self.rotate_domain(
            source=domain_id,
            target=bench_domain.id,
            reason="Strike 2 detected"
        )

        # 4. Put sick domain on warmup
        await self.set_domain_warmup(domain_id, days=14)

        # 5. Alert
        await self.slack.notify_strike_2(domain_id)

    async def pause_domain_campaigns(self, domain_id: UUID):
        """Remove domain inboxes from active campaigns."""
        # Get all inboxes on domain
        inboxes = await self.db.fetch(
            "SELECT id FROM sender_accounts WHERE domain_id = $1",
            domain_id
        )

        # Remove from campaign_inboxes
        for inbox in inboxes:
            await self.db.execute(
                "DELETE FROM campaign_inboxes WHERE sender_account_id = $1",
                inbox['id']
            )
```

**Estimated Effort:** 3-5 days
- Day 1-2: Implement strike detection logic
- Day 3: Build domain rotation function
- Day 4: Campaign reassignment automation
- Day 5: Testing and validation

---

#### Gap #3: Bench Domain Management ⚠️ **MEDIUM PRIORITY**

**Problem:**
No concept of "bench domains" (warmed but inactive, ready for rotation).

**Impact:**
- Manual domain management required
- No pre-warmed backups ready
- Slow response to Strike 2 events

**Solution:**
```sql
-- Migration: 039_domain_bench_system.sql

-- Add pool_tier to domains
ALTER TABLE domains ADD COLUMN pool_tier VARCHAR(20) DEFAULT 'active';

-- Create view for bench domain selection
CREATE VIEW v_bench_domains AS
SELECT
    d.*,
    COUNT(sa.id) as inbox_count,
    AVG(sa.warmup_score) as avg_warmup_score
FROM domains d
LEFT JOIN sender_accounts sa ON sa.domain_id = d.id AND sa.inbox_state = 'live'
WHERE d.pool_tier = 'bench'
  AND d.domain_state = 'live'
  AND d.is_active = true
GROUP BY d.id
HAVING COUNT(sa.id) >= 10  -- At least 10 warmed inboxes
ORDER BY AVG(sa.warmup_score) DESC;
```

**UI Component:**
```typescript
// charm-email-os/app/domains/bench/page.tsx
export default function BenchDomainsPage() {
  const { data: benchDomains } = useQuery({
    queryKey: ['domains', 'bench'],
    queryFn: () => api.get('/domains?pool_tier=bench')
  });

  return (
    <DomainGrid
      domains={benchDomains}
      actions={[
        { label: 'Promote to Active', onClick: promoteDomain },
        { label: 'Start Warmup', onClick: startWarmup }
      ]}
    />
  );
}
```

**Estimated Effort:** 4-6 days
- Day 1-2: Database schema changes
- Day 3-4: Backend API for bench management
- Day 5-6: UI for viewing/managing bench domains

---

### Architectural Decisions to Make

#### Decision #1: Instant Kill vs Strike System

**Current Charm Approach:**
```python
if inbox.hard_blocked_24h >= 1:
    kill_inbox_immediately()  # Instant kill
```

**Gemini SOP Approach:**
```python
strikes = count_strikes_in_48h_window(domain_id)
if strikes == 1:
    pause_inbox()
elif strikes == 2:
    pause_domain()
elif strikes >= 3:
    kill_domain()
```

**Recommendation:**
- **Keep instant kill for 550 5.7.705 (tenant threshold)** - This is catastrophic, requires immediate action
- **Add graduated strikes for 550 5.7.1 (spam filter)** - This can escalate, use time window
- **Hybrid approach:** Instant kill for critical codes, graduated for warning codes

**Proposed Logic:**
```python
# Instant kill codes (no strikes needed)
INSTANT_KILL_CODES = ['550 5.7.705', '550 5.1.8']

# Graduated strike codes
STRIKE_CODES = ['550 5.7.1', '550 5.4.1']

if error_code in INSTANT_KILL_CODES:
    await self.kill_domain_immediately(domain_id)
elif error_code in STRIKE_CODES:
    await self.record_strike(domain_id)
    strikes = await self.count_strikes(domain_id)
    if strikes >= 3:
        await self.kill_domain(domain_id)
    elif strikes == 2:
        await self.pause_domain(domain_id)
```

---

#### Decision #2: Domain-Level vs Inbox-Level Rotation

**Gemini SOP:** Rotate entire domains (52 inboxes at once)
**Charm Current:** Rotate individual inboxes within domains

**Recommendation:** **Implement BOTH**

**Use Domain-Level Rotation When:**
- Strike 2 or Strike 3 triggered
- Domain reputation is systemically bad
- Microsoft/Google marks entire domain as spam

**Use Inbox-Level Rotation When:**
- Single inbox has technical issue
- Individual inbox quota exceeded
- Targeted inbox-level flags

**Implementation:**
```python
class RotationManager:
    async def rotate_inbox(self, inbox_id: UUID):
        """Single inbox rotation (current Charm behavior)."""
        # ... existing logic

    async def rotate_domain(self, domain_id: UUID):
        """Full domain rotation (new Gemini SOP behavior)."""
        # Get all campaigns using this domain
        campaigns = await self.get_domain_campaigns(domain_id)

        # Get bench domain
        bench = await self.get_best_bench_domain(workspace_id)

        # Reassign all campaigns to bench domain inboxes
        for campaign in campaigns:
            await self.reassign_campaign_domain(
                campaign_id=campaign.id,
                from_domain=domain_id,
                to_domain=bench.id
            )
```

---

## Part 4: System-Wide Recommendations

### Immediate Actions (Week 1)

**Priority 1: Fix Dead Domain Sync Bug** (from audit doc)
```sql
-- CRITICAL: 1,475 inboxes in dead domains still marked "Connected"
UPDATE domains SET is_active = false WHERE domain_state = 'dead';

UPDATE sender_accounts sa
SET status = 'Not connected'
FROM domains d
WHERE sa.domain_id = d.id AND d.domain_state = 'dead';
```

**Priority 2: Add Rolling Window Tracking**
- Create `inbox_error_window` table
- Implement `count_domain_strikes()` function
- Modify sync worker to record errors in window

**Priority 3: Backfill sender_account_count**
```sql
UPDATE domains d
SET sender_account_count = (
  SELECT COUNT(*) FROM sender_accounts sa WHERE sa.domain_id = d.id
);
```

---

### Short-Term Enhancements (Week 2-4)

**1. Implement Strike 2 Logic**
- Domain pausing on 2 strikes
- Bench domain rotation
- Campaign reassignment automation

**2. Build Bench Domain Management**
- Add `pool_tier` to domains
- Create UI for managing bench
- Automate warmup tracking for bench domains

**3. Enhance Error Classification**
```python
# Expand error code taxonomy
ERROR_CODE_SEVERITY = {
    '550 5.7.705': 'CATASTROPHIC',  # Tenant ban
    '550 5.1.8': 'CRITICAL',         # Access denied
    '550 5.7.1': 'HIGH',             # Spam filter
    '550 5.4.1': 'MEDIUM',           # Domain blacklist
    '421': 'LOW'                     # Temporary issue
}
```

---

### Long-Term Strategy (Month 2+)

**1. Multi-Tier Kill System**
- Instant kill for catastrophic errors
- Graduated strikes for escalating issues
- Manual review for edge cases

**2. Predictive Health Scoring**
```python
# Use warmup data to predict domain health
def calculate_health_score(domain_id):
    """Predict likelihood of domain burning in next 7 days."""
    metrics = {
        'bounce_rate_7d': get_bounce_rate(domain_id),
        'reply_rate_trend': get_reply_trend(domain_id),
        'warmup_score': get_warmup_score(domain_id),
        'days_since_last_error': get_days_since_error(domain_id)
    }
    return ml_model.predict(metrics)  # 0-100 score
```

**3. Automated Domain Procurement**
```python
# Auto-buy replacement domains when bench depletes
async def maintain_bench_inventory(workspace_id):
    bench_count = await count_bench_domains(workspace_id)

    if bench_count < 5:  # Minimum bench size
        # Trigger domain purchase job
        await create_domain_purchase_job(
            workspace_id=workspace_id,
            count=10,
            registrar='dynadot'
        )
```

---

## Part 5: Testing & Validation Plan

### Test Scenarios

**Scenario 1: Strike 1 (Single Inbox Error)**
```python
async def test_strike_1():
    # Simulate 550 5.7.1 error on 1 inbox
    await simulate_bounce(inbox_id, '550 5.7.1')

    # Verify inbox paused
    inbox = await get_inbox(inbox_id)
    assert inbox.inbox_state == 'dead'
    assert 'flagged_hard_blocked' in inbox.tags

    # Verify domain still active
    domain = await get_domain(domain_id)
    assert domain.domain_state == 'live'
```

**Scenario 2: Strike 2 (2 Inboxes in 48h)**
```python
async def test_strike_2():
    # Day 1: First inbox error
    await simulate_bounce(inbox_1, '550 5.7.1')

    # Day 2: Second inbox error (within 48h)
    await simulate_bounce(inbox_2, '550 5.7.1')

    # Verify domain paused
    domain = await get_domain(domain_id)
    assert domain.domain_state == 'flagged'  # or 'paused'

    # Verify campaigns reassigned
    campaigns = await get_domain_campaigns(domain_id)
    assert len(campaigns) == 0  # All moved off domain

    # Verify bench domain rotated in
    bench = await get_active_bench_domain(workspace_id)
    assert bench is not None
```

**Scenario 3: Strike 3 (3 Inboxes in 48h)**
```python
async def test_strike_3():
    # Simulate 3 errors in 48h window
    await simulate_bounce(inbox_1, '550 5.7.1')
    await simulate_bounce(inbox_2, '550 5.7.1')
    await simulate_bounce(inbox_3, '550 5.7.1')

    # Verify domain killed
    domain = await get_domain(domain_id)
    assert domain.domain_state == 'dead'
    assert domain.is_active == False

    # Verify kill trigger created
    trigger = await get_latest_kill_trigger(domain_id)
    assert trigger.trigger_type == 'strike_3'
```

---

## Part 6: Migration Path

### Phase 1: Foundation (Weeks 1-2)
```
✅ Week 1: Critical Fixes
   - Fix dead domain sync bug
   - Backfill sender_account_count
   - Clean up orphaned records

✅ Week 2: Rolling Window
   - Create inbox_error_window table
   - Implement strike tracking functions
   - Add to sync worker
```

### Phase 2: Strike System (Weeks 3-5)
```
✅ Week 3: Strike 2 Logic
   - Domain pausing function
   - Campaign reassignment
   - Bench rotation

✅ Week 4: Strike 3 Logic
   - Domain kill workflow
   - Domain swap automation
   - Incubator tracking

✅ Week 5: Testing
   - End-to-end strike scenarios
   - Load testing
   - Rollback plan
```

### Phase 3: Bench Management (Weeks 6-8)
```
✅ Week 6: Database Schema
   - Add pool_tier to domains
   - Create rotation history table
   - Build bench views

✅ Week 7: Backend API
   - Bench domain listing
   - Manual rotation endpoints
   - Warmup automation

✅ Week 8: UI Development
   - Bench domains dashboard
   - Rotation controls
   - Health monitoring
```

---

## Conclusion

### What to Build First

**Immediate (This Sprint):**
1. ✅ Rolling window strike tracking table
2. ✅ Strike counting functions
3. ✅ Fix dead domain sync bug (from audit)

**Next Sprint:**
4. ✅ Strike 2 domain pausing
5. ✅ Basic bench domain rotation
6. ✅ Slack alerts for strikes

**Month 2:**
7. ✅ Full bench management UI
8. ✅ Automated domain procurement
9. ✅ Predictive health scoring

### Key Architectural Decisions

**Adopt from Gemini SOP:**
- ✅ 48-hour rolling window logic
- ✅ Graduated strike system (1→2→3)
- ✅ Domain-level rotation on Strike 2

**Keep from Charm:**
- ✅ Inbox-level granular rotation
- ✅ Differentiated bounce classification
- ✅ Comprehensive audit logging
- ✅ Tag-based flagging (not deletion)

**Hybrid Approach:**
- ✅ Instant kill for catastrophic errors (550 5.7.705)
- ✅ Graduated strikes for escalating issues (550 5.7.1)
- ✅ Both inbox-level AND domain-level rotation

### Success Metrics

**Measure these after implementation:**
1. **Time to Detection:** How long from first error to Strike 2?
2. **False Positive Rate:** How many domains falsely flagged?
3. **Domain Burn Rate:** Domains killed per month (should decrease)
4. **Bench Utilization:** How often are bench domains rotated in?
5. **Campaign Uptime:** % of campaigns with healthy inboxes

---

## Appendix: File References

### Database Migrations
- `migrations/018_health_rotation_schema.sql` - Kill triggers, rotation history
- `migrations/025_differentiated_bounce_columns.sql` - Bounce type tracking
- `migrations/026_warmup_tracking_schema.sql` - Warmup snapshots
- `migrations/036_campaign_burn_events.sql` - Campaign burn tracking

### Backend Logic
- `sync_modules/health_checks.py` - Threshold-based kill triggers
- `sync_modules/kill_processor.py` - Inbox flagging and rotation
- `sync_modules/sync_events.py` - SMTP error extraction
- `sync_modules/sync_warmup.py` - Warmup automation

### Documentation
- `docs/concepts/kill-triggers.md` - Kill trigger overview
- `docs/adr/adr-005-differentiated-bounce-thresholds.md` - Bounce classification ADR
- `docs/foam/health-monitoring.md` - Health monitoring system

### Frontend
- `charm-email-os/app/clients/[clientId]/page.tsx` - Client dashboard
- `charm-email-os/app/domains/page.tsx` - Domain management UI

---

**Document Version:** 1.0
**Last Updated:** 2026-02-23
**Author:** Database Integrity Audit Team
**Status:** Ready for Review & Implementation
