---
title: Gemini SOP ↔ Charm Email OS - Exact Feature Mapping
created: 2026-02-23
tags: [gemini-sop, mapping, implementation-status, kill-switch]
status: ready-for-implementation
---

# Gemini Kill Switch SOP ↔ Charm Email OS - Exact Feature Mapping

## Quick Status Summary

| Gemini SOP Rule | Charm Status | Implementation Gap | Priority |
|----------------|--------------|-------------------|----------|
| **Inbox Rule 1:** 1 spam bounce → pause inbox | ✅ **IMPLEMENTED** | None | N/A |
| **Domain Rule 1:** Bounce rate >2.5% (7d) → pause domain | ⚠️ **PARTIAL** | Missing domain pause action | **HIGH** |
| **Domain Rule 2:** Spam complaint >0.1% → pause domain | ❌ **NOT IMPLEMENTED** | No complaint rate tracking | **MEDIUM** |
| **Domain Rule 3:** Open rate <20% (3d) → pause domain | ❌ **NOT IMPLEMENTED** | No open rate domain threshold | **MEDIUM** |
| **Strike System:** 1-2-3 strikes in 48h window | ❌ **NOT IMPLEMENTED** | No rolling window logic | **CRITICAL** |
| **Bench Rotation:** Auto-rotate on Strike 2 | ❌ **NOT IMPLEMENTED** | No bench domain concept | **HIGH** |

---

## Part 1: Inbox-Level Guardrails (Auto-Pause)

### Gemini SOP Rule 1: "If an inbox receives 1 bounce classified as Spam/Block (550), pause the inbox immediately"

**Charm Implementation:**
```python
# File: sync_modules/health_checks.py (Lines 43-46)
'hard_blocked_24h': {
    'value': 1,  # ✅ MATCHES GEMINI: 1 bounce
    'severity': 'instant',
    'description': '1+ spam/policy rejections in 24h (reputation damage)'
}
```

**Exact Mapping:**
| Gemini Requirement | Charm Implementation | Status |
|-------------------|---------------------|---------|
| Detect 550 error codes | ✅ `extract_bounce_reason()` in `sync_events.py` | ✅ IMPLEMENTED |
| Classify as "Spam/Block" | ✅ `bounce_type='hard_blocked'` for 5.7.x codes | ✅ IMPLEMENTED |
| Pause inbox immediately | ✅ `inbox_state='dead'` + EmailBison tag | ✅ IMPLEMENTED |
| Threshold: 1 bounce | ✅ `KILL_THRESHOLD_HARD_BLOCKED_24H = 1` | ✅ IMPLEMENTED |

**Database Evidence:**
```sql
-- Current Charm workspace bounces
SELECT bounce_type, COUNT(*) FROM response_messages
WHERE workspace_id = 'b9abd34a-f16a-4b92-bda0-5af10f8c44bd'
GROUP BY bounce_type;

-- Results:
hard_blocked   | 5    -- These trigger instant inbox pause
hard_unknown   | 23   -- These need 3 to trigger
soft_full      | 1    -- These don't trigger
```

**Verdict:** ✅ **FULLY IMPLEMENTED** - Charm meets or exceeds this requirement.

---

## Part 2: Domain-Level Guardrails (Auto-Pause)

### Gemini SOP Rule 1: "If Domain Bounce Rate exceeds 2.5% over the last 7 days, pause all active campaigns for this domain"

**Charm Implementation:**
```python
# File: sync_modules/health_checks.py (Lines 64-68)
'bounce_rate_all_7d': {
    'value': 0.05,  # ⚠️ MISMATCH: 5% vs Gemini's 2.5%
    'min_sends': 50,
    'severity': 'instant',
    'description': 'Total bounce rate >5%'
}
```

**Exact Mapping:**
| Gemini Requirement | Charm Implementation | Gap Analysis |
|-------------------|---------------------|--------------|
| Track bounce rate over 7 days | ✅ `bounce_rate_all_7d` tracked | ✅ IMPLEMENTED |
| Threshold: 2.5% | ❌ Current: 5% (too lenient) | ⚠️ **NEEDS ADJUSTMENT** |
| Pause all campaigns on domain | ❌ Only flags inbox, doesn't pause domain campaigns | ❌ **MISSING** |
| Apply at domain level | ❌ Applied at inbox level only | ❌ **MISSING** |

**Current Code Behavior:**
```python
# What Charm DOES (health_checks.py):
if inbox.bounce_rate_all_7d > 0.05:  # 5% threshold
    await self.flag_inbox(inbox.id, 'bounce_rate_all_7d')
    # ❌ Does NOT pause domain campaigns

# What Gemini SOP REQUIRES:
if domain.bounce_rate_7d > 0.025:  # 2.5% threshold
    await self.pause_all_domain_campaigns(domain.id)  # ← MISSING
```

**Required Changes:**

1. **Lower threshold to 2.5%:**
```python
KILL_THRESHOLD_TOTAL_BOUNCE_RATE = float(os.getenv('KILL_THRESHOLD_TOTAL_BOUNCE_RATE', 0.025))  # Changed from 0.05
```

2. **Add domain-level bounce rate calculation:**
```sql
-- New query needed in health_checks.py
CREATE OR REPLACE FUNCTION get_domain_bounce_rate_7d(p_domain_id UUID)
RETURNS NUMERIC AS $$
    SELECT
        COALESCE(
            COUNT(*) FILTER (WHERE ce.bounce_type IS NOT NULL)::NUMERIC /
            NULLIF(COUNT(*)::NUMERIC, 0),
            0
        )
    FROM campaign_events ce
    JOIN sender_accounts sa ON sa.id = ce.sender_account_id
    WHERE sa.domain_id = p_domain_id
    AND ce.sent_at >= NOW() - INTERVAL '7 days'
$$ LANGUAGE SQL;
```

3. **Add domain pause function:**
```python
async def pause_domain_campaigns(self, domain_id: UUID, reason: str):
    """Pause all active campaigns using this domain."""
    # Remove domain inboxes from campaigns
    await self.db.execute("""
        DELETE FROM campaign_inboxes ci
        USING sender_accounts sa
        WHERE ci.sender_account_id = sa.id
        AND sa.domain_id = $1
    """, domain_id)

    # Mark domain as flagged
    await self.db.execute("""
        UPDATE domains
        SET domain_state = 'flagged',
            kill_reason = $2
        WHERE id = $1
    """, domain_id, reason)

    # Alert
    await self.alerter.notify_domain_paused(domain_id, reason)
```

**Verdict:** ⚠️ **PARTIALLY IMPLEMENTED** - Needs threshold adjustment + domain pause action.

---

### Gemini SOP Rule 2: "If Domain Spam Complaint Rate exceeds 0.1%, pause all active campaigns for this domain"

**Charm Implementation:**
```python
# File: sync_modules/health_checks.py (Lines 32-36)
'spam_complaint': {
    'value': 1,  # ⚠️ DIFFERENT APPROACH: 1 complaint vs 0.1% rate
    'severity': 'instant',
    'description': '1+ spam complaints = immediate death'
}
```

**Exact Mapping:**
| Gemini Requirement | Charm Implementation | Gap Analysis |
|-------------------|---------------------|--------------|
| Track spam complaints | ✅ Tracked in `campaign_events` | ✅ IMPLEMENTED |
| Calculate complaint RATE | ❌ Uses count (1+) not rate (0.1%) | ❌ **MISSING** |
| Apply at domain level | ❌ Applied at inbox level only | ❌ **MISSING** |
| Pause domain campaigns | ❌ Kills inbox, doesn't pause domain | ❌ **MISSING** |

**Current Behavior:**
```python
# Charm's approach (inbox-level, count-based):
if inbox.spam_complaints_24h >= 1:
    await self.kill_inbox(inbox.id)  # Instant kill

# Gemini SOP approach (domain-level, rate-based):
if domain.spam_complaint_rate > 0.001:  # 0.1%
    await self.pause_domain_campaigns(domain.id)
```

**Why the Difference?**
- **Charm's philosophy:** 1 spam complaint = instant kill (more aggressive)
- **Gemini's philosophy:** Use rate-based threshold (more forgiving for high-volume)

**Recommendation:** **KEEP CHARM'S APPROACH** but ADD domain-level tracking

**Hybrid Implementation:**
```python
# Add to DOMAIN_THRESHOLDS in health_checks.py
DOMAIN_THRESHOLDS = {
    'spam_complaint_rate': 0.001,  # 0.1% spam complaint rate
    'spam_complaint_count': 2,     # OR 2+ complaints on domain
    # ...
}

async def check_domain_spam_complaints(self, domain_id: UUID):
    """Check both rate AND count (belt-and-suspenders)."""
    stats = await self.db.fetchrow("""
        SELECT
            COUNT(*) FILTER (WHERE ce.spam_complaint = true) as complaint_count,
            COUNT(*) as total_sends,
            COUNT(*) FILTER (WHERE ce.spam_complaint = true)::NUMERIC /
                NULLIF(COUNT(*)::NUMERIC, 0) as complaint_rate
        FROM campaign_events ce
        JOIN sender_accounts sa ON sa.id = ce.sender_account_id
        WHERE sa.domain_id = $1
        AND ce.sent_at >= NOW() - INTERVAL '7 days'
    """, domain_id)

    # Trigger if EITHER threshold exceeded
    if stats['complaint_count'] >= 2 OR stats['complaint_rate'] > 0.001:
        await self.pause_domain_campaigns(domain_id, 'spam_complaints')
```

**Verdict:** ⚠️ **DIFFERENT APPROACH** - Charm is more aggressive (instant kill on 1 complaint), Gemini uses rate-based threshold.

---

### Gemini SOP Rule 3: "If Open Rate drops below 20% over a continuous 3-day period, pause all active campaigns for this domain"

**Charm Implementation:**
```python
# ❌ NOT FOUND in health_checks.py
# No open rate thresholds at domain level
```

**Exact Mapping:**
| Gemini Requirement | Charm Implementation | Gap Analysis |
|-------------------|---------------------|--------------|
| Track open rate | ✅ `campaign_events.opened_at` exists | ✅ DATA AVAILABLE |
| Calculate domain-level open rate | ❌ Not implemented | ❌ **MISSING** |
| 3-day continuous window | ❌ No windowed tracking | ❌ **MISSING** |
| Threshold: <20% | ❌ No threshold defined | ❌ **MISSING** |
| Pause domain campaigns | ❌ No action defined | ❌ **MISSING** |

**Why This Matters (from Gemini SOP):**
> "This catches stealth spam-folder filtering where bounce codes are not generated"

**Implementation Needed:**
```python
# Add to DOMAIN_THRESHOLDS
DOMAIN_THRESHOLDS = {
    'low_open_rate': 0.20,  # 20% minimum open rate
    'low_open_rate_days': 3,  # Continuous 3-day period
    # ...
}

async def check_domain_open_rate(self, domain_id: UUID):
    """Check if open rate dropped below 20% for 3 consecutive days."""
    # Get daily open rates for last 3 days
    daily_rates = await self.db.fetch("""
        WITH daily_stats AS (
            SELECT
                DATE(ce.sent_at) as send_date,
                COUNT(*) FILTER (WHERE ce.opened_at IS NOT NULL)::NUMERIC /
                    NULLIF(COUNT(*)::NUMERIC, 0) as open_rate
            FROM campaign_events ce
            JOIN sender_accounts sa ON sa.id = ce.sender_account_id
            WHERE sa.domain_id = $1
            AND ce.sent_at >= NOW() - INTERVAL '3 days'
            GROUP BY DATE(ce.sent_at)
            ORDER BY send_date DESC
            LIMIT 3
        )
        SELECT * FROM daily_stats
    """, domain_id)

    # Check if ALL 3 days are below 20%
    if len(daily_rates) == 3:
        if all(row['open_rate'] < 0.20 for row in daily_rates):
            await self.pause_domain_campaigns(
                domain_id,
                f"Low open rate (<20%) for 3 consecutive days"
            )
```

**Verdict:** ❌ **NOT IMPLEMENTED** - Critical for detecting stealth spam filtering.

---

## Part 3: Strike System (1-2-3 within 48 hours)

### Gemini SOP Strike System

**Strike 1:** 1 inbox flagged → Pause that inbox only
**Strike 2:** 2 inboxes flagged within 48h → Pause entire domain, rotate bench
**Strike 3:** 3 inboxes flagged within 48h → Kill domain, swap new domain

**Charm Implementation:**
```python
# File: sync_modules/health_checks.py (Lines 78-84)
DOMAIN_THRESHOLDS = {
    'unhealthy_warning': 0.15,    # 15% unhealthy = flag
    'unhealthy_pause': 0.30,      # 30% unhealthy = pause
    'dead_inbox_flagged': 1,      # 1 dead inbox = flag domain
    'dead_inbox_dead': 2,         # 2+ dead inboxes = domain dead
}
```

**Exact Mapping:**

| Strike Level | Gemini SOP | Charm Implementation | Gap |
|-------------|-----------|---------------------|-----|
| **Strike 1** | Pause inbox | ✅ Marks `inbox_state='dead'` | ✅ MATCHES |
| **Strike 2** | Pause domain + rotate bench (within 48h) | ⚠️ Marks domain flagged at 30% unhealthy | ❌ **NO 48H WINDOW** |
| **Strike 3** | Kill domain + swap (within 48h) | ⚠️ Marks `domain_state='dead'` at 2+ dead inboxes | ❌ **NO TIME WINDOW** |

**Critical Difference:**

**Gemini SOP:**
```
Timeline-based:
Day 1, 9am: Inbox A gets 550 5.7.1 → Strike 1 (pause inbox A)
Day 2, 2pm: Inbox B gets 550 5.7.1 → Strike 2 (within 48h! Pause domain, rotate bench)
Day 3, 10am: Inbox C gets 550 5.7.1 → Strike 3 (within 48h! Kill domain)
```

**Charm Current:**
```
Count-based (no time window):
Anytime: Inbox A flagged → Domain gets 1 dead inbox
Anytime: Inbox B flagged → Domain gets 2 dead inboxes → domain_state='dead'
❌ No concept of "within 48 hours"
```

**Missing Implementation:**

1. **Rolling window table** (from earlier analysis):
```sql
CREATE TABLE inbox_error_window (
    id UUID PRIMARY KEY,
    inbox_id UUID NOT NULL,
    domain_id UUID NOT NULL,
    error_code VARCHAR(20),
    detected_at TIMESTAMPTZ NOT NULL,
    window_expires_at TIMESTAMPTZ  -- detected_at + 48 hours
);
```

2. **Strike detection logic:**
```python
async def check_domain_strikes(self, domain_id: UUID):
    """Check for Strike 2 or Strike 3 within 48h window."""
    # Count unique inboxes with errors in 48h window
    strike_count = await self.db.fetchval("""
        SELECT COUNT(DISTINCT inbox_id)
        FROM inbox_error_window
        WHERE domain_id = $1
        AND detected_at >= NOW() - INTERVAL '48 hours'
    """, domain_id)

    if strike_count == 2:
        # STRIKE 2
        await self.execute_strike_2(domain_id)
    elif strike_count >= 3:
        # STRIKE 3
        await self.execute_strike_3(domain_id)

async def execute_strike_2(self, domain_id: UUID):
    """Strike 2: Pause domain, rotate bench."""
    await self.pause_domain_campaigns(domain_id)
    await self.rotate_bench_domain(domain_id)
    await self.enable_domain_warmup(domain_id, days=14)
    await self.alerter.notify_strike_2(domain_id)

async def execute_strike_3(self, domain_id: UUID):
    """Strike 3: Kill domain, execute swap."""
    await self.kill_domain(domain_id)
    await self.execute_domain_swap(domain_id)
    await self.alerter.notify_strike_3(domain_id)
```

**Verdict:** ❌ **NOT IMPLEMENTED** - Charm lacks time-windowed strike detection.

---

## Part 4: Manual Review Protocol

### Gemini SOP: "Campaign managers must review the paused inbox logs every morning"

**Charm Implementation:**
```python
# Slack alerts exist for individual inbox kills
# File: sync_modules/slack_alerter.py
await self.alerter.notify_inbox_killed(inbox_id, trigger_type)
```

**What Gemini SOP Requires:**
> "If they see two inboxes from the same domain paused in the same morning report, they manually execute the Strike 2 (Bench) protocol"

**Charm's Current Morning Report:**
- ❌ No consolidated daily report
- ❌ No domain-level grouping of killed inboxes
- ❌ No Strike 2 manual escalation workflow

**Implementation Needed:**
```python
# New function in slack_alerter.py
async def send_daily_kill_summary(self):
    """Send morning summary of killed inboxes, grouped by domain."""
    kills_24h = await self.db.fetch("""
        SELECT
            d.domain_name,
            COUNT(DISTINCT sa.id) as killed_inbox_count,
            ARRAY_AGG(sa.email_address) as killed_emails,
            MAX(kq.created_at) as latest_kill
        FROM kill_queue kq
        JOIN sender_accounts sa ON sa.id = kq.inbox_id
        JOIN domains d ON d.id = sa.domain_id
        WHERE kq.created_at >= NOW() - INTERVAL '24 hours'
        GROUP BY d.id, d.domain_name
        HAVING COUNT(DISTINCT sa.id) >= 2  -- Flag domains with 2+ kills
        ORDER BY killed_inbox_count DESC
    """)

    if kills_24h:
        message = "⚠️ **MORNING KILL REPORT** - Domains with 2+ Killed Inboxes:\n\n"
        for row in kills_24h:
            message += f"🚨 **{row['domain_name']}**: {row['killed_inbox_count']} inboxes killed\n"
            message += f"   Emails: {', '.join(row['killed_emails'])}\n"
            message += f"   ⚠️ **ACTION REQUIRED:** Review for Strike 2 protocol\n\n"

        await self.send_alert(message, channel='#campaign-ops')
```

**Verdict:** ⚠️ **PARTIAL** - Charm has individual alerts, needs daily summary + domain grouping.

---

## Part 5: Implementation Priority Matrix

### CRITICAL (Must Implement This Week)

| Priority | Gemini SOP Feature | Current Gap | Estimated Effort |
|----------|-------------------|-------------|------------------|
| 🔴 **P0** | 48-hour rolling window strike tracking | No time windows | 2-3 days |
| 🔴 **P0** | Domain pause on Strike 2 | Only flags, doesn't pause campaigns | 1-2 days |
| 🔴 **P0** | Domain bounce rate → pause campaigns | Tracks rate but doesn't pause | 1 day |

### HIGH (Implement Next Sprint)

| Priority | Gemini SOP Feature | Current Gap | Estimated Effort |
|----------|-------------------|-------------|------------------|
| 🟡 **P1** | Domain open rate monitoring (3-day window) | Not implemented | 2-3 days |
| 🟡 **P1** | Bench domain rotation on Strike 2 | No bench concept | 3-5 days |
| 🟡 **P1** | Daily kill summary report (grouped by domain) | No daily report | 1 day |

### MEDIUM (Refinements)

| Priority | Gemini SOP Feature | Current Gap | Estimated Effort |
|----------|-------------------|-------------|------------------|
| 🟢 **P2** | Domain spam complaint rate (0.1%) | Uses count not rate | 1 day |
| 🟢 **P2** | Adjust bounce rate threshold (2.5% vs 5%) | Config change | 1 hour |
| 🟢 **P2** | Manual Strike 2 escalation workflow | Not defined | 2 days |

---

## Part 6: Exact SQL Implementation Plan

### Step 1: Create Rolling Window Table (Day 1)

```sql
-- File: migrations/038_rolling_window_strike_tracking.sql

CREATE TABLE inbox_error_window (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    inbox_id UUID NOT NULL REFERENCES sender_accounts(id) ON DELETE CASCADE,
    domain_id UUID NOT NULL REFERENCES domains(id) ON DELETE CASCADE,
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    error_code VARCHAR(20) NOT NULL,  -- e.g., "550 5.7.1"
    error_type VARCHAR(50),  -- 'hard_blocked', 'spam_complaint', etc.
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

-- Function: Count strikes in rolling window
CREATE OR REPLACE FUNCTION count_domain_strikes(
    p_domain_id UUID,
    p_window_hours INTEGER DEFAULT 48
) RETURNS INTEGER AS $$
    SELECT COUNT(DISTINCT inbox_id)
    FROM inbox_error_window
    WHERE domain_id = p_domain_id
    AND detected_at >= NOW() - (p_window_hours || ' hours')::INTERVAL
$$ LANGUAGE SQL STABLE;

-- Function: Get strike details
CREATE OR REPLACE FUNCTION get_domain_strike_details(
    p_domain_id UUID,
    p_window_hours INTEGER DEFAULT 48
) RETURNS TABLE(
    inbox_id UUID,
    email_address VARCHAR,
    error_count BIGINT,
    first_error TIMESTAMPTZ,
    latest_error TIMESTAMPTZ
) AS $$
    SELECT
        iew.inbox_id,
        sa.email_address,
        COUNT(*) as error_count,
        MIN(iew.detected_at) as first_error,
        MAX(iew.detected_at) as latest_error
    FROM inbox_error_window iew
    JOIN sender_accounts sa ON sa.id = iew.inbox_id
    WHERE iew.domain_id = p_domain_id
    AND iew.detected_at >= NOW() - (p_window_hours || ' hours')::INTERVAL
    GROUP BY iew.inbox_id, sa.email_address
    ORDER BY first_error ASC
$$ LANGUAGE SQL STABLE;
```

### Step 2: Add Domain Health Functions (Day 2)

```sql
-- Function: Get domain bounce rate (7-day)
CREATE OR REPLACE FUNCTION get_domain_bounce_rate_7d(p_domain_id UUID)
RETURNS NUMERIC AS $$
    SELECT
        COALESCE(
            COUNT(*) FILTER (WHERE ce.bounce_type IS NOT NULL)::NUMERIC /
            NULLIF(COUNT(*)::NUMERIC, 0),
            0
        )
    FROM campaign_events ce
    JOIN sender_accounts sa ON sa.id = ce.sender_account_id
    WHERE sa.domain_id = p_domain_id
    AND ce.sent_at >= NOW() - INTERVAL '7 days'
    AND ce.sent_at IS NOT NULL
$$ LANGUAGE SQL STABLE;

-- Function: Get domain spam complaint rate (7-day)
CREATE OR REPLACE FUNCTION get_domain_spam_rate_7d(p_domain_id UUID)
RETURNS NUMERIC AS $$
    SELECT
        COALESCE(
            COUNT(*) FILTER (WHERE ce.spam_complaint = true)::NUMERIC /
            NULLIF(COUNT(*)::NUMERIC, 0),
            0
        )
    FROM campaign_events ce
    JOIN sender_accounts sa ON sa.id = ce.sender_account_id
    WHERE sa.domain_id = p_domain_id
    AND ce.sent_at >= NOW() - INTERVAL '7 days'
$$ LANGUAGE SQL STABLE;

-- Function: Get domain open rate (3-day)
CREATE OR REPLACE FUNCTION get_domain_open_rate_3d(p_domain_id UUID)
RETURNS TABLE(
    day_date DATE,
    open_rate NUMERIC,
    total_sends BIGINT
) AS $$
    SELECT
        DATE(ce.sent_at) as day_date,
        COUNT(*) FILTER (WHERE ce.opened_at IS NOT NULL)::NUMERIC /
            NULLIF(COUNT(*)::NUMERIC, 0) as open_rate,
        COUNT(*) as total_sends
    FROM campaign_events ce
    JOIN sender_accounts sa ON sa.id = ce.sender_account_id
    WHERE sa.domain_id = p_domain_id
    AND ce.sent_at >= NOW() - INTERVAL '3 days'
    GROUP BY DATE(ce.sent_at)
    ORDER BY day_date DESC
$$ LANGUAGE SQL STABLE;
```

### Step 3: Modify sync_events.py to Record Errors (Day 3)

```python
# File: sync_modules/sync_events.py
# Add after extract_bounce_reason() function

async def record_error_in_window(
    self,
    inbox_id: UUID,
    domain_id: UUID,
    workspace_id: UUID,
    error_code: str,
    error_type: str,
    error_message: str = None,
    window_hours: int = 48
):
    """Record error in rolling window for strike tracking."""
    await self.db.execute("""
        INSERT INTO inbox_error_window
        (inbox_id, domain_id, workspace_id, error_code, error_type, error_message, window_expires_at)
        VALUES ($1, $2, $3, $4, $5, $6, NOW() + ($7 || ' hours')::INTERVAL)
    """, inbox_id, domain_id, workspace_id, error_code, error_type, error_message, window_hours)

# Modify bounce processing to record in window
async def process_bounce_event(self, event_data):
    # ... existing bounce detection code ...

    if bounce_type in ['hard_blocked', 'spam_complaint']:
        # Record in rolling window for strike tracking
        await self.record_error_in_window(
            inbox_id=event['sender_account_id'],
            domain_id=event['domain_id'],
            workspace_id=event['workspace_id'],
            error_code=smtp_code,
            error_type=bounce_type,
            error_message=bounce_reason
        )
```

### Step 4: Add Domain-Level Health Checks (Day 4-5)

```python
# File: sync_modules/health_checks.py
# Add new method to HealthCheckModule class

async def check_domain_health_thresholds(self):
    """Check domain-level thresholds per Gemini SOP."""
    domains = await self.db.fetch("""
        SELECT DISTINCT d.id, d.domain_name, d.workspace_id
        FROM domains d
        JOIN sender_accounts sa ON sa.domain_id = d.id
        WHERE d.is_active = true
        AND d.domain_state NOT IN ('dead', 'retired')
    """)

    for domain in domains:
        # Check 1: Bounce rate >2.5% (7-day)
        bounce_rate = await self.db.fetchval(
            "SELECT get_domain_bounce_rate_7d($1)",
            domain['id']
        )
        if bounce_rate and bounce_rate > 0.025:  # 2.5%
            await self.pause_domain_campaigns(
                domain['id'],
                f"Bounce rate {bounce_rate*100:.2f}% exceeds 2.5% threshold"
            )

        # Check 2: Spam complaint rate >0.1% (7-day)
        spam_rate = await self.db.fetchval(
            "SELECT get_domain_spam_rate_7d($1)",
            domain['id']
        )
        if spam_rate and spam_rate > 0.001:  # 0.1%
            await self.pause_domain_campaigns(
                domain['id'],
                f"Spam complaint rate {spam_rate*100:.2f}% exceeds 0.1% threshold"
            )

        # Check 3: Open rate <20% for 3 consecutive days
        daily_rates = await self.db.fetch(
            "SELECT * FROM get_domain_open_rate_3d($1)",
            domain['id']
        )
        if len(daily_rates) == 3:
            if all(row['open_rate'] and row['open_rate'] < 0.20 for row in daily_rates):
                await self.pause_domain_campaigns(
                    domain['id'],
                    "Open rate below 20% for 3 consecutive days (stealth spam filtering)"
                )

        # Check 4: Strike system (rolling 48h window)
        strike_count = await self.db.fetchval(
            "SELECT count_domain_strikes($1, 48)",
            domain['id']
        )
        if strike_count == 2:
            await self.execute_strike_2(domain['id'])
        elif strike_count >= 3:
            await self.execute_strike_3(domain['id'])

async def pause_domain_campaigns(self, domain_id: UUID, reason: str):
    """Pause all active campaigns on this domain."""
    # Remove domain inboxes from campaigns
    removed_count = await self.db.fetchval("""
        WITH removed AS (
            DELETE FROM campaign_inboxes ci
            USING sender_accounts sa
            WHERE ci.sender_account_id = sa.id
            AND sa.domain_id = $1
            RETURNING ci.id
        )
        SELECT COUNT(*) FROM removed
    """, domain_id)

    # Mark domain as flagged
    await self.db.execute("""
        UPDATE domains
        SET domain_state = 'flagged',
            kill_reason = $2,
            killed_at = NOW()
        WHERE id = $1
    """, domain_id, reason)

    # Alert
    await self.alerter.notify_domain_paused(domain_id, reason, removed_count)

    # Log
    await self.audit_logger.log_domain_pause(domain_id, reason, removed_count)
```

### Step 5: Add Daily Summary Report (Day 6)

```python
# File: sync_modules/slack_alerter.py
# Add new method

async def send_daily_kill_summary(self):
    """Send morning summary of kills grouped by domain (Gemini SOP requirement)."""
    kills_24h = await self.db.fetch("""
        SELECT
            d.id as domain_id,
            d.domain_name,
            d.workspace_id,
            w.workspace_name,
            COUNT(DISTINCT sa.id) as killed_inbox_count,
            ARRAY_AGG(sa.email_address ORDER BY kq.created_at) as killed_emails,
            MIN(kq.created_at) as first_kill,
            MAX(kq.created_at) as latest_kill,
            count_domain_strikes(d.id, 48) as current_strikes
        FROM kill_queue kq
        JOIN sender_accounts sa ON sa.id = kq.inbox_id
        JOIN domains d ON d.id = sa.domain_id
        JOIN workspaces w ON w.id = d.workspace_id
        WHERE kq.created_at >= NOW() - INTERVAL '24 hours'
        AND kq.status IN ('pending', 'completed')
        GROUP BY d.id, d.domain_name, d.workspace_id, w.workspace_name
        ORDER BY killed_inbox_count DESC, latest_kill DESC
    """)

    if not kills_24h:
        # No kills - all good!
        message = "✅ **Morning Kill Report** - No inboxes killed in last 24h. All systems healthy!"
        await self.send_alert(message, channel='#campaign-ops')
        return

    # Build report
    message = "📊 **MORNING KILL REPORT** - Last 24 Hours\n\n"

    critical_domains = []
    warning_domains = []

    for row in kills_24h:
        if row['current_strikes'] >= 2:
            critical_domains.append(row)
        else:
            warning_domains.append(row)

    # Critical: Domains with 2+ strikes
    if critical_domains:
        message += "🚨 **CRITICAL - DOMAINS AT STRIKE 2+** (Manual Review Required):\n\n"
        for row in critical_domains:
            message += f"**{row['domain_name']}** ({row['workspace_name']})\n"
            message += f"  • Strikes: {row['current_strikes']} (within 48h window)\n"
            message += f"  • Killed in last 24h: {row['killed_inbox_count']} inboxes\n"
            message += f"  • Emails: {', '.join(row['killed_emails'][:5])}"
            if len(row['killed_emails']) > 5:
                message += f" (+{len(row['killed_emails']) - 5} more)"
            message += "\n"
            message += f"  • ⚠️ **ACTION:** Execute Strike {row['current_strikes']} protocol\n\n"

    # Warning: Domains with 1 strike
    if warning_domains:
        message += "⚠️ **WARNING - DOMAINS AT STRIKE 1**:\n\n"
        for row in warning_domains:
            message += f"**{row['domain_name']}** ({row['workspace_name']})\n"
            message += f"  • Killed: {row['killed_inbox_count']} inboxes\n"
            message += f"  • Watch for additional kills within 48h\n\n"

    await self.send_alert(message, channel='#campaign-ops')
```

---

## Part 7: Configuration Changes Required

### Environment Variables to Update

```bash
# File: .env or .env.local

# Adjust bounce rate threshold to match Gemini SOP
KILL_THRESHOLD_TOTAL_BOUNCE_RATE=0.025  # Changed from 0.05 (5%) to 0.025 (2.5%)

# Add new domain-level thresholds
DOMAIN_SPAM_COMPLAINT_RATE=0.001  # 0.1% spam complaint rate
DOMAIN_LOW_OPEN_RATE=0.20  # 20% minimum open rate
DOMAIN_LOW_OPEN_RATE_DAYS=3  # Continuous 3-day period

# Strike system windows
STRIKE_WINDOW_HOURS=48  # 48-hour rolling window for strikes
```

### Database Configuration

```python
# File: sync_modules/health_checks.py
# Update DOMAIN_THRESHOLDS

DOMAIN_THRESHOLDS = {
    # Gemini SOP: Bounce rate >2.5% (7d)
    'bounce_rate_7d': 0.025,

    # Gemini SOP: Spam complaint rate >0.1%
    'spam_complaint_rate': 0.001,

    # Gemini SOP: Open rate <20% for 3 days
    'low_open_rate': 0.20,
    'low_open_rate_days': 3,

    # Existing thresholds
    'unhealthy_warning': 0.15,
    'unhealthy_pause': 0.30,
    'dead_inbox_flagged': 1,
    'dead_inbox_dead': 2,
}
```

---

## Part 8: Testing Plan

### Test Scenario 1: Inbox Auto-Pause (Gemini Rule 1)

```python
async def test_inbox_auto_pause_on_spam_bounce():
    """Verify inbox pauses on 1 spam bounce (550 5.7.1)."""
    # Simulate bounce
    await simulate_bounce(inbox_id, error_code='550 5.7.1')

    # Verify inbox paused
    inbox = await db.fetchrow("SELECT * FROM sender_accounts WHERE id = $1", inbox_id)
    assert inbox['inbox_state'] == 'dead', "Inbox should be marked dead"
    assert 'flagged_hard_blocked' in inbox['tags'], "Should be tagged"

    # Verify domain NOT paused (Strike 1 only)
    domain = await db.fetchrow("SELECT * FROM domains WHERE id = $1", domain_id)
    assert domain['domain_state'] == 'live', "Domain should still be live"
```

### Test Scenario 2: Domain Pause on Bounce Rate (Gemini Rule 1)

```python
async def test_domain_pause_on_high_bounce_rate():
    """Verify domain pauses when bounce rate exceeds 2.5% over 7 days."""
    # Send 100 emails from domain over 7 days
    for i in range(100):
        await simulate_send(domain_id)

    # Simulate 3 bounces (3% bounce rate)
    for i in range(3):
        await simulate_bounce(domain_id)

    # Run health checks
    await health_checker.check_domain_health_thresholds()

    # Verify domain paused
    domain = await db.fetchrow("SELECT * FROM domains WHERE id = $1", domain_id)
    assert domain['domain_state'] == 'flagged', "Domain should be flagged"

    # Verify campaigns removed
    campaign_count = await db.fetchval("""
        SELECT COUNT(*) FROM campaign_inboxes ci
        JOIN sender_accounts sa ON sa.id = ci.sender_account_id
        WHERE sa.domain_id = $1
    """, domain_id)
    assert campaign_count == 0, "All campaigns should be removed"
```

### Test Scenario 3: Strike 2 (Gemini 48h Window)

```python
async def test_strike_2_within_48h_window():
    """Verify Strike 2 triggers when 2 inboxes flagged within 48h."""
    # Day 1, 9am: First inbox error
    await simulate_bounce(inbox_1, error_code='550 5.7.1')

    # Day 2, 2pm: Second inbox error (within 48h)
    await advance_time(hours=29)  # 29 hours later
    await simulate_bounce(inbox_2, error_code='550 5.7.1')

    # Check strikes
    strike_count = await db.fetchval(
        "SELECT count_domain_strikes($1, 48)",
        domain_id
    )
    assert strike_count == 2, "Should have 2 strikes"

    # Run health check
    await health_checker.check_domain_health_thresholds()

    # Verify Strike 2 executed
    domain = await db.fetchrow("SELECT * FROM domains WHERE id = $1", domain_id)
    assert domain['domain_state'] == 'flagged', "Domain should be paused (Strike 2)"

    # Verify bench rotation attempted
    # (requires bench domain system implementation)
```

### Test Scenario 4: Low Open Rate (Gemini Rule 3)

```python
async def test_domain_pause_on_low_open_rate():
    """Verify domain pauses when open rate <20% for 3 consecutive days."""
    # Day 1: Send 100, 10 opens (10% open rate)
    await simulate_day_activity(domain_id, sends=100, opens=10)

    # Day 2: Send 100, 15 opens (15% open rate)
    await simulate_day_activity(domain_id, sends=100, opens=15)

    # Day 3: Send 100, 18 opens (18% open rate)
    await simulate_day_activity(domain_id, sends=100, opens=18)

    # Run health check
    await health_checker.check_domain_health_thresholds()

    # Verify domain paused
    domain = await db.fetchrow("SELECT * FROM domains WHERE id = $1", domain_id)
    assert domain['domain_state'] == 'flagged', "Domain should be paused (stealth spam filtering)"
    assert 'open rate' in domain['kill_reason'].lower(), "Kill reason should mention open rate"
```

---

## Part 9: Rollout Plan

### Week 1: Foundation (Database + Core Logic)
- **Day 1-2:** Create rolling window table + functions
- **Day 3:** Modify sync_events.py to record errors
- **Day 4-5:** Add domain health check functions
- **Deploy:** Friday evening (low-traffic period)

### Week 2: Testing + Monitoring
- **Day 1-2:** Run tests against staging environment
- **Day 3:** Deploy to production with **monitoring-only mode**
  - Log what WOULD happen, don't actually pause domains yet
- **Day 4-5:** Review logs, tune thresholds

### Week 3: Gradual Rollout
- **Day 1:** Enable inbox-level auto-pause (already working, verify)
- **Day 2:** Enable domain bounce rate pausing (Gemini Rule 1)
- **Day 3:** Enable Strike 2 detection (48h window)
- **Day 4:** Enable low open rate detection (Gemini Rule 3)
- **Day 5:** Enable spam complaint rate (Gemini Rule 2)

### Week 4: Full Production + Daily Reports
- **Day 1:** Enable daily morning kill summary
- **Day 2-5:** Monitor, tune, adjust based on feedback

---

## Summary: Key Takeaways

### ✅ What Charm Already Has (Well Implemented)
1. **Inbox-level auto-pause** - Matches Gemini SOP perfectly
2. **SMTP error code tracking** - More sophisticated than SOP requires
3. **Differentiated bounce classification** - hard_blocked vs hard_unknown
4. **Comprehensive audit logging** - kill_queue, kill_triggers, campaign_burn_events

### ❌ Critical Gaps (Must Build)
1. **48-hour rolling window** - Strike system requires time-based detection
2. **Domain-level pause action** - Currently only flags, doesn't remove campaigns
3. **Open rate monitoring** - Critical for detecting stealth spam filtering
4. **Daily summary report** - Manual review protocol requires this

### ⚠️ Configuration Adjustments
1. Lower bounce rate threshold: 5% → 2.5%
2. Add spam complaint rate threshold: 0.1%
3. Add open rate threshold: 20% (3-day window)

### 📅 Timeline: 3-4 Weeks
- Week 1: Database foundation
- Week 2: Testing and monitoring
- Week 3: Gradual rollout
- Week 4: Full production

**Total Estimated Effort:** 15-20 development days across 4 weeks

---

**Document Status:** Ready for Implementation
**Last Updated:** 2026-02-23
**Next Action:** Review with team, get approval for Week 1 sprint
