# Kill Trigger System - Executive Dashboard Guide

**Purpose:** Understanding what the Kill Velocity and Kill Breakdown charts show on the Executive Dashboard

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

These are **automated flags** triggered by the health monitoring system:

| Trigger Type | Threshold | What It Means | Why It Matters |
|--------------|-----------|---------------|----------------|
| `spam_complaint` | ≥1 complaint | User clicked "Report Spam" | **Instant death** - kills sender reputation |
| `hard_blocked_24h` | ≥1 block | ESP rejected as spam/policy violation | **Reputation damage** - server thinks we're spam |
| `hard_unknown_24h` | ≥3 bad addresses | Emails to non-existent addresses | **List quality issue** - we have bad data |
| `hard_bounces_24h` | ≥2 bounces | Unclassified hard bounces | **Fallback** - catches edge cases |
| `fresh_inbox_hard_bounce` | ≥1 bounce on new inbox | Any bounce on inbox <14 days old | **Premature deployment** - inbox wasn't ready |

### Manual Deactivations (NOT Shown) ❌

These are **business/operational decisions**:
- Domain deactivated
- HyperTide subscription cancelled
- Manual inbox shutdown
- Infrastructure changes

**Why excluded?** These aren't quality issues - they're strategic decisions. Including them would make the Kill Velocity chart useless for identifying send quality problems.

---

## The Kill Queue Workflow

When an inbox triggers a kill threshold, here's what happens:

```
1. DETECT (Every 15 min)
   Health check finds: hard_blocked_24h = 1
   ↓

2. QUEUE
   Insert into kill_queue table
   Status: 'pending'
   ↓

3. TAG (EmailBison)
   Apply tag: "flagged_hard_blocked_24h"
   Inbox remains in EmailBison (NOT deleted)
   ↓

4. FLAG (Local DB)
   inbox_state = 'dead'
   killed_at = NOW()
   kill_trigger = 'hard_blocked_24h'
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

**How to interpret:**

| Dominant Trigger | Root Cause | Action Needed |
|------------------|------------|---------------|
| `spam_complaint` | Recipients actively reporting spam | **Messaging problem** - emails are spammy or irrelevant |
| `hard_blocked_24h` | ESP blocking you | **Reputation damage** - need to improve sender reputation |
| `hard_unknown_24h` | Bad email addresses | **List quality** - clean your data sources |
| `fresh_inbox_bounce` | New inboxes bouncing | **Premature deployment** - need longer warmup |

---

## Differentiated Bounce Thresholds

Not all hard bounces are treated equally. The system uses **different thresholds** based on severity:

### High Urgency: Reputation Damage

**`spam_complaint`** - Threshold: ≥1
- User clicked "Report Spam"
- **Instant death, no exceptions**
- Indicates messaging is perceived as spam

**`hard_blocked_24h`** - Threshold: ≥1
- SMTP code 550 5.7.x (spam/policy rejection)
- **Critical** - ESP thinks you're a spammer
- Single occurrence triggers flag

### Medium Urgency: List Quality

**`hard_unknown_24h`** - Threshold: ≥3
- SMTP code 550 5.1.1 (user unknown)
- **Tolerant** - need pattern, not single event
- Indicates bad email addresses in your list

### Fallback: Unclassified

**`hard_bounces_24h`** - Threshold: ≥2
- Generic hard bounce counter
- Only triggers if specific triggers didn't fire
- Catches edge cases where SMTP code extraction failed

---

## SMTP Code Classification

Bounces are classified by extracting SMTP codes from message bodies:

| SMTP Code | Extended Code | Classification | Kill Trigger | Meaning |
|-----------|---------------|----------------|--------------|---------|
| 550 | 5.1.1 | `hard_unknown` | `hard_unknown_24h` | User doesn't exist |
| 550 | 5.7.1 | `hard_blocked` | `hard_blocked_24h` | Spam/policy block |
| 550 | 5.7.51 | `hard_blocked` + spam | `spam_complaint` | User reported spam |
| 552 | 5.2.2 | `soft_full` | None | Mailbox full (temporary) |
| 421 | 4.7.0 | `soft_temp` | None | Temporary failure (retry) |

**Soft bounces** (4xx codes) don't trigger kills - they're temporary issues.

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
