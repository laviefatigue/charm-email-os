# Kill Trigger System - Executive Dashboard Guide

**Purpose:** Understanding what the Kill Velocity and Kill Breakdown charts show on the Executive Dashboard

> **2026-05-04 — Rule rewritten.** All count-based 24h triggers (`hard_blocked_24h ≥ N`, `hard_unknown_24h ≥ N`, `hard_bounces_24h ≥ N`) and 7d rate triggers were replaced by a **single ESP-agnostic lifetime-rate rule**. Dashboard charts will now show kills attributed to `hard_bounce_rate_lifetime` (and `spam_complaint`) only. Historical kills with the old trigger types remain in the data for trend continuity. See [docs/concepts/kill-triggers.md](../concepts/kill-triggers.md) and [adr-010-lifetime-rate-kill-rule-2026-05-04](../adr/adr-010-lifetime-rate-kill-rule-2026-05-04.md).

---

## Executive Summary

The Executive Dashboard tracks **system-initiated inbox deaths due to bad sending behavior**, not manual deactivations. When you see "Kill Velocity" or "Kill Breakdown," you're seeing inboxes that were automatically flagged because they:

- Received spam complaints
- Got blocked by ESPs (Gmail/Microsoft)
- Hit bad email addresses
- Bounced during warmup

**Manual deactivations** (domain shutdowns, subscription cancellations) are **excluded** from these charts - they're operational decisions, not quality issues.

---

## What Gets Counted as a "Kill"?

### System Kills (Shown on Dashboard) ✅

These are **automated flags** triggered by the health monitoring system. **Post-2026-05-04**, two trigger types fire under the new lifetime-rate rule:

| Trigger Type | Threshold | What It Means | Why It Matters |
|--------------|-----------|---------------|----------------|
| `spam_complaint` | ≥1 complaint (lifetime) | User reported spam (phrase-match on lead reply) | **Instant death** - kills sender reputation |
| `hard_bounce_rate_lifetime` | hard bounces ÷ lifetime sends > **5%** (≥20 sends required) | Lifetime hard-bounce rate exceeds Postmaster Tools "high" threshold | **Sustained reputation / list-quality issue** - inbox is consistently bouncing too much |

**Pre-2026-05-04 (historical only — still visible in older kill data):**

| Trigger Type | (Removed) | Reason for removal |
|--------------|-----------|--------------------|
| `hard_blocked_24h` | Was ≥1 (Gmail) / ≥2 (MS) | Replaced — count rules over 24h windows produced false positives via rolling-counter inflation |
| `hard_unknown_24h` | Was ≥1 (Gmail) / ≥3 (MS) | Same |
| `hard_bounces_24h` | Was ≥1 (Gmail) / ≥2 (MS) | Same |
| `hard_bounce_rate_7d` | Was > 2% with 100+ sends | Replaced by lifetime rate (more stable, no window math) |
| `bounce_rate_all_7d` | Was > 5% (incl. soft bounces) | Removed — soft bounces are mailbox-full / temp issues, not reputation signal |
| `fresh_inbox_blocked` / `fresh_inbox_unknown` | (already removed 2026-03-18) | Were duplicates of `hard_blocked_24h` / `hard_unknown_24h` |
| `disconnected_timeout` | (removed 2026-04-30 by ADR-009) | Connection state is now monitoring-only, not a kill trigger |

### Manual Deactivations (NOT Shown) ❌

These are **business/operational decisions**:
- Domain deactivated
- HyperTide subscription cancelled
- Manual inbox shutdown
- Infrastructure changes

**Why excluded?** These aren't quality issues - they're strategic decisions. Including them would make the Kill Velocity chart useless for identifying send quality problems.

---

## The Kill Queue Workflow

When an inbox triggers a kill threshold, here's what happens (post-2026-05-04 rate rule):

```
1. DETECT (Every 15 min)
   Health check computes: hard_bounces_lifetime / emails_sent_all_time
   If > 5% AND emails_sent_all_time >= 20: trigger fires
   ↓

2. QUEUE
   Insert into kill_queue table
   Status: 'pending'
   trigger_type: 'hard_bounce_rate_lifetime' or 'spam_complaint'
   trigger_value: actual rate (e.g., 0.0673 = 6.73%) or complaint count
   ↓

3. TAG (EmailBison)
   Apply tag: "flagged_hard_bounce_rate_lifetime" or "flagged_spam_complaint"
   Inbox remains in EmailBison (NOT deleted)
   ↓

4. FLAG (Local DB)
   inbox_state = 'dead'
   killed_at = NOW()
   kill_trigger = 'hard_bounce_rate_lifetime'
   ↓

5. DASHBOARD
   Shows up in Kill Velocity chart
   Categorized in Kill Breakdown pie chart
```

**Key Point:** Inboxes are **tagged, not deleted**. They remain in EmailBison with a tag explaining WHY they were flagged. This allows manual review and pattern analysis.

---

## Reading the Dashboard Charts

### Kill Velocity Chart

**What it shows:** Weekly inbox deaths due to bad sending over the entire client history.

**What it means:**
- **Spike in deaths:** List quality issue or campaign problem that week
- **Steady deaths:** Ongoing systematic issue (bad data, aggressive sending)
- **Zero deaths:** Clean sending behavior ✅

**What to look for:**
- Sudden spikes (investigate what campaign/list was used)
- Increasing trend (systematic problem getting worse)
- High baseline (overall send quality issues)

### Kill Breakdown Pie Chart

**What it shows:** Distribution of kill triggers over the last 30 days.

**How to interpret (post-2026-05-04):**

| Dominant Trigger | Root Cause | Action Needed |
|------------------|------------|---------------|
| `spam_complaint` | Recipients actively reporting spam (phrase-match in lead reply) | **Messaging problem** - emails are spammy or irrelevant |
| `hard_bounce_rate_lifetime` | Sustained > 5% lifetime hard-bounce rate | **List quality + reputation** - bad addresses and/or ESP rejection over the inbox's life |

**Older kills (pre-2026-05-04 in historical data only):**

| Trigger | Interpretation today |
|---------|----------------------|
| `hard_blocked_24h`, `hard_unknown_24h`, `hard_bounces_24h` | Old count-based rules; many were false positives from counter inflation. 307 such kills were resurrected on 2026-05-04. |
| `hard_bounce_rate_7d`, `bounce_rate_all_7d` | Old windowed rate rules; replaced by lifetime rate. |
| `disconnected_timeout` | Old connection-based kill; removed by ADR-009. ~1,200 fleet-wide zombies attributed to it. |

---

## Kill Thresholds (post-2026-05-04)

The system uses **two thresholds**:

### High Urgency: Reputation Damage

**`spam_complaint`** - Threshold: `complaints_lifetime ≥ 1`
- User reported as spam (phrase-match on lead reply)
- **Instant death, no exceptions**
- Indicates messaging is perceived as spam
- Coverage caveat: phrase-match on lead replies only — no JMRP / Postmaster Tools

### Sustained: List Quality + Reputation

**`hard_bounce_rate_lifetime`** - Threshold: lifetime hard-bounce rate **> 5%** (with ≥20 lifetime sends)
- `(hard_blocked + hard_unknown bounces) / emails_sent_all_time > 0.05`
- Computed on demand from `response_messages` — no rolling counter to drift
- 5% chosen to match Google Postmaster Tools / AWS SES "high bounce" range
- ESP-agnostic — applies same threshold to Gmail and Microsoft

### What gets ignored

- **Soft bounces** (mailbox-full, temp errors): captured for analytics, **never kill**
- **Below 20 lifetime sends**: skipped (insufficient data — give the inbox time to graduate)
- **Connection state**: monitoring-only per ADR-009, not a kill trigger

---

## SMTP Code Classification

Bounces are classified by extracting SMTP codes from message bodies. Classification feeds into the lifetime-rate numerator (`hard_blocked` + `hard_unknown`):

| SMTP Code | Extended Code | Classification | Used in rate? | Meaning |
|-----------|---------------|----------------|----------------|---------|
| 550 | 5.1.1 | `hard_unknown` | **Yes** | User doesn't exist |
| 550 | 5.7.1 | `hard_blocked` | **Yes** | Spam/policy block |
| 550 | 5.7.x (most) | `hard_blocked` | **Yes** | ESP-side reputation/policy rejection |
| 552 | 5.2.2 | `soft_full` | No | Mailbox full (temporary) |
| 421 | 4.7.0 | `soft_temp` | No | Temporary failure (retry) |

**Soft bounces** (4xx codes) are still classified and stored for analytics, but they don't enter the kill rate calculation.

See [docs/concepts/kill-triggers.md](../concepts/kill-triggers.md) for the full SMTP code table.

---

## Volume History Data Sources

The Volume History chart pulls from `daily_volume_snapshots` table:

| Metric | Data Source | Accuracy |
|--------|-------------|----------|
| **Emails Sent** | EmailBison campaign stats | ✅ Accurate - from API |
| **Daily Capacity** | SUM(daily_limit) of live inboxes | ✅ Accurate - snapshot at EOD |
| **Live Inboxes** | Count of `inbox_state = 'live'` | ✅ Accurate - snapshot at EOD |
| **Kills That Day** | Count of `killed_at = date` | ⚠️ Only system kills (excludes manual) |

**Backfill Status:**
- Initial backfill: 2026-02-23
- Coverage: Nov 25, 2025 - Feb 22, 2026
- Total emails: 54,716 across 7 workspaces
- Daily updates via sync worker

---

## Key Metrics Explained

### Survival Rate
```
(Live Inboxes / Total Inboxes) × 100%
```
**Good:** >85% | **Warning:** 70-85% | **Critical:** <70%

Shows what percentage of your total provisioned inboxes are still alive and usable.

### Kill Velocity (7d)
```
COUNT(inbox deaths in last 7 days)
```
**Good:** 0-2 | **Warning:** 3-5 | **Critical:** >5

Recent death rate - indicates current send quality.

### Kill Velocity (30d)
```
COUNT(inbox deaths in last 30 days)
```
Shows monthly trend - useful for comparing against capacity planning.

### Domain Health Score
```
Weighted average of all inbox health scores on that domain
```
**Healthy:** 80-100 | **Good:** 60-80 | **Warning:** 40-60 | **Critical:** 0-40

Indicates overall domain reputation.

---

## Common Questions

### Q: Why don't I see all my dead inboxes in the Kill Velocity chart?

**A:** The chart only shows **system kills** (bad sending behavior). If you:
- Manually deactivated a domain
- Cancelled a HyperTide subscription
- Manually marked inboxes as dead

Those won't appear in the Kill Velocity chart because they're operational decisions, not quality issues.

### Q: What does "flagged_spam_complaint" tag mean in EmailBison?

**A:** An inbox with this tag received a spam complaint from a recipient. The inbox was automatically:
1. Tagged in EmailBison with `flagged_spam_complaint`
2. Marked as `inbox_state = 'dead'` locally
3. Excluded from future campaign assignments

The inbox is **not deleted** - it remains in EmailBison for your review.

### Q: Can I reverse a kill?

**A:** Yes, using the `cancel_kill()` function:
1. Removes the kill queue entry
2. Removes the tag from EmailBison
3. Marks inbox as `inbox_state = 'live'` again

But **be careful** - if the inbox triggered a kill, there's probably a real issue. Investigate first.

### Q: Why are there different thresholds for different bounce types?

**A:** Because not all bounces are equal:

- **Spam blocks** (1 = kill) damage your sender reputation with the ESP
- **Bad addresses** (3 = kill) are just list quality issues - more tolerant

See [ADR-005: Differentiated Bounce Thresholds](../adr/adr-005-differentiated-bounce-thresholds.md) for the full rationale.

### Q: What's the "combined fallback" for hard_bounces_24h?

**A:** If the system couldn't determine whether a bounce was:
- Spam block (5.7.x)
- Bad address (5.1.1)

It falls back to the generic `hard_bounces_24h >= 2` threshold. This catches edge cases where SMTP code extraction failed.

### Q: How often do health checks run?

**A:** Every **15 minutes**. The EmailBison Sync Worker:
1. Syncs bounce data from EmailBison
2. Runs health checks against thresholds
3. Queues inboxes that breach thresholds
4. Kill processor tags and flags them

### Q: Do 24h counters reset?

**A:** Yes, at **midnight UTC** every day:
- `hard_bounces_24h` → 0
- `hard_blocked_24h` → 0
- `hard_unknown_24h` → 0

Without this reset, legitimate inboxes would eventually accumulate enough bounces to trigger thresholds.

**7-day counters** decay gradually (14% per day) to approximate a rolling window.

---

## Monitoring Best Practices

1. **Check Kill Velocity weekly** - Look for spikes or trends
2. **Review Kill Breakdown monthly** - Identify systematic issues
3. **Investigate sudden spikes** - What campaign/list caused it?
4. **Monitor dominant triggers** - If one trigger dominates, you have a pattern
5. **Track survival rate** - Declining survival = capacity problem
6. **Review tagged inboxes in EmailBison** - Filter by `flagged_*` tags to see patterns

---

## Related Documentation

- [Kill Triggers Concept](../concepts/kill-triggers.md) - Full technical documentation
- [Health Monitoring](../features/health-monitoring.md) - Overall health system
- [ADR-005: Differentiated Bounce Thresholds](../adr/adr-005-differentiated-bounce-thresholds.md) - Design decision
- [EmailBison Sync Worker](../local-development/emailbison-sync-worker.md) - How data is synced

---

## Appendix: Example Scenarios

### Scenario 1: Spike in spam_complaint kills

**Dashboard shows:** Kill Velocity spike, Kill Breakdown dominated by `spam_complaint`

**Root cause:** Recent campaign with spammy messaging or bad targeting

**Actions:**
1. Identify which campaign caused the spike (check timestamp)
2. Review campaign messaging and targeting
3. Quarantine the campaign or list segment
4. Improve messaging/targeting before redeploying

### Scenario 2: Steady hard_unknown_24h kills

**Dashboard shows:** Consistent kills every week, Kill Breakdown shows `hard_unknown_24h`

**Root cause:** Data source providing bad email addresses

**Actions:**
1. Review lead enrichment provider quality
2. Check data source (Apollo, ZoomInfo, etc.)
3. Implement email verification before sending
4. Flag or replace the data provider

### Scenario 3: fresh_inbox_hard_bounce pattern

**Dashboard shows:** Kills concentrated in first 2 weeks of inbox life

**Root cause:** Inboxes deployed before warmup completed

**Actions:**
1. Extend warmup period from 14 to 30 days
2. Review inbox deployment process
3. Implement warmup progress checks before deployment
4. Ensure backup capacity so you don't rush deployments
