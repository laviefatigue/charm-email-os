---
title: Kill Triggers
created: 2026-02-12
updated: 2026-05-04
tags: [concept, health, kill-triggers, infrastructure, rate-rewrite-2026-05-04]
---

# Kill Triggers

Automated inbox termination system that protects domain reputation by detecting and removing problematic inboxes.

> **2026-05-04 — RATE-BASED REWRITE (load-bearing).** All windowed-count
> rules (`hard_blocked_24h ≥ N`, `hard_unknown_24h ≥ N`, `hard_bounces_24h
> ≥ N`, `hard_bounce_rate_7d > 2%`, `bounce_rate_all_7d > 5%`) are
> **removed** from the kill-decision path. A single ESP-agnostic
> lifetime-rate rule replaces them:
>
>     spam_complaint ≥ 1                                    → kill
>     emails_sent_all_time < 20                              → skip
>     hard_bounces_lifetime / emails_sent_all_time > 5%      → kill
>
> Numerator computed on demand from `response_messages.bounce_type IN
> ('hard_blocked','hard_unknown')`. Denominator from
> `sender_accounts.emails_sent_all_time` (synced from EB). **No stored
> rolling counter, no decay job, no daily reset** — the inflation bug
> class that produced the 2026-04-14 Barrena mass-kill (39 healthy
> Connected inboxes wiped in 0.18 seconds via `GREATEST(stale, fresh)`
> reconciliation) is structurally gone.
>
> Migration 105 added `hard_bounce_rate_lifetime` to the
> `kill_trigger_type` enum. New kills emit either
> `hard_bounce_rate_lifetime` or `spam_complaint` only. Legacy enum
> values stay for historical kill_queue / sender_account rows.
>
> **Soft bounces are captured (`bounce_type IN ('soft_full','soft_temp')`
> still classified and stored) but never trigger kills.** Mailbox-full
> and temp errors are not reputation signals.
>
> See [[../adr/adr-010-lifetime-rate-kill-rule-2026-05-04]] for the
> decision rationale, the Barrena evidence, and the
> [[../plans/kill-rule-rate-based-rewrite]] plan for execution detail.
> Resurrection of 307 false-positive kills (35 Barrena + 272 fleet)
> shipped same day. 58 legitimate new-kills queued under new rule
> (dominantly SKMR Mary Elzey + Hello Hero Jessica Jordan).

> ## ⚠ KEY CONSTRAINT — Read this before interpreting any threshold below
>
> **Charm has no access to authoritative spam-complaint signal.** No Microsoft JMRP enrollment. No Gmail Postmaster Tools API access. EB's `/replies?folder=spam` returns empty for our setup. Our entire complaint-detection surface is **response-parsing of EB-synced replies** — specifically the `folder='inbox'` lead-reply phrase match path (`detect_spam_in_response`). The Health V3 spec assumed JMRP-grade signal volume. **In practice the load-bearing reputation defense is the lifetime hard-bounce rate rule above (`hard_bounces_lifetime / emails_sent_all_time > 5%`)**, since hard-blocked bounces include all the `5.7.x` sender-reputation rejections Microsoft surfaces. See § _Spam complaint detection_ below for the full constraint analysis.

## Core Philosophy

1. **Rate, not count.** Lifetime hard-bounce rate is the kill signal. Count-based 24h rules produced false positives (one bad day on a healthy long-running inbox) and were vulnerable to counter inflation. Rates self-correct as more sends accumulate.
2. **On-demand computation, not stored counters.** The kill rule reads `COUNT(*) FROM response_messages` at every health-check tick. No counter to inflate, no decay to maintain, no reset job to skip. Eliminates the bug class entirely.
3. **Kill fast, swap fast, diagnose after** — Don't investigate while reputation degrades.
4. **100% backup capacity** — Always have warmed backups ready.
5. **1 spam complaint = inbox death** — Phrase-match coverage is poor (no JMRP/Postmaster Tools), but a phrase-match reply is high-signal when it does fire. Domain-level burn decision is rate-based.
6. **Min-volume floor of 20 lifetime sends.** Below 20 sends the rate rule skips (insufficient denominator). Above 20, every health-check tick reads fresh truth.
7. **Soft bounces are noise, not signal.** Captured for analytics, never killed on.

## Kill Trigger Types (post-2026-05-04 rate rewrite)

| Trigger | Condition | Priority | Tag in EB |
|---------|-----------|----------|-----------|
| `spam_complaint` | `complaints_lifetime ≥ 1` | 0 (highest) | `flagged_spam_complaint` |
| `hard_bounce_rate_lifetime` | `emails_sent_all_time ≥ 20 AND hard_bounces_lifetime / emails_sent_all_time > 5%` | 1 | `flagged_hard_bounce_rate_lifetime` |

That's it. Two rules. No ESP dispatch, no count thresholds, no
windowed counters.

### Removed rules (kept in enum for historical rows only)

These trigger types still exist in the `kill_trigger_type` enum and in
`INBOX_KILLING_TRIGGERS` so historical `kill_queue` / `sender_accounts`
rows still classify correctly, but **no code path emits them anymore**:

- `hard_blocked_24h` (was Microsoft 2 / Google 1)
- `hard_unknown_24h` (was Microsoft 3 / Google 1)
- `hard_bounces_24h` (was Microsoft 2 / Google 1)
- `hard_bounce_rate_7d` (was > 2% with 100+ sends)
- `bounce_rate_all_7d` (was > 5%, included soft bounces)
- `disconnected_timeout` (removed 2026-04-30 by ADR-009 — connection state is now monitoring-only)

## Bounce Classification (still load-bearing)

Bounce classification is **unchanged** by the rate rewrite. Every
bounce gets its SMTP code parsed by `extract_bounce_reason` in
`sync_modules/sync_events.py` and stored as `bounce_type` in
`response_messages`. The new kill rule reads only the `hard_blocked` and
`hard_unknown` rows; the rest exist for analytics and audit.

| Bounce Type | SMTP Codes | Meaning | Used by kill rule? |
|-------------|------------|---------|--------------------|
| `hard_blocked` | 550 5.7.x, or keyword (blocked/spam/blacklist/denied) | Spam/policy rejection | **Yes** (numerator) |
| `hard_unknown` | 550 5.1.x, or keyword (not found/unknown) | Bad email address | **Yes** (numerator) |
| `soft_full` | 552, 452, 5.2.2, 4.2.2 | Mailbox full/over quota | No (captured for analytics) |
| `soft_temp` | 421, 4.7.x, any 4xx | Temporary failure | No (captured for analytics) |
| `unknown` | Empty/missing bounce reason | Unclassifiable | No |

See [[adr-005-differentiated-bounce-thresholds]] for the original classification rationale (the rule it gated has been rewritten, but the classification scheme survives).

## Domain Burn Classification

Unchanged by the rate rewrite. After an inbox is killed, the kill
processor decides whether to also burn the domain. Two-tier:

| Classification | Triggers | Domain Action | Rationale |
|----------------|----------|---------------|-----------|
| **Rate-based domain evaluation** | `spam_complaint` | Complaint rate < 0.3% = safe. 0.3-1.0% = `monitoring` (7-day window). > 1.0% = immediate burn. | Rate-based thresholds scale across different domain sizes (3-inbox Gmail vs 50-inbox Microsoft). |
| **Inbox-level only** | All other triggers (including new `hard_bounce_rate_lifetime`) | Never burns domain | Bounces are inbox-level. Safe to promote B-Set inboxes from the same domain. |

**Workspace circuit breaker:** 3+ domains in the same workspace with spam kills within 24h triggers fleet-wide list quality response. Affected domains enter `monitoring` instead of burning.

```python
# From kill_processor.py
DOMAIN_KILLING_TRIGGERS = set()  # Empty — provider_block_* removed (misclassified recipient rejections)

CONDITIONAL_DOMAIN_TRIGGERS = {
    'spam_complaint',  # Rate-based: <0.3% safe, 0.3-1.0% monitoring, >1.0% burn
}

INBOX_KILLING_TRIGGERS = {
    'hard_bounce_rate_lifetime',  # NEW post-2026-05-04 — replaces all _24h count rules
    # Legacy values kept so historical kill_queue rows still classify:
    'hard_bounces_24h', 'hard_blocked_24h', 'hard_unknown_24h',
    'hard_bounce_rate_7d', 'bounce_rate_all_7d',
    'disconnected_timeout',
}
```

## Kill Queue Process (unchanged)

```
┌─────────────────────────────────────────────────────────────────┐
│                        KILL QUEUE FLOW                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  1. DETECT     Health check finds rate > 5% or complaint ≥ 1   │
│       ↓        (runs every 15 minutes)                         │
│                                                                 │
│  2. QUEUE      Insert into kill_queue table                    │
│       ↓        Status: 'pending'                               │
│                                                                 │
│  3. TAG        Apply trigger-specific tag in EmailBison        │
│       ↓        Tag: flagged_hard_bounce_rate_lifetime          │
│                  or flagged_spam_complaint                     │
│                Status: 'flagged'                               │
│                                                                 │
│  4. UPDATE     Mark inbox_state = 'dead' locally               │
│                Inbox excluded from future campaigns            │
│                                                                 │
│  NOTE: Inboxes are NOT deleted from EmailBison.                │
│        They remain tagged for visibility into WHY flagged.     │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Tagging System (post-rewrite)

| Tag Name | Trigger | Meaning |
|----------|---------|---------|
| `flagged_spam_complaint` | Spam complaint | User reported spam |
| `flagged_hard_bounce_rate_lifetime` | Lifetime rate > 5% | Sustained list-quality / reputation issue |

Plus historical tags from before the rewrite (do not re-emit; review only):
`flagged_hard_blocked_24h`, `flagged_hard_unknown_24h`, `flagged_hard_bounces_24h`.

## Database Schema

### kill_queue Table

| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID | Primary key |
| `inbox_id` | UUID | FK to sender_accounts |
| `workspace_id` | UUID | FK to workspaces |
| `trigger_type` | `kill_trigger_type` enum | Which trigger fired |
| `trigger_value` | DECIMAL | Actual value at trigger time (rate fraction or complaint count) |
| `trigger_threshold` | DECIMAL | Threshold that was breached |
| `status` | VARCHAR | pending, flagged, failed, cancelled |
| `tagged_at` | TIMESTAMP | When inbox was tagged in EmailBison |
| `tag_name` | VARCHAR | Trigger-specific tag applied |
| `error_message` | TEXT | Error / cancellation note |
| `created_at` | TIMESTAMP | When queued |

### sender_accounts — fields used by the rule

| Column | Type | Source | Usage |
|--------|------|--------|-------|
| `emails_sent_all_time` | INTEGER | EB sender.emails_sent_count (sync) | Rate denominator |
| `complaints_lifetime` | INTEGER | response-parsing on lead replies | Spam-complaint threshold |
| `hard_bounces_lifetime` | _computed_ | `COUNT(*) FROM response_messages WHERE bounce_type IN ('hard_blocked','hard_unknown')` | Rate numerator |

### sender_accounts — legacy columns (no longer load-bearing)

These columns are still updated by `aggregate_bounce_counts_from_events`
and the daily reset / decay jobs for UI consumers, but they no longer
drive kill decisions:

- `hard_bounces_24h`, `hard_blocked_24h`, `hard_unknown_24h`
- `hard_bounces_7d`, `soft_bounces_7d`
- `bounce_rate_7d`, `hard_bounce_rate_7d`, `total_bounce_rate_7d`

Will be cleaned up after a release cycle of UI-consumer migration.

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `KILL_THRESHOLD_SPAM` | 1 | Spam complaints to trigger kill |
| `KILL_MIN_SENDS_LIFETIME` | 20 | Min lifetime sends before rate evaluation |
| `KILL_MATURE_RATE` | 0.05 | Lifetime hard bounce rate threshold (5%) |
| `KILL_RULE_DRY_RUN` | true (initial) | When true, log decisions instead of queueing kills |

The legacy `KILL_THRESHOLD_HARD_BLOCKED_24H`, `_HARD_UNKNOWN_24H`,
`_HARD_BOUNCES_24H`, `_HARD_BOUNCE_RATE`, `_TOTAL_BOUNCE_RATE`,
`_MIN_SENDS`, `_MIN_SENDS_24H_FOR_COUNT_TRIGGER`,
`_MIN_SENDS_7D_FALLBACK` env vars are no longer read by the kill rule.
They remain for legacy column maintenance.

## Evaluation Order (post-rewrite)

```python
# Three branches, top to bottom (sync_modules/health_checks.py:evaluate_lifetime_rule)

1. complaints_lifetime ≥ 1                                 → 'spam_complaint'
2. emails_sent_all_time < KILL_MIN_SENDS_LIFETIME (20)     → SKIP
3. hard_bounces_lifetime / emails_sent_all_time > 0.05     → 'hard_bounce_rate_lifetime'
```

That's it. The function is pure — extracted as `evaluate_lifetime_rule(complaints, sends, hard_bounces)` for unit testability without DB.

## SMTP Code Classification (unchanged from prior ADR-005)

Bounces are classified by extracting SMTP enhanced status codes from message bodies via regex (`extract_bounce_reason` in `sync_modules/sync_events.py`). The classification is provider-aware: Microsoft 365 and Google Workspace have overlapping but not identical code semantics.

**Critical clarification (2026-05-01 audit):** No SMTP code from either Microsoft 365 or Google Workspace means "user reported as spam." Real complaint signals route out-of-band — see § _Spam complaint detection_ below. Earlier versions of this table mapped `550 5.7.51` to `spam_complaint`; that was incorrect (5.7.51 is `TenantInboundAttribution`, a B2B partner-connector restriction). Removed.

### Recipient-side rejections (NORMAL — count toward `hard_bounces_lifetime` numerator)

| Code | Provider | Meaning | bounce_type |
|------|----------|---------|-------------|
| 550 5.1.0 | Both | Sender address rejected | `hard_unknown` |
| 550 5.1.1 | Both | Mailbox doesn't exist | `hard_unknown` |
| 550 5.1.10 | MS | Recipient not found by SMTP lookup | `hard_unknown` |
| 553 5.1.2 | Gmail | Domain not found | `hard_unknown` |
| 550 5.2.1 | Both | Recipient account inactive / receive rate exceeded | `hard_unknown` |
| 550 5.4.1 | MS | Recipient address rejected (admin policy / no longer employed / org rule) | `hard_unknown` |
| 554 5.4.14 | MS | Hop count exceeded / mail loop | `hard_unknown` |
| 550 5.0.350 | MS | Generic wrapper for non-specific errors from external recipient server (read body) | varies |
| 550 5.4.317 | MS | Recipient anti-spam policy block | `hard_blocked` |
| 550 5.7.1 | Both | Generic policy block — auth, IP-rep, distribution group, transport rule | `hard_blocked` |
| 550 5.7.12 | MS | Recipient set up to reject outside-org mail | `hard_blocked` |
| 550 5.7.23 | MS | SPF violation at recipient | `hard_blocked` |
| 550 5.7.26 | Gmail | DMARC/SPF/DKIM unauthenticated (sender setup issue) | `hard_blocked` |
| 550 5.7.27 | Gmail | SPF specifically failed | `hard_blocked` |
| 550 5.7.28 | Gmail | **Algorithmic: unusual unsolicited email rate detected** | `hard_blocked` (reputation alarm) |
| 550 5.7.30 | Gmail | DKIM specifically failed | `hard_blocked` |
| 550 5.7.32 | Gmail | From-header alignment failure | `hard_blocked` |
| 550 5.7.40 | Gmail | Missing DMARC record/policy | `hard_blocked` |
| 550 5.7.51 | MS | TenantInboundAttribution / partner connector restriction (B2B config issue) | `hard_blocked` |
| 550 5.7.124/.133/.134/.136 | MS | Distribution group / mailbox / mail-user set to reject outside-org | `hard_blocked` |
| 550 5.7.193 | MS | Microsoft tenant-level rejection (recipient policy) | `hard_blocked` |
| 550 5.7.350 | MS | Recipient external server detected as spam (server-level filter) | `hard_blocked` |
| 550 5.7.520 | MS | Recipient anti-spam policy variant (5.7.5xx range) | `hard_blocked` |
| 550 5.7.703 | MS | Recipient Tenant Allow/Block List blocked | `hard_blocked` |

### Sender-side severe warnings (RARE but CRITICAL — your account/IP/tenant has been banned)

These codes mean Microsoft (or Gmail's algorithmic system) has explicitly banned your sending. They are NOT recipient errors — they are direct accusations that your reputation is in trouble. Currently fall through to the lifetime rate rule (will flip to instant-kill once Plan D Pass 3 sender-ban detection moves from alert-first to enforcement). See `docs/plans/kill-trigger-accuracy.md`.

| Code | Provider | Meaning | Severity |
|------|----------|---------|----------|
| 550 5.7.501 | MS | "Spam abuse detected" — sending account banned | **CRITICAL** |
| 550 5.7.502 | MS | "Banned sender" | **CRITICAL** |
| 550 5.7.503 | MS | "Banned sender" | **CRITICAL** |
| 550 5.7.508 | MS | IPv6 send-rate exceeded | High |
| 550 5.7.511 | MS | "Access denied, banned sender" — IP on Microsoft blocklist (delist@microsoft.com) | **CRITICAL** |
| 550 5.7.606–649 | MS | Banned sending IP range | **CRITICAL** |
| 550 5.7.705 | MS | Tenant exceeded outbound abuse threshold | **CRITICAL** |
| 550 5.7.708 | MS | Traffic not accepted from this IP — tenant flagged | **CRITICAL** |
| 550 5.7.750 | MS | Unregistered domain block | High |
| 550 5.7.800 | MS | EHLO/P1/P2 sender domain banned | **CRITICAL** |
| 550 5.7.509 | MS | Sender DMARC reject policy hit recipient | High |

### Soft / temporary (captured but never trigger kills)

| Code | Provider | Meaning | bounce_type |
|------|----------|---------|-------------|
| 552 5.2.2 / 452 4.2.2 | Both | Mailbox full | `soft_full` |
| 552 5.3.4 | Gmail | Message exceeds size/header limits | `soft_full` |
| 421 4.7.0 | Both | Generic temporary failure / PTR / TLS | `soft_temp` |
| 421 4.7.26 / 4.7.27 / 4.7.30 / 4.7.40 | Gmail | Rate-limited variant of auth-failure codes | `soft_temp` |
| 421 4.7.28 | Gmail | Unusual unsolicited email rate (rate-limited) | `soft_temp` |
| 421 4.7.29 | Gmail | TLS required (rate-limited) | `soft_temp` |

### ⚠ HARD CONSTRAINT — Spam complaint detection is response-parsing only

**Charm does NOT have access to authoritative spam-complaint signals.** This is a load-bearing constraint that affects every aspect of how the kill-trigger system can detect real reputation damage. Read this section carefully.

#### What we don't have

| Provider channel | Status | Why we can't use it |
|------------------|--------|---------------------|
| **Microsoft JMRP** (Junk Email Reporting Program) | ❌ Not enrolled | Requires registering an FBL recipient address with SNDS. Not currently configured. |
| **Gmail Postmaster Tools** | ❌ No access | Dashboard-only product, no API surface. |
| **EB `/replies?folder=spam`** | ✅ Endpoint exists, ❌ always empty | Verified 2026-05-01: 0 rows across all active campaigns / all workspaces / all time. |
| **EB `emailbison_campaigns.complaints` field** | ✅ Synced, ❌ always 0 | All 198 active campaigns report `complaints=0`. |

#### What we DO have

```
folder='inbox' phrase match  (active path)
   ├── detect_spam_in_response() runs on every reply we sync from EB
   ├── matches active-voice phrases: "I marked this as spam", etc.
   └── Production rate: very low — most leads who complain don't reply at all
```

#### What this means operationally

1. **Coverage is poor** — a fraction of real reputation damage is detected via complaints. Most goes through hard-bounce signals.
2. **`spam_complaint ≥ 1 = death` still fires correctly when triggered** — phrase-match is high-confidence when it does fire.
3. **Our actual reputation defense is the lifetime hard-bounce rate** — when Microsoft hard-rejects mail, we see `5.7.x` codes pile up in `response_messages`. Lifetime rate > 5% catches sustained abuse.
4. **Sender-ban codes** (5.7.501-503/511/606-649/703/705/708/750/800) are the closest proxy to "Microsoft is angry at us." Plan D Pass 3 currently alert-first.

## Daily Counter Reset (legacy maintenance only)

The `_24h` and `_7d` columns are still maintained by:

- `reset_daily_counters` (sync worker, daily at midnight) — zeros `_24h` columns.
- `decay_weekly_counters` (sync worker) — 14% daily decay on `_7d` columns.
- `aggregate_bounce_counts_from_events` (sync worker) — `GREATEST(stale, fresh)` reconciliation.

**These no longer affect kill decisions.** Kept for UI consumers that haven't migrated to the lifetime fields. Will be removed in a follow-up cleanup.

## Monitoring

### Kill Trigger Monitor (UI)

The Health page shows:

- **Action Required** (red) - Inboxes pending kill
- **Recent Kills** - Completed kills

### Verification Queries

```sql
-- Current kill queue status (post-rewrite, expect mostly hard_bounce_rate_lifetime + spam_complaint)
SELECT trigger_type::text, status, COUNT(*)
FROM kill_queue
GROUP BY trigger_type, status
ORDER BY COUNT(*) DESC;

-- Inboxes with active triggers under the new rule
SELECT email_address, emails_sent_all_time, complaints_lifetime,
       (SELECT COUNT(*) FROM response_messages rm
        WHERE rm.sender_account_id = sa.id AND rm.folder = 'bounced'
          AND rm.bounce_type IN ('hard_blocked','hard_unknown')) AS hard_bnc,
       ROUND(100.0 * (SELECT COUNT(*) FROM response_messages rm
        WHERE rm.sender_account_id = sa.id AND rm.folder = 'bounced'
          AND rm.bounce_type IN ('hard_blocked','hard_unknown')) /
            NULLIF(emails_sent_all_time, 0), 2) AS rate_pct
FROM sender_accounts sa
WHERE inbox_state = 'live' AND is_active = TRUE
  AND emails_sent_all_time >= 20
ORDER BY rate_pct DESC NULLS LAST;
```

## ESP-Specific Kill Profiles

Gmail and Microsoft have fundamentally different infrastructure shapes (set by vendor HyperTide), but the new lifetime-rate rule is **ESP-agnostic** — Postmaster Tools and AWS SES apply the same rate threshold to both.

| Metric | Gmail | Microsoft |
|--------|-------|-----------|
| **Inboxes per domain** | ~3 | ~50 |
| **Daily limit per inbox** | 20 | 2 |
| **Domain daily capacity** | ~60 sends | ~100 sends |
| **Time to cross 20-send floor** | 1 day | 10 days |
| **Time to accumulate 1500 lifetime sends** | ~80 days | ~750 days |
| **Time for rate to react to current behavior** | Fast (small denominator changes quickly) | Slow (small denominator already, but sends accumulate slowly) |
| **Blast radius per domain burn** | Low (~3 inboxes) | Catastrophic (~50 inboxes) |

The ESP-specific risk lives at the **domain-burn** layer, not the inbox-kill layer.

## Resurrection of False-Positive Kills (2026-05-04 one-shot)

The validator at `scripts/validate_new_kill_rule.py` audited the entire fleet against the new rule and identified inboxes that:

- Were killed by a count-based rule (`hard_blocked_24h`, `hard_unknown_24h`, `hard_bounces_24h`),
- Are still `Connected` in EB (not actually broken),
- Have no spam complaint (real reputation damage),
- Read as healthy under the new rule (rate ≤ 5%).

Resurrected via `scripts/resurrect_false_positive_kills.py`:

- Phase 2 (Barrena canary): **35/35 revived**.
- Phase 3 (fleet): **272/272 revived** across 8 workspaces.
- Total: **307 inboxes restored**.

The script is read-only by default (dry-run). `--apply` required to write. Audit log written per workspace. Idempotent — safe to re-run.

## Files

| File | Purpose |
|------|---------|
| `sync_modules/health_checks.py` | Kill rule + domain state. `evaluate_lifetime_rule` is the pure-function form of the rule. |
| `sync_modules/kill_processor.py` | Kill queue processing + domain burning. |
| `sync_modules/sync_events.py` | Bounce classification from EmailBison responses. |
| `api/routes/health.py` | Kill trigger monitor + ESP analysis + campaign attribution API. |
| `scripts/validate_new_kill_rule.py` | Read-only fleet audit against the new rule. |
| `scripts/resurrect_false_positive_kills.py` | One-shot revival of count-rule false positives. |
| `migrations/105_kill_trigger_lifetime_rate.sql` | Adds `hard_bounce_rate_lifetime` enum value. |
| `tests/test_kill_rule_unit.py` | 22 pure-function unit tests including Barrena regression. |
| `tests/test_kill_rule_lifetime.py` | 12 DB-integration tests. |

## Related

- [[../adr/adr-010-lifetime-rate-kill-rule-2026-05-04]] — Decision record for this rewrite.
- [[../plans/kill-rule-rate-based-rewrite]] — Execution plan (status: code complete, deployed, resurrection done, awaiting dry-run flip).
- [[../adr/adr-009-connection-state-separated-from-kill-state-2026-04-30]] — Why disconnect is not a kill trigger.
- [[../adr/adr-006-tagging-kill-overhaul-2026-04-27]] — Workspace-scoped EB API keys + per-workspace queue processing (still in effect).
- [[../adr/adr-005-differentiated-bounce-thresholds]] — Bounce classification rationale (the rule it gated has been rewritten; the classification scheme survives).
- [[../features/health-monitoring]] - Health monitoring overview.
- [[../local-development/emailbison-sync-worker]] - Sync worker that runs health checks.
- [[domain-lifecycle]] - Domain state machine.
