---
title: V3 Compliance Gap Analysis
created: 2026-02-21
updated: 2026-04-30
tags: [health, v3, compliance, gaps, implementation]
---

# Inbox & Domain Health System V3 - Compliance Gap Analysis

Comprehensive analysis of V3 specification coverage in the charm-email-os implementation.

## 2026-04-30 STATUS UPDATE

Below the original Feb-2026 analysis (overall ~78%), several ADR-driven
shifts have changed the picture. Current state per workstream:

### Kill Trigger compliance — POST-OVERHAUL (ADR-006 + ADR-007 + ADR-009)

| Trigger | Feb-2026 status | 2026-04-30 status | Source of truth |
|---------|----------------|-------------------|-----------------|
| `spam_complaint` ≥ 1 | DONE | **DONE — Google instant-burns domain too (ADR-007)** | [docs/concepts/kill-triggers.md](../concepts/kill-triggers.md) |
| `hard_bounces_24h` ≥ 2 (MS) / ≥ 1 (Google) | uniform 2 | **ESP-AWARE per ADR-007** | health_checks.py KILL_THRESHOLDS_BY_ESP |
| `hard_blocked_24h` ≥ 2 (MS) / ≥ 1 (Google) | uniform 2 | **ESP-AWARE per ADR-007** | health_checks.py |
| `hard_unknown_24h` ≥ 3 (MS) / ≥ 1 (Google) | uniform 3 | **ESP-AWARE per ADR-007** | health_checks.py |
| `hard_bounce_rate_7d` > 2.0% | > 0.5% (Feb) | **TIGHTENED to 2.0%** (overhaul) | health_checks.py |
| `bounce_rate_all_7d` > 5% | > 5% | DONE | health_checks.py |
| `fresh_inbox_bounce` ≥ 1 | DONE | DONE | health_checks.py |
| `provider_block` (per-ESP) | MISSING (Feb) | **DONE — `flagged_provider_block_microsoft` / `_gmail`** | health_checks.py + kill_processor.py |
| `disconnected_timeout` ≥ 21 days | TODO | **REMOVED 2026-04-30 (ADR-009)** — connection-only conditions never produce a kill | [docs/adr/adr-009-...md](../adr/adr-009-connection-state-separated-from-kill-state-2026-04-30.md) |

### Operational discipline added since Feb

| Discipline | Source | Effect |
|------------|--------|--------|
| 20-send floor on count-based triggers | ADR-006 §"20-send floor" | Count-based kills only fire when `total_sends_24h ≥ 20` (or `7d ≥ 20` fallback). Prevents kills from low-volume noise (Phase 0 audit found 65% of count-trigger kills were on inboxes with <20 sends). |
| Per-workspace processing | ADR-006 + migration 089 | `kill_processor.process_workspace_queue(workspace_id, name)` replaces global cross-workspace fanout. Each workspace uses its scoped EB API key. |
| Cross-domain promotion allowed (within workspace) | ADR-006 | Killed inbox → next reserve in workspace promoted, regardless of source domain. Microsoft skipped (ride-to-death). |
| `flagged_but_alive` audit metric | mig-099 + overhaul_audit | Surfaces drift if a row was tagged in EB but DB wasn't updated to dead. Should be 0 in steady state. |
| `stuck_active_null_pool` audit metric | overhaul_audit + sync_accounts self-heal | Catches inboxes at lifecycle='active' AND pool=NULL on non-burned domains. Should be 0. |
| `kill_queue_pending_over_2h` audit metric | overhaul_audit | Surfaces stuck-pending kills (kill_processor runs every 15 min). |
| Connection state separated from kill state (ADR-009) | this session | Disconnect duration drives notifications, never kills. ~1,200 fleet-wide zombies were the symptom that prompted this change. |
| Silent-failure hardening | this session (commits 94fd0fa, e7bbd59) | `lifecycle_tag_sync.tag_inbox` and `kill_processor` pool-tag strip both distinguish 404 (intended) from transient failures (re-raise to retry). Stops new EB↔DB drift. |

### What remains MISSING vs V3 spec

Same as Feb-2026 in these areas — the work hasn't been picked up:

| Feature | Status |
|---------|--------|
| Confirming kill triggers (placement-based, multi-day trend) | TODO — requires placement testing service |
| Bounce source / segment quarantine analysis | TODO — list_segment_tracker partial |
| Postmaster/SNDS API integration | TODO — requires Hypertide integration |
| Domain rotation enforcement at 240+ days | PARTIAL — phase calculated, no enforcement |

### Net 2026-04-30 compliance estimate

- **Section 3 (Inbox Kill Triggers)**: 95% (was 95%; provider_block done, disconnected_timeout removed as out-of-scope-for-kill, confirming kills still TODO)
- **Section 5 (Domain Rules)**: 95% (was 95%; ESP-aware Google small-fleet logic added)
- **Section 6 (Portfolio Structure)**: 90% (cross-domain promotion + per-workspace package targets via mig-097)
- Overall: **~80%** (modest gain — most progress was on operational discipline, not feature surface)

### Cross-reference to current docs

For the AUTHORITATIVE current behavior, read these instead of the original Feb analysis below:

- [docs/concepts/kill-triggers.md](../concepts/kill-triggers.md) — current trigger tables, ESP-aware
- [docs/adr/adr-006-tagging-kill-overhaul-2026-04-27.md](../adr/adr-006-tagging-kill-overhaul-2026-04-27.md)
- [docs/adr/adr-007-drop-warning-state-2026-04-29.md](../adr/adr-007-drop-warning-state-2026-04-29.md)
- [docs/adr/adr-009-connection-state-separated-from-kill-state-2026-04-30.md](../adr/adr-009-connection-state-separated-from-kill-state-2026-04-30.md)
- [docs/plans/INBOX-INTEGRITY-PROGRAM.md](../plans/INBOX-INTEGRITY-PROGRAM.md) — master tracker

---

# (Original Feb-2026 analysis below — preserved for reference; some details superseded by 2026-04 ADRs)


## Critical Architectural Decision: Tag-Only, Never Delete

**The system is intentionally non-destructive.** We NEVER delete inboxes from EmailBison.

| Action | What We Do | What We DON'T Do |
|--------|------------|------------------|
| Kill Trigger Fires | Tag inbox with `flagged_{trigger_type}` | Delete inbox from EmailBison |
| Mark as Dead | Set `inbox_state = 'dead'` locally | Remove from campaigns in EmailBison |
| Domain Kill | Tag all domain inboxes | Delete domain or inboxes |

### Why Tags = Proof of Intent

- If a tag appears (e.g., `flagged_spam_complaint`), it **proves** the kill logic correctly identified the inbox
- Tags are **visible in EmailBison** for manual review
- Human operators decide whether to act on the tags externally
- This creates an **audit trail** without risk of automated destruction

### Implementation Files

- `sync_modules/kill_processor.py` - Tags only, no deletion
- `sync_modules/emailbison_client.py` - `delete_sender_account()` intentionally removed
- Kill queue status: `pending` → `flagged` (final state, no `deleted` state used)

**This is working as designed. The V3 spec's "kill" language maps to "tag + flag locally" in our implementation.**

---

## Executive Summary

**Updated: 2026-02-22** - Major V3 compliance improvements implemented.

| Section | Coverage | Status |
|---------|----------|--------|
| **Section 3: Inbox Kill Triggers** | **95%** | Instant kills + provider blocking DONE; Confirming kills TODO |
| **Section 5: Domain Rules** | **95%** | Lifecycle + thresholds + cross-inbox + domain-wide bounce DONE |
| **Section 6: Portfolio Structure** | **85%** | Roles + backup promotion automation DONE |
| **Section 7: ESP Configuration** | 40% | Schema ready; Postmaster/SNDS requires Hypertide integration |
| **Section 11: Campaign Management** | **95%** | Burn tracking + granular trigger breakdown + quarantine DONE |
| **Section 12: List Management** | **85%** | Segment quarantine + provider flagging DONE |
| **Section 13: Placement Testing** | 5% | Schema only; Requires external service |
| **Section 18: Alerting** | 30% | Slack only; Domain flagging alerts added |
| **Section 19: Data Model** | **98%** | campaign_burn_events + domain aggregate metrics added |

**Overall V3 Compliance: ~78%** (up from 70%)

### Recent Implementations (2026-02-22)

| Feature | File | Status |
|---------|------|--------|
| Campaign burn events table | `migration 036` | DONE |
| Granular trigger tracking per campaign | `kill_processor.py` | DONE |
| Domain aggregate metrics | `migration 037` | DONE |
| Domain-wide bounce rate check (>5% = flag) | `health_checks.py` | DONE |
| Cross-inbox pattern detection | `health_checks.py` | DONE |
| Domain flagging alerts | `slack_alerter.py` | DONE |
| Burn breakdown views | `migration 036` | DONE |

### Recent Implementations (2026-02-21)

| Feature | File | Status |
|---------|------|--------|
| Provider-specific blocking | `health_checks.py` | DONE |
| Domain health thresholds (1 dead=flagged, 2+=dead) | `health_checks.py`, `kill_processor.py` | DONE |
| Campaign burn counters | `kill_processor.py` | DONE |
| Campaign quarantine triggers (2+ burns = quarantine) | `kill_processor.py` | DONE |
| Backup promotion automation | `kill_processor.py` | DONE |
| List segment tracking | `list_segment_tracker.py` | DONE |
| Enrichment provider flagging | `list_segment_tracker.py` | DONE |

---

## Section 3: Inbox Kill Triggers

### Instant Kill Triggers (85% Implemented)

| Trigger | V3 Spec | Status | Location | Notes |
|---------|---------|--------|----------|-------|
| Spam complaint >= 1 | YES | **DONE** | `health_checks.py:224-231` | Exact match |
| Hard bounces (24h) >= 2 | YES | **DONE** | `health_checks.py:255-263` | Enhanced: Split into blocked/unknown |
| Hard blocked (24h) >= 1 | - | **DONE** | `health_checks.py:235-241` | MORE aggressive than spec |
| Hard unknown (24h) >= 3 | - | **DONE** | `health_checks.py:245-251` | Additional differentiation |
| Hard bounce rate (7d) > 0.5% | YES | **DONE** | `health_checks.py:266-274` | Min 50 sends enforced |
| Total bounce rate (7d) > 5% | YES | **DONE** | `health_checks.py:277-286` | Exact match |
| Fresh inbox bounce >= 1 | YES | **DONE** | `health_checks.py:288-296` | Age < 14 days |
| Provider block | YES | **MISSING** | - | No per-provider blocking logic |

### Confirming Kill Triggers (0% Implemented)

| Trigger | V3 Spec | Status | Notes |
|---------|---------|--------|-------|
| Primary inbox placement < 85% | 2 consecutive | **TODO** | Requires placement testing |
| Spam folder placement > 5% | 2 consecutive | **TODO** | Requires placement testing |
| Degrading trend | 3 consecutive days | **TODO** | Requires trend tracking |

**Note**: `health.py:577-583` has explicit TODO comment for confirming triggers.

### List Contamination Check (0% Implemented)

| Feature | Status | Notes |
|---------|--------|-------|
| Bounce source analysis | **MISSING** | No segment/company correlation |
| Segment quarantine | **MISSING** | No quarantine mechanism |

---

## Section 5: Domain Rules

### Domain Health Thresholds (85% Implemented)

| Rule | V3 Spec | Status | Notes |
|------|---------|--------|-------|
| < 15% unhealthy = Live | YES | **DONE** | `health_checks.py` DOMAIN_THRESHOLDS |
| 15-30% unhealthy = Flagged | YES | **DONE** | `health_checks.py` DOMAIN_THRESHOLDS |
| > 30% unhealthy = Pause | YES | **DONE** | `health_checks.py` DOMAIN_THRESHOLDS |
| 1 inbox dead = Flagged | YES | **DONE** | `health_checks.py:450` |
| 2 inboxes dead = Dead | YES | **DONE** | `health_checks.py:446` |
| Bounce rate > 5% domain-wide | YES | **DONE** | `migration 037` + `_check_domain_bounce_rate_thresholds()` |
| Complaints across multiple inboxes | YES | **DONE** | `migration 037` + `inboxes_with_complaints >= 2` |
| Blocks across multiple inboxes | YES | **DONE** | `migration 037` + `inboxes_with_blocks >= 2` |

### Domain Lifecycle (100% Implemented)

| Phase | Days | Status | Location |
|-------|------|--------|----------|
| Warming | 0-14 | **DONE** | `health.py:383-395` |
| Ramping | 14-30 | **DONE** | `health.py:383-395` |
| Establishing | 30-90 | **DONE** | `health.py:383-395` |
| Peak | 90-180 | **DONE** | `health.py:383-395` |
| Monitoring | 180-240 | **DONE** | `health.py:383-395` |
| Rotation | 240+ | **PARTIAL** | Phase calculated, no enforcement |

---

## Section 6: Portfolio Structure

| Feature | Status | Notes |
|---------|--------|-------|
| Inbox roles (Primary/Hot Backup/Warming) | **DONE** | `inbox_role` enum in schema |
| Pool tier tracking | **DONE** | `pool_tier` VARCHAR column |
| 100% hot backup capacity target | **DONE** | `_build_backup_capacity()` calculates |
| 50% warming pipeline target | **DONE** | Calculated in health endpoints |
| Hot Backup → Primary promotion | **MISSING** | `inbox_rotation_history` tracks but no automation |
| Max 2-3 inboxes per domain | **MISSING** | No constraint enforcement |

---

## Section 7: ESP Configuration

| Feature | Status | Notes |
|---------|--------|-------|
| ESP distribution tracking | **PARTIAL** | Counted but not configurable |
| Per-ESP inbox health | **PARTIAL** | Single health score, not per-ESP |
| Gmail Postmaster integration | **SCHEMA ONLY** | `gmail_reputation` column exists, not populated |
| Microsoft SNDS integration | **SCHEMA ONLY** | `microsoft_snds_status` column exists, not populated |
| Per-ESP kill tracking | **PARTIAL** | ESP field tracked at kill time |

---

## Section 11: Campaign Management

| Feature | Status | Notes |
|---------|--------|-------|
| Campaign states (Live/Quarantined/Dead) | **PARTIAL** | Schema has states, API uses different enum |
| Quarantine: 2+ inboxes burned in 7d | **MISSING** | No burn detection |
| Quarantine: Burns across 2+ domains | **MISSING** | No cross-domain detection |
| Quarantine: Bounce rate > 5% | **DONE** | `health.py:812-827` |
| Quarantine: Copy variant burns 2+ | **MISSING** | No variant tracking |
| Campaign-inbox sync | **DONE** | `sync_campaigns.py:228-340` |
| Campaign metrics snapshots | **DONE** | `sync_campaigns.py:171-226` |

---

## Section 12: List Management

| Feature | Status | Notes |
|---------|--------|-------|
| Segment quarantine on 2+ bounces | **MISSING** | No segment tables |
| Segment purge on 3+ bounces | **MISSING** | No purge mechanism |
| Enrichment provider flagging | **MISSING** | No provider tracking |
| List bounce rate > 3% stop | **MISSING** | No list-level thresholds |
| Lead status tracking | **DONE** | `LeadStatus` enum in models |
| Lead source attribution | **DONE** | `LeadSource` enum in models |

---

## Section 13: Placement Testing

| Feature | Status | Notes |
|---------|--------|-------|
| Seed list management | **MISSING** | No seed list tables |
| Test cadence scheduling | **MISSING** | No scheduling |
| Placement test execution | **MISSING** | No test triggering |
| Primary >= 85% threshold | **MISSING** | Columns exist, not populated |
| Spam < 5% threshold | **MISSING** | Columns exist, not populated |
| 2 consecutive failures = kill | **MISSING** | No consecutive tracking |

---

## Section 18: Alerting

| Alert Type | Severity | Channels | Status |
|------------|----------|----------|--------|
| Spam complaint | Critical | Slack+SMS+Email+Dashboard | **SLACK ONLY** |
| Domain killed | Critical | Slack+SMS+Email+Dashboard | **PARTIAL** |
| Inbox killed | High | Slack+Email+Dashboard | **SLACK ONLY** |
| Domain flagged | High | Slack+Email+Dashboard | **MISSING** |
| Campaign quarantined | High | Slack+Email+Dashboard | **MISSING** |
| Placement drop | Medium | Email+Dashboard | **MISSING** |
| ESP reputation drop | Medium | Email+Dashboard | **MISSING** |
| Backup capacity < 75% | Medium | Email+Dashboard | **MISSING** |
| Domain age > 180 days | Low | Dashboard | **MISSING** |
| Copy age > 45 days | Low | Dashboard | **MISSING** |

**Implemented channels**: Slack only (via `slack_alerter.py`)

---

## Section 19: Data Model (85% Complete)

| Table | Status | Notes |
|-------|--------|-------|
| sender_accounts (inbox) | **DONE** | All V3 fields present |
| domains | **DONE** | Core fields present |
| kill_queue | **DONE** | 24hr safety window workflow |
| kill_trigger_events | **DONE** | Trigger detection audit |
| inbox_health_snapshots | **DONE** | Time-series health data |
| inbox_rotation_history | **DONE** | Rotation audit trail |
| campaign_events | **DONE** | Reply/bounce events |
| response_messages | **DONE** | Full message content |
| **list_segments** | **MISSING** | Not created |
| **placement_tests** | **MISSING** | Not created |
| **seed_list_addresses** | **MISSING** | Not created |

---

## Implementation Priority Matrix

**Reminder**: All "kill" actions = **tag + flag locally**. Never delete from EmailBison.

### Critical (Must Have for Production)

1. **Provider-specific blocking** (Section 3)
   - Add provider block detection to health checks
   - Tag with `flagged_provider_block_{esp}` when detected

2. **Domain health thresholds** (Section 5)
   - Implement percentage-based unhealthy inbox detection
   - Tag domain inboxes when > 30% unhealthy (manual review decides action)
   - Change 1 dead inbox = Flagged (currently requires 2)

3. **Campaign quarantine triggers** (Section 11)
   - Detect 2+ inboxes tagged by same campaign
   - Flag campaigns for manual review (no auto-removal from inboxes)

### High Priority (Important for Scale)

4. **Backup promotion automation** (Section 6)
   - Auto-promote Hot Backup when Primary tagged/dead
   - Auto-promote Warming when Hot Backup promoted

5. **Postmaster/SNDS integration** (Section 7)
   - Gmail Postmaster Tools API integration
   - Microsoft SNDS data import
   - Per-ESP health differentiation (inform tagging decisions)

6. **Additional alert channels** (Section 18)
   - Email alerting for High/Medium severity
   - Dashboard alert display
   - SMS for Critical alerts

### Medium Priority (Nice to Have)

7. **Confirming kill triggers** (Section 3)
   - Placement testing integration
   - Consecutive failure tracking

8. **List segment management** (Section 12)
   - Segment quarantine tables
   - Enrichment provider tracking

9. **Placement testing** (Section 13)
   - Seed list management
   - Test scheduling

### Low Priority (Future Enhancement)

10. **Domain age rotation enforcement** (Section 5)
11. **Copy age tracking** (Section 18)
12. **Cross-inbox pattern detection** (Section 5)

---

## Files Requiring Changes

### Sync Modules
- `sync_modules/health_checks.py` - Add provider blocking, domain thresholds
- `sync_modules/kill_processor.py` - Add domain kill execution
- **NEW**: `sync_modules/domain_health_aggregator.py` - Domain metrics
- **NEW**: `sync_modules/placement_tester.py` - Placement test execution

### API Routes
- `api/routes/health.py` - Add domain thresholds, placement metrics
- `api/routes/campaigns.py` - Add quarantine state management
- **NEW**: `api/routes/placement.py` - Placement test endpoints

### Database Migrations
- **NEEDED**: Add `list_segments` table
- **NEEDED**: Add `placement_tests` table
- **NEEDED**: Add `seed_list_addresses` table
- **NEEDED**: Update `domains` with state transition logic

---

## Related Documentation

- [[health-monitoring]] - Current health monitoring docs
- [[../concepts/kill-triggers]] - Kill trigger reference
- [[../adr/adr-005-differentiated-bounce-thresholds]] - Bounce threshold ADR
