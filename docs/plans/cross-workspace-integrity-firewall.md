---
title: Cross-Workspace Integrity Firewall
created: 2026-04-30
updated: 2026-04-30
status: PROPOSED — pending operator review of keyword seed + Charm sub-brand confirmation
related:
  - docs/audits/2026-04-29-cross-workspace-pollution-audit.md
  - docs/audits/2026-04-30-foreign-inbox-list.md
  - docs/audits/2026-04-30-skmr-full-inbox-list.md
  - apps/eod-reapply/HANDOFF.md
future-adr: ADR-009 (to be written when this plan reaches in-progress)
---

# Cross-Workspace Integrity Firewall

> **The hard rule** — *no inbox on the wrong workspace can ever go live, ever, under any condition.*
>
> Every section below serves that rule. If a part of this design lets a wrong-workspace inbox into a pool, that's a bug in the design.

---

## 0. TL;DR

When Hypertide provisions an inbox into the wrong EmailBison workspace (a known recurring bug — see batched events on 2026-03-11, 2026-03-31, 2026-04-14), our DB faithfully syncs the wrong placement and our pool/tag/lifecycle paths happily promote it to `live`. SPUI's `growspui.com` mailboxes are currently sitting tagged `live` in Sammy's workspace as a result. If `eod-reapply --apply` fires against Sammy, SPUI's actual mailboxes will physically send Sammy's outbound. Cross-tenant data leak.

This plan installs a structural firewall: every inbox is gated through a per-client domain-pattern check before it can hold any pool tag. Foreign inboxes get marked `is_quarantined=TRUE` and are excluded from every pool-eligibility query in the codebase. The check fires at sync time, runs against the existing `clients.domain_pattern` field (currently NULL for all 19 clients), and uses keyword substring matching so `.com` / `.co` / `.io` variants are handled naturally.

**This is defense, not offense. Hypertide upstream is still broken.** This plan does not fix the provisioning bug — it ensures the consequences don't reach the brand.

---

## 1. Problem statement (with concrete numbers)

As of 2026-04-30, fleet-wide audit found:

| Risk class | Count | Detail |
|------------|------:|--------|
| Foreign + tagged `live` (eligible for any reapply) | **22** | All Sammy ← SPUI on `growspui.com`, EB ids 9206–9227 |
| Foreign + tagged `reserve` (next promotion = leak) | **5** | Sammy ← SKMR on 5 stablekernel domains |
| Foreign + dormant (no pool tag) | **30** | Sammy ← Spout on `discoverspoutwater.com` |
| Foreign in EB workspace, no DB-side mismatch (already cleaned in DB) | **0** | (was 28 SKMR ← Sammy; resolved 2026-04-30 by domain-table flip) |

The root cause is provably batched — 22 inboxes on a single domain, single day (2026-03-31), consecutive EB sender ids 9206–9227. Random pollution wouldn't cluster. **Hypertide's automated provisioning is creating EB sender records with the wrong workspace_id.** The bug has not been root-caused; we have circumstantial evidence pointing to a workspace_id parameter passed wrong or a default falling back to Sammy.

The pattern repeats — three batched events in 35 days. Without a firewall, the next batch lands silently.

---

## 2. Hard constraints (the rules)

These come from the user. Every design choice below is checked against them.

| # | Rule | Enforcement |
|---|------|-------------|
| HR-1 | A foreign inbox **never** holds a pool tag — `live`, `reserve`, or any future pool value | Layer 3 (eligibility lockout) |
| HR-2 | Pollution must surface — operator must know it exists, not silently | Audit metric + Slack alert |
| HR-3 | Existing legitimate inboxes must not be affected by the firewall ship | Backfill correctness + the keyword seed table being right before deploy |
| HR-4 | The match must be simple — single field, simple substring, no over-engineered DSL | Keyword in `clients.domain_pattern`, comma-separated for multi-brand |
| HR-5 | New clients that haven't been configured cannot accidentally let pollution through | NULL pattern → quarantine all inboxes (fail-closed) |

---

## 3. What this does NOT solve

Stating this explicitly so we don't oversell it.

- **The Hypertide upstream bug** is unchanged. New pollution will keep arriving. The firewall just makes it inert.
- **Cross-tenant within shared-keyword clients** (SK ↔ SKMR both have `kernel` / `stablekernel` content) — if Hypertide places an SKMR mailbox in SK, BOTH workspaces' patterns match the domain, and the gate cannot distinguish. This is an irreducible weakness. Mitigation: operator review surface + narrower keyword for SK if a brand-distinguishing substring exists (it currently doesn't — see §6).
- **EB-side cleanup of the 57 existing polluted inboxes in Sammy** is outside this firewall. The firewall blocks them from holding pool tags going forward; physical removal from EB's Sammy workspace is a separate operator action.
- **Re-attaching dead inboxes to active campaigns** (the original `eod-reapply` problem) is not solved here; that tool remains the path. The firewall makes `eod-reapply` *safe* by guaranteeing its target_set has no foreign senders.

---

## 4. Design

### 4.1 Schema (minimal — three additions)

```sql
-- 1. Match input: per-client keyword(s). Already exists, all NULL today.
-- Type stays VARCHAR. Comma-separated for multi-brand clients (Charm).
-- Example values:
--   Sammy:                          'sammy'
--   SPUI:                           'spui'
--   Stable Kernel:                  'kernel'
--   Stable Kernel Market Research:  'stablekernel'
--   Charm:                          'charm,growthgroupusa,alldealsgroup,globaloutreachclub,urosaf-bio'
-- (clients.domain_pattern VARCHAR — already present, no migration needed)

-- 2. Match output: per-inbox quarantine flag.
ALTER TABLE sender_accounts
    ADD COLUMN is_quarantined BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN quarantine_reason VARCHAR,
    ADD COLUMN quarantine_detected_at TIMESTAMPTZ;

CREATE INDEX idx_sender_accounts_quarantined
    ON sender_accounts(is_quarantined)
    WHERE is_quarantined = TRUE;

-- 3. Hard structural lockout: pool can never be set on a quarantined row.
ALTER TABLE sender_accounts
    ADD CONSTRAINT chk_quarantined_no_pool
    CHECK (NOT is_quarantined OR inventory_pool_status IS NULL);
```

The CHECK constraint is load-bearing. Even if every code path that sets `inventory_pool_status` had a bug, this constraint would refuse the write at the DB layer. **HR-1 enforced structurally, not procedurally.**

### 4.2 Match logic (keyword substring, case-insensitive)

```python
def matches_workspace(email: str, domain_pattern: str | None) -> bool:
    if not domain_pattern:
        return False  # NULL pattern = no match (HR-5)
    domain = email.split('@', 1)[1].lower()
    keywords = [k.strip().lower() for k in domain_pattern.split(',') if k.strip()]
    return any(k in domain for k in keywords)
```

SQL equivalent (used in backfill + audit):

```sql
SELECT
    sa.id,
    NOT EXISTS (
        SELECT 1
        FROM unnest(string_to_array(LOWER(c.domain_pattern), ',')) AS k(keyword)
        WHERE LOWER(SPLIT_PART(sa.email_address, '@', 2)) LIKE '%' || trim(k.keyword) || '%'
    ) AS should_quarantine
FROM sender_accounts sa
JOIN workspaces w ON w.id = sa.workspace_id
LEFT JOIN clients c ON c.workspace_id = w.id
```

Keep deliberately stupid. No regex, no fuzzy matching, no domain parsing libraries. If a pattern doesn't catch what the operator wanted, the operator updates the keyword string. **HR-4.**

### 4.3 The gate — three sites, in order of importance

#### Gate site 1: `sync_accounts.upsert` (the primary gate)

Top of the function, before any pool / lifecycle / state assignment runs:

```python
async def upsert(self, eb_inbox, workspace_id):
    pattern = await self._get_client_pattern(workspace_id)
    quarantined = not matches_workspace(eb_inbox.email, pattern)
    
    if quarantined:
        await self._upsert_quarantined(eb_inbox, workspace_id, reason='pattern_mismatch')
        return  # never reaches the normal pool-assignment branches
    
    # ... existing logic, unchanged ...
```

The quarantined branch writes the row with `is_quarantined=TRUE`, `inventory_pool_status=NULL`, `quarantine_reason='pattern_mismatch'`, `quarantine_detected_at=NOW()`. We still record the row so it's visible to audits — we just exclude it from every downstream qualification.

#### Gate site 2: pool selection queries (defense-in-depth)

Every query that selects pool candidates gets `AND NOT sa.is_quarantined`:

- [sync_modules/lifecycle_tag_sync.py](sync_modules/lifecycle_tag_sync.py) — graduation queries
- [sync_modules/pool_promotion.py](sync_modules/pool_promotion.py) — candidate selection
- [sync_modules/set_tag_sync.py](sync_modules/set_tag_sync.py) — tag application
- [sync_modules/health_checks.py](sync_modules/health_checks.py) — kill candidate selection

Each filter is independently sufficient given the CHECK constraint, but they make the intent explicit at every callsite. **Critical**: if a new pool-selection callsite is added later and the developer forgets the filter, the CHECK constraint catches it — the write fails loud rather than silent pollution.

#### Gate site 3: the EB tag-application path

`set_tag_sync.py` reads from `inventory_pool_status` and applies the corresponding tag in EB. Since quarantined rows have `inventory_pool_status=NULL` (constraint-enforced), they emit no tag. No EB-side tagging, no promotion, no reapply target_set inclusion. The leak path closes structurally.

### 4.4 Audit + alerting

Extend [sync_modules/overhaul_audit.py](sync_modules/overhaul_audit.py) — three new metrics:

```python
metrics['quarantined_inbox_count']            # total is_quarantined=TRUE
metrics['quarantined_in_active_campaigns']    # the smoking-gun: still attached to a campaign
metrics['newly_quarantined_24h']              # detection trend — should hit during a Hypertide bug recurrence
```

Slack alert fires daily. Anything `quarantined_in_active_campaigns > 0` is a P1 — means a quarantined inbox is in someone's outbound, which (a) shouldn't happen post-firewall but (b) we want to know fast if it does.

### 4.5 Operator review surface

The existing daily Slack alert lists each quarantined inbox grouped by `(workspace, expected_owner_workspace, reason)`. Operator workflow:

1. Read alert: "Sammy has 3 newly quarantined inboxes — 3 on `growspui.com` (matches SPUI keyword)"
2. Decide: is this Hypertide pollution (yes, 99% of the time) or a legitimate brand exception we need to add?
3. If pollution: action is to physically clean up in EB (separate from the firewall — see §8)
4. If legitimate: update `clients.domain_pattern` to add the keyword, then re-sync triggers re-evaluation

**No automatic approval workflow in v1.** Operator changes the pattern manually. v2 could add a UI for keyword management, but it's not blocking.

---

## 5. Critical analysis — where this design is weak

The user explicitly asked for criticism, not advocacy. Here's where it's not airtight.

### 5.1 Shared keywords are an unavoidable hole

If SK and SKMR both have `kernel` (or `stablekernel`) in their pattern, an SKMR mailbox accidentally placed in SK's EB workspace passes SK's gate. The firewall will not catch this case.

**Mitigation options, none clean:**
- **(a) Use distinct keywords**: requires SK and SKMR to have brand-distinguishable substrings. Today, SKMR domains are all `*stablekernel.*` (verb-prefix); SK domains are mixed (`enjoystablekernel`, `evolvestablekernel`, **but also** `growwithkernel`, `optimizekernel`). No single substring distinguishes them — `stablekernel` matches BOTH workspaces' domains.
- **(b) Hardcoded approved-domain list per client**: stop using the keyword and store the literal domain set per client. High maintenance burden — every new domain requires an INSERT.
- **(c) Workspace pair allowlist**: explicitly mark "domain X belongs to workspace Y" via `domains.workspace_id` set authoritatively (not by the legacy first-arrival heuristic). This is what we did for the 11 stablekernel domains today — manual flip. Long term we'd need this as the permanent record, with new domains promoted to authoritative when first-arrival is operator-confirmed.

**Recommendation**: ship the firewall with shared keywords as-is, accept this gap explicitly, and queue option (c) as a follow-up where `domains.workspace_id` becomes the authoritative override that takes precedence over the keyword. The firewall already gives us 22 of 22 SPUI catches; the SK ↔ SKMR case is rare (1 of 100+ provisioning events) and catchable by the audit metric.

### 5.2 Pattern is operator-curated → operator error is a vector

If the operator sets Charm's pattern to `'charm'` instead of `'charm,growthgroupusa,alldealsgroup,globaloutreachclub,urosaf-bio'`, the firewall correctly quarantines the 4 sub-brand domains (~6 inboxes). That's what HR-5 expects (fail-closed). But it generates noise the operator must clear by updating the pattern.

If the operator sets a pattern *too broad*, e.g., `'a'`, every inbox passes — the firewall is silently disabled for that client.

**Mitigation**: keyword length validation (require ≥3 chars per keyword), and an audit metric `client_match_rate_per_workspace` that flags when match rate is suspiciously high (e.g., 100% when it should drop a few — though "should drop" requires a baseline). v1 ships without the validation; v2 adds it.

### 5.3 The CHECK constraint conflicts with existing rows

The 57 currently-polluted inboxes in Sammy have non-NULL `inventory_pool_status` (22 `live`, 5 `reserve`). Adding the constraint without first nulling these rows will fail the constraint check on existing data — the migration aborts.

**Migration sequence** must be:
1. Set `is_quarantined=TRUE` and `inventory_pool_status=NULL` for all currently-foreign rows (via the backfill query)
2. **Then** add the CHECK constraint
3. Companion EB-side untag (strip `live`/`reserve` from these in EB so the views align)

If steps run out of order, migration fails or EB stays out of sync.

### 5.4 The `domains` table is still not authoritative

We're not touching `domains.workspace_id` in this firewall. It remains a first-arrival heuristic, which means the SKMR/Sammy stablekernel case from today (legacy ownership wrong) will keep happening for new domains. The keyword pattern is now the authoritative answer, but `domains.workspace_id` is still consulted by other code paths (e.g., the cross-workspace audit, set_tag_sync's per-domain queries).

**Open architectural question**: should `domains.workspace_id` be deprecated entirely in favor of "derive workspace from the email's keyword match against `clients.domain_pattern`"? That would unify authority but is a larger change. For v1 we leave `domains.workspace_id` as is and accept that it occasionally lies.

### 5.5 Pattern changes are not idempotent for already-synced inboxes

If operator changes Charm's pattern from `'charm'` to `'charm,growthgroupusa'`, existing inboxes on `growthgroupusa.com` that were already quarantined don't auto-unquarantine — they wait until the next sync touches them. There's a window where operator has fixed the pattern but pool eligibility is still locked out.

**Mitigation**: post-pattern-change job that re-evaluates all sender_accounts for a given workspace and unquarantines those that now match. Trigger via API endpoint or run nightly. Not blocking for v1; manual re-sync of the workspace works as a workaround.

### 5.6 Layer 3 is enforced at multiple sites — every site is a potential bypass

`AND NOT sa.is_quarantined` must be added to ~5 query sites. If a future PR adds a new pool-selection codepath and forgets the filter, the CHECK constraint catches the eventual write — but the developer might be confused why their code "doesn't work." The error message from the constraint is technical (`new row violates check constraint`), not pedagogical.

**Mitigation**: a code search test in CI — `tests/test_no_pool_selection_without_quarantine_filter.py` greps for known query patterns and asserts the filter clause is present. Brittle but cheap.

### 5.7 New EB-side senders that bypass our DB

If Hypertide creates a sender in EB workspace W and we don't sync it (sync down, manual creation), the inbox exists in EB without a corresponding `sender_accounts` row. The firewall has no opinion — it can only act on rows in our DB. If the operator manually applies an EB tag to that sender, it gets pool eligibility from EB's perspective even though we never saw it.

**Mitigation**: this is the cross-workspace audit's job (separate plan, daily per-workspace EB scan). The firewall and the audit are complementary — neither alone is sufficient.

### 5.8 No protection during the deployment window

Between deploying the gate code and running the backfill, there's a window where new syncs use the gate but old polluted rows still hold pool tags. If `eod-reapply` runs in this window, it would still pick up the existing pollution.

**Mitigation**: deployment runbook hard-orders backfill BEFORE the gate ships, and disables `eod-reapply --apply` for the duration. ~30 minutes of operator vigilance. v2 wraps this in a feature flag for cleaner rollout.

---

## 6. Keyword seed table (CONFIRMED 2026-05-01 — populated in production)

Based on data-driven extraction from production owned domains (post-cleanup of 143 unpurchased candidates). All 11 active workspaces confirmed. Verified: 0 outliers across all 4,207 active inboxes when applying the firewall predicate against live data.

| Workspace / Client | Keyword(s) | Live match | Notes |
|---|---|---:|---|
| Sammy | `sammy` | 100% (634/634) | All inbox-level cross-pollution previously remembered ("22 SPUI in Sammy") was fixed before this audit — DB clean |
| SPUI | `spui` | 100% (95/95) | matches `growspui`, `setspui`, etc. |
| Spout | `spoutwater` | 100% (575/575) | matches `discoverspoutwater` and all `*spoutwater.com` |
| Selery | `selery` | 100% (729/729) | works across `.com/.co/.info/.io` TLDs |
| Search Atlas | `searchatlas` | 100% (660/660) | |
| Linkgraph | `linkgraph` | 100% (238/238) | |
| Hello Hero | `hellohero` | 100% (520/520) | matches plural form `helloheroes` too |
| Stable Kernel | `kernel` | 100% (175/175) | catches `*stablekernel` AND `growwithkernel`, `optimizekernel` — shared with SKMR (see §5.1) |
| Stable Kernel Market Research | `stablekernel` | 100% (105/105) | narrower than SK — catches `*stablekernel.*` only |
| Charm | `charm,growthgroupusa,alldealsgroup,globaloutreachclub,urosaf-bio,eudalie-bio,inspi-cure-eu,mydealslift,stylepad24` | 100% (437/437) | 9 sub-brands. All sub-brands operate as legitimate sub-clients testing through Charm (operator confirmed 2026-05-01). Per D-F. |
| Barrena | `guardare` | 100% (39/39) | brand uses `guardare.com`, NOT `barrena.com` |

**Inactive / no-inbox clients** (pattern can stay NULL until first inbox arrives):
- Checkout Components, Estrada, EventPanda, Ink'd, Neon, Peaksave, Root Access, Test Workspace

Per HR-5, NULL pattern = quarantine all. So if any of these inactive clients suddenly receives an inbox before pattern is set, the inbox correctly quarantines and the audit alert surfaces it.

---

## 7. Phased implementation

### Phase 0: Preparation — ✅ SHIPPED 2026-05-01
- ✅ Operator confirmed keyword seed table above
- ✅ Operator confirmed NULL-pattern fail-closed policy
- ✅ Charm sub-brand list extended to 9 (4 new: eudalie-bio, inspi-cure-eu, mydealslift, stylepad24) — all confirmed as legitimate sub-clients per D-F
- ✅ Generated-domain cleanup: 143 unpurchased candidates soft-deleted; forward prevention shipped (commit `ba39fe5`) — `is_active` semantic now strictly `(approval_status IN ('legacy','purchased'))`
- ✅ `clients.domain_pattern` populated for all 11 active workspaces; verified 0 outliers across 4,207 active inboxes when running firewall SQL predicate against live data

### Phase 2: Populate `clients.domain_pattern` — ✅ SHIPPED 2026-05-01
Single atomic UPDATE using `FROM (VALUES ...)` — see commit message for exact SQL. Defense-in-depth: every firewall query also filters `d.is_active = TRUE AND d.approval_status IN ('legacy','purchased')`.

### Phase 1: Schema migration (migration 101)
```sql
-- migrations/101_quarantine_columns.sql
ALTER TABLE sender_accounts
    ADD COLUMN is_quarantined BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN quarantine_reason VARCHAR,
    ADD COLUMN quarantine_detected_at TIMESTAMPTZ;
CREATE INDEX idx_sender_accounts_quarantined ON sender_accounts(is_quarantined) WHERE is_quarantined = TRUE;
```
No CHECK constraint yet — would conflict with existing polluted rows.

### Phase 2: Populate `clients.domain_pattern`
Single migration applying the operator-confirmed seed. Idempotent (only updates rows where pattern is NULL or matches the prior value).

### Phase 3: Backfill — quarantine existing pollution + null their pool tags
```sql
-- migrations/102_backfill_quarantine.sql
WITH foreign_inboxes AS (
    SELECT sa.id
    FROM sender_accounts sa
    JOIN workspaces w ON w.id = sa.workspace_id
    LEFT JOIN clients c ON c.workspace_id = w.id
    WHERE sa.is_active = TRUE
      AND (c.domain_pattern IS NULL OR NOT EXISTS (
          SELECT 1 FROM unnest(string_to_array(LOWER(c.domain_pattern), ',')) AS k(keyword)
          WHERE LOWER(SPLIT_PART(sa.email_address, '@', 2)) LIKE '%' || trim(k.keyword) || '%'
      ))
)
UPDATE sender_accounts sa
SET is_quarantined = TRUE,
    quarantine_reason = 'pattern_mismatch_backfill',
    quarantine_detected_at = NOW(),
    inventory_pool_status = NULL,
    updated_at = NOW()
FROM foreign_inboxes f
WHERE sa.id = f.id
RETURNING sa.email_address;
```

Companion: EB-side tag strip script `scripts/strip_quarantined_tags_from_eb.py` — reads the just-quarantined rows, removes their `live`/`reserve` tags from each workspace via per-workspace API key. Read-then-write, full pre-state JSON capture, single confirmation prompt before each workspace.

### Phase 4: Add CHECK constraint
```sql
-- migrations/103_quarantine_pool_constraint.sql
ALTER TABLE sender_accounts
    ADD CONSTRAINT chk_quarantined_no_pool
    CHECK (NOT is_quarantined OR inventory_pool_status IS NULL);
```
Now safe — no existing row violates.

### Phase 5: Code changes — gate + filters
- `sync_modules/sync_accounts.py`: gate at top of `upsert`
- `sync_modules/lifecycle_tag_sync.py`: filter
- `sync_modules/pool_promotion.py`: filter
- `sync_modules/set_tag_sync.py`: filter
- `sync_modules/health_checks.py`: filter
- `sync_modules/overhaul_audit.py`: 3 new metrics
- New: `sync_modules/workspace_matcher.py` (~30 lines, the match function + tests)

### Phase 6: Tests + audit gate verification
- Unit: matcher returns correct truth value for known cases (the 22 SPUI, 5 SKMR, 30 Spout)
- Integration: full upsert path with foreign inbox produces quarantined row with `inventory_pool_status=NULL`
- Constraint: attempting `UPDATE sender_accounts SET inventory_pool_status='live' WHERE is_quarantined=TRUE` raises constraint violation
- E2E: run backfill against staging snapshot, verify no false positives or negatives against audit doc

### Phase 7: Deploy + post-deploy verification
- Deploy charm-api (constraint + columns active)
- Deploy emailbison-sync (gate + filters active)
- Run audit script: confirm `quarantined_inbox_count == 57` (the known baseline)
- Confirm `quarantined_in_active_campaigns` count, expected near-zero (foreign inboxes shouldn't be in campaigns; if they are, that's a separate cleanup)
- Monitor for 48h: any new `quarantined_inbox_count` increase signals Hypertide bug recurrence — caught by the firewall this time

### Phase 8: `eod-reapply` integration
- Add pre-flight check to `eod-reapply check`: refuse target campaigns if their workspace has any `is_quarantined=TRUE AND in_active_campaign=TRUE` inboxes
- Closes the loop: the original motivating risk (SPUI mailboxes attached to Sammy via reapply) becomes structurally impossible

---

## 8. EB-side cleanup (separate from firewall, but sequenced with it)

The firewall makes the 57 polluted inboxes pool-ineligible in our DB. They still exist as EB sender records in the wrong workspace. Operator decides per-cluster:

| Cluster | Action | Why |
|---------|--------|-----|
| 22 SPUI on `growspui.com` in Sammy | DELETE from Sammy's EB workspace | These are SPUI's actual physical mailboxes — should not be visible to anyone operating Sammy |
| 5 SKMR-stablekernel in Sammy (active+reserve) | DELETE from Sammy's EB workspace | Same — SKMR has these correctly registered already; Sammy's copy is duplicate registration |
| 30 Spout-vollmer on `discoverspoutwater.com` in Sammy | DELETE from Sammy's EB workspace | Dormant residue, no operational risk but dirty — clean for hygiene |
| Any others surfaced post-firewall by audit | Per-case decision | Audit alert drives review |

EB DELETE is reversible (Hypertide can re-provision if it was a mistake). Audit captures pre-state JSON before each delete.

---

## 9. Test plan

### 9.1 Unit tests (`tests/test_workspace_matcher.py`)
| Case | Expected |
|------|----------|
| `bhoumik@growspui.com` against Sammy pattern `sammy` | foreign |
| `mary@analyzestablekernel.com` against SKMR pattern `stablekernel` | match |
| `mary@growwithkernel.com` against SK pattern `kernel` | match |
| `urosaf-bio.com` against Charm pattern `charm,urosaf-bio` | match |
| Any email against NULL pattern | foreign (HR-5) |
| Empty pattern after strip (e.g. `,,,`) | foreign |
| Case sensitivity: `MARY@SAMMY.COM` against `sammy` | match |
| Whitespace in pattern: `' charm , urosaf-bio '` | parsed correctly |

### 9.2 Integration tests
- Upsert foreign inbox: row written with `is_quarantined=TRUE`, `inventory_pool_status=NULL`
- Upsert legit inbox: normal pool flow runs, unchanged behavior
- Existing legit inbox on operator-curated pattern change: re-sync re-evaluates correctly

### 9.3 Constraint tests
- `UPDATE sender_accounts SET inventory_pool_status='live' WHERE is_quarantined=TRUE` → raises
- `UPDATE sender_accounts SET is_quarantined=TRUE WHERE inventory_pool_status IS NOT NULL` → raises (the constraint is symmetric on the bool flip)
- Concurrent transactions: backfill and live sync running together — no deadlock, no constraint violations

### 9.4 Backfill regression test
Run backfill against a snapshot of the 2026-04-30 production state. Assert:
- Exactly 57 rows in Sammy quarantine
- 0 rows in any other workspace post-backfill (we already flipped the SKMR domains)
- No rows with `is_quarantined=TRUE AND inventory_pool_status IS NOT NULL` after migration

### 9.5 E2E with `eod-reapply`
- Configure a Sammy campaign with the 22 SPUI inboxes attached (test scenario)
- Run `eod-reapply check --workspace Sammy --campaign-id X`
- Expected: `[FAIL] cross_workspace_quarantine: 22 inboxes in target_set are quarantined`
- Run `eod-reapply reapply --apply` — refuses with exit code 2

---

## 10. Operational runbook

### Day-to-day: reading the daily audit
Slack alert lists each quarantined inbox grouped by workspace. Operator decisions:

- **All quarantined are recognized as Hypertide pollution**: action is EB-side cleanup (`DELETE` from wrong workspace). No code change needed. Update the workspace's audit_logs for tracking.
- **A quarantined inbox looks legitimate to the workspace**: operator updates the keyword in `clients.domain_pattern`. Next sync re-evaluates and unquarantines. (For now, manual `UPDATE sender_accounts SET is_quarantined=FALSE WHERE id=...` is the workaround until v2 ships re-evaluation.)
- **Quarantine count spikes (e.g., +20 overnight)**: red flag — Hypertide bug just recurred. Cross-reference EB sender_id ranges; if consecutive, it's a batch event. Investigate provisioning logs.

### Updating a client's keyword
```sql
UPDATE clients SET domain_pattern = 'charm,newsubdomain', updated_at = NOW() WHERE workspace_id = '...';
-- Then trigger re-sync of that workspace to re-evaluate is_quarantined for existing rows
```

### Adding a new client
- Set `clients.domain_pattern` BEFORE first sync
- If you forget, all inboxes on first sync quarantine — alert fires — fix pattern, re-sync, unquarantines
- Inactive clients with NULL pattern are fine because they have no inboxes

---

## 11. Failure modes that break production

| Failure mode | Probability | Impact | Mitigation |
|--------------|-------------|--------|------------|
| Backfill mis-quarantines legit inboxes (pattern wrong) | Medium | Their pool tags get stripped, they fall out of campaigns | Operator reviews seed BEFORE deploy; rollback by inverse UPDATE + re-tag in EB |
| CHECK constraint deploys before backfill | Medium | Migration fails; deploy aborts | Migration ordering enforced via filename sequence (101→102→103) |
| Sync gate has a code bug | Low | New legit inboxes wrongly quarantined | Audit detects unusual quarantine rate; rollback by setting is_quarantined=FALSE (constraint allows that direction) |
| Operator sets pattern too broad | Low | Firewall silently disabled for client | Audit metric `client_match_rate` at 100% on a workspace where pollution exists is suspicious; v2 adds keyword length validation |
| EB tag strip fails mid-batch | Medium | DB and EB diverge; some EB tags remain | Pre-state JSON capture allows replay; idempotent strip script |
| Hypertide upstream bug recurs | High (probability of recurrence: high — it's already happened 3x) | New polluted inboxes arrive | **The firewall correctly handles this — they quarantine on arrival.** This isn't a failure, it's the firewall doing its job |

---

## 12. Decisions needed before this ships

| # | Decision | Default if unanswered |
|---|----------|----------------------|
| D-1 | Confirm full keyword seed table (§6) | Default to the proposed table — but operator must explicitly green-light each row |
| D-2 | NULL pattern policy: quarantine all (HR-5) vs. allow all | Default: quarantine all (per HR-5) |
| D-3 | SK/SKMR shared-keyword acceptance — ship as-is or block until distinct keywords found | Default: ship as-is, document the gap, follow up with `domains.workspace_id` authority later |
| D-4 | Should backfill also touch `is_active=FALSE` rows? | Default: no — they're already invisible to all sync paths. Only `is_active=TRUE` gets quarantined |
| D-5 | Pattern change re-evaluation: manual SQL workaround in v1, automated in v2? | Default: manual in v1 |
| D-6 | Slack channel for the audit alert | Default: same channel as `overhaul_audit` |

---

## 13. Future work (not in this plan)

- **ADR-009** — formal architectural decision record once this plan reaches in-progress. Captures the design + alternatives considered + the shared-keyword acceptance.
- **`domains.workspace_id` as authoritative source** — second-pass design where domain ownership is tracked authoritatively (operator-curated, not legacy first-arrival heuristic). Closes the SK ↔ SKMR shared-keyword hole.
- **UI for pattern management** — admin page where operator sees match rate per client, can edit keywords, triggers re-evaluation.
- **Hypertide upstream investigation** — the actual fix is upstream. Trace which provisioning code path created the 2026-03-31 batch (22 SPUI into Sammy) and the 2026-04-14 batch (50+ across pairs). Likely in `Hypertide/automation/` or `api/services/hypertide_client.py`. Once the bug is fixed, the firewall stays as a permanent safety net.
- **Per-workspace EB scanner** (`apps/integrity-scanner/`) — complementary to the firewall. Catches EB-side senders that never got synced into our DB (firewall has no opinion on those). Daily fleet-wide audit.

---

## 14. Hard-rule check

Final pass: does this design satisfy *the hard rule* — "no inbox on the wrong workspace can ever go live, ever"?

| Pathway to "live" | Blocked by |
|-------------------|------------|
| sync_accounts.upsert assigning pool='live' | Gate at site 1 — quarantined rows return early |
| lifecycle_tag_sync graduating to 'live' | Filter at site 2 — `AND NOT is_quarantined` |
| pool_promotion selecting candidate for 'live' | Filter at site 2 |
| set_tag_sync writing 'live' tag to EB | Filter at site 3 — also reads `inventory_pool_status` which is NULL by constraint |
| Manual `UPDATE sender_accounts SET inventory_pool_status='live'` | CHECK constraint refuses |
| New code path missing the filter | CHECK constraint refuses |
| EB-side manual tag (operator paste) on a polluted inbox | **NOT BLOCKED** — outside our enforcement boundary. Caught by audit (next-sync re-evaluation) but during the gap, the inbox holds the EB tag |

The single gap is operator-applied EB tags on a polluted inbox between firewall pass and next sync. Mitigation: `eod-reapply` and any reapply tool consume pool state from our DB (where the inbox is `inventory_pool_status=NULL`), not from EB tags, so even an EB tag manually applied doesn't actually trigger pool behavior in our stack.

**Verdict**: with the eod-reapply integration in Phase 8, the hard rule holds. Without it, there's a theoretical bypass via EB-side manual tag + something that consumes EB tags directly. None of our current code does that — but it's a class of future bug worth naming.
