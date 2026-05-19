---
title: Hypertide Data Model and Change Tracking
created: 2026-05-18
updated: 2026-05-18
status: shipped (steps 3-9 + 10a in prod; only 10b clients.workspace_id drop pending)
tags: [hypertide, data-model, change-tracking, plan, schema-migration]
---

# Hypertide Data Model and Change Tracking

> **Purpose**: Hand-off document. Captures a model + design synthesis arrived at in conversation on 2026-05-18. Receiving chat already has HT API access and integration context — **this doc deliberately omits API-level details** ([[hypertide-api]] is canonical for those) and focuses on the data model rewrite and change-tracking design.
>
> **Status**: recommendations with positions taken. Each major decision marked **DECISION** is a position to ratify or challenge before implementation. Each item marked **OPEN** is still genuinely unresolved.
>
> **2026-05-18 resolution pass (this chat)** — the receiving chat that had HT API context has now resolved OPEN #1, #2, #4, #5; promoted them to RESOLVED with the actual production-data answers; refined DECISION 1 to reflect that HT exposes no stable organization identifier (only `subscriptionId` is stable); added DECISION 5 (default F&F) and DECISION 6 (verdict timing); flagged Concern A and Concern C against the original framing. Original phrasing preserved where still correct.
>
> Related:
> - Existing architecture plan: [[hypertide-service]] — sections of this get superseded; see "What this changes" below
> - Operator runbook: [apps/hypertide-worker/HANDOFF.md](../../apps/hypertide-worker/HANDOFF.md)
> - HT API reference: [[hypertide-api]] — unchanged, still canonical
> - Client model code: [api/models/client.py](../../api/models/client.py)

## TL;DR

Three connected reworks, in order:

1. **Schema rework** — invert `clients.workspace_id` (current 1:1) into `workspaces.client_id` (1:many). Add a client-level status field including a `friends_and_family` value. Bind HT identity via a `client_hypertide_subscriptions(subscription_id PK, client_id)` join table — **NOT a single `hypertide_organization_id` column**, because HT exposes no stable organization identifier (see RESOLVED #1). Required because today's schema cannot represent a single client with multiple workspaces (Stable Kernel + Stable Kernel Market Research, or Ink'd with both EB and Instantly).

2. **Ingest model inversion** — stop using "no matching DB row" as the F&F signal. Sync every HT subscription into `client_hypertide_subscriptions`, tag F&F at the client level, filter operationally via a `v_operational_clients` view (Concern A) instead of scattering filter clauses across every read path. **`domains.is_legacy` is kept** with its original "acquired outside the HT pipeline" semantic — only its F&F-detection misuse goes away (Concern C).

3. **Change tracking inside `apps/hypertide-worker`** — detect HT `Done|Active → Cancelled` transitions via DB trigger, correlate each to *our* domain-state justification persisted at kill-time on `domains.qualifies_for_cancellation_at` (DECISION 6 / formerly OPEN #4), alert on unjustified transitions. Stays inside the existing Coolify microservice. Sequencing constraint: the motivating case (Ink'd) cannot be evaluated until Instantly extraction is in place AND the kill-trigger evaluator persists its verdicts.

## Context

Today's hypertide-worker (Phase 1, shipped 2026-05-13) is strictly read-only. It pulls HT records, matches them to DB rows by `domain_name`, populates `domains.hypertide_*` columns, and flags unmatched rows as `is_legacy=TRUE`. The parity model assumes "if HT has it and we don't, it's friends-and-family — ignore."

That model is wrong in two ways:

- **F&F is at the organization level, not the absence-of-DB-row level.** HT stores everything by organization. Some orgs are our client work; some are partnerships using our HT account for their own infra. Both belong in our DB; the distinction is a positive tag at the client level.
- **The schema can't represent a client with multiple workspaces.** `clients.workspace_id` is 1:1. Real clients (Stable Kernel, Ink'd) have multiple workspaces — sometimes across multiple providers.

We're also missing a transition log: HT subscriptions move from active to cancelled, and we have no record of when or why. The audit overwrites `hypertide_status` on each pass; only the current snapshot survives. That makes incident reconstruction impossible and removes our ability to detect HT failures or out-of-band operator actions.

## The hierarchy

```
HT Organization (e.g. "Stable Kernel")              ← billing identity, source of truth in HT
  ↓ 1:1
CharmOS Client                                       ← clients table, holds F&F tag + status
  ↓ 1:many
Workspaces                                           ← workspaces table, resource-side fan-out
  ↓ each on
Provider (EmailBison | Instantly)                    ← determined by workspace type, API key per workspace
  ↓ each holds
Sender accounts / Inboxes                            ← sender_accounts table
  ↑ tied to
Domains                                              ← owned by HT org via subscription,
                                                       routed to workspace by inbox-landing
                                                       (today inferential; see Open #5)
```

### Canonical examples (the cases this design has to handle)

| Client | HT Org | Workspaces | Provider mix | F&F? | Notes |
|---|---|---|---|---|---|
| Stable Kernel | Stable Kernel | "Stable Kernel" EB, "Stable Kernel Market Research" EB | EB-only, 2 workspaces | No | Same client splits domains across two EB workspaces — needs disambiguation at ingest |
| Ink'd | Ink'd | "Ink'd" EB (dead), "Ink'd" Instantly (live) | Mixed: EB + Instantly | No | EB workspace is empty; real infrastructure on Instantly — current EB-only sync sees Ink'd as "no signal" |
| (any F&F partner) | partner-name | (zero or partner-managed) | Either, partner-managed | **Yes** | Synced into clients with F&F tag, then filtered out of all CharmOS operational views |

Any design that doesn't accommodate all three rows is incomplete.

## DECISION 1 — Schema rework (revised 2026-05-18)

**Position**: invert the `clients ↔ workspaces` relationship; **bind HT identity at the subscription level via a join table, NOT via a single org-id column on `clients`** (HT has no stable org id — see RESOLVED #1).

Current ([api/models/client.py:131](../../api/models/client.py#L131)):

```
clients (
  id UUID PK,
  name TEXT,
  workspace_id UUID UNIQUE,   -- the 1:1 FK that breaks the model
  ...
)
workspaces (
  id UUID PK,
  ...                          -- no FK to clients
)
```

Proposed:

```
clients (
  id UUID PK,
  name TEXT,
  client_status VARCHAR(24) NOT NULL DEFAULT 'friends_and_family',
                                              -- 'client' | 'friends_and_family' | 'prospect' | 'inactive'
                                              -- default is F&F per DECISION 5 — operator promotes to 'client'
  primary_hypertide_organization_name TEXT,   -- human label for ops, NOT a unique key
                                              -- (org names are plural per real customer — Hello Hero has
                                              -- 5 variants, Charm 6, Stable Kernel 4 — so this is a
                                              -- nullable display field, nothing more)
  -- workspace_id column REMOVED after backfill
  ...
)
workspaces (
  id UUID PK,
  client_id UUID REFERENCES clients(id),      -- NEW: 1:many parent FK
  provider VARCHAR(16) NOT NULL DEFAULT 'emailbison',  -- DECISION 3
  ...
)

client_hypertide_subscriptions (
  subscription_id   TEXT PRIMARY KEY,         -- Stripe sub_* — stable, what HT actually keys on
  client_id         UUID NOT NULL REFERENCES clients(id),
  first_seen_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  last_seen_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  organization_name TEXT,                     -- HT's organizationName at first/last sight, for human matching
  notes             TEXT                      -- operator scratch (e.g. "promoted from F&F 2026-06-01")
);
CREATE INDEX chs_client_idx ON client_hypertide_subscriptions(client_id);
```

### Why subscription-as-identity, not org-name

HT's `/orders/active` fields (verified this session): `id, domain, status, paymentStatus, subscriptionId, forwardingDomain, sendingTool, organizationName, productId, createdAt`. There is no `organizationId`. `organizationName` is free text. Observed plurality:

- Hello Hero: 5 distinct `organizationName` values (`HH Compute`, `HH Load balancer`, `HH Scaling system`, `HH Server farm`, `HH System`)
- Charm: 6 distinct values
- Stable Kernel: 4 distinct values (`Stable Kernel`, `stable kernel`, `Stable Kernel Network HT`, `Stable Kernel Market Research`)

A `clients.hypertide_organization_id TEXT UNIQUE` column would have no source to populate it from. `subscriptionId` (Stripe) IS stable and IS what HT keys billing on. The join table makes the operator-curated mapping explicit and reversible.

### Migration outline

1. `ALTER TABLE clients ADD COLUMN client_status VARCHAR(24) NOT NULL DEFAULT 'friends_and_family', ADD COLUMN primary_hypertide_organization_name TEXT;`
2. `ALTER TABLE workspaces ADD COLUMN client_id UUID REFERENCES clients(id), ADD COLUMN provider VARCHAR(16) NOT NULL DEFAULT 'emailbison';`
3. `CREATE TABLE client_hypertide_subscriptions (...);` per above.
4. **Manual seed step**: operator backfills the join table from current state — "these subscription_ids are Stable Kernel, those are Sammy AI, these are friends-and-family, etc." We have ~211 unique subscription_ids in current production, so this is a one-shot tagging exercise of a bounded set, not unbounded operator work. Use the 2026-05-06 snapshot in `d:/tmp/ht_snapshot_2026-05-06T18-45-43Z.json` as the seed source (or pull fresh).
5. Backfill `workspaces.client_id` from existing `clients.workspace_id` (one-shot UPDATE), then operator reviews and groups orphan workspaces under their correct client (Stable Kernel + Stable Kernel MR → one client). No safe automated rule for this.
6. Promote known-real clients from default `friends_and_family` to `client_status='client'` based on existing roster (operator action — bounded list of ~15 in-scope workspaces today).
7. After verification, `ALTER TABLE clients DROP COLUMN workspace_id;` — and update all reads.
8. Create `v_operational_clients` view (per Concern A / DECISION 2 revised) as the new default read API.

### What this breaks

- Every code path that reads `clients.workspace_id` directly. Notable in [api/routes/clients.py](../../api/routes/clients.py), [api/models/client.py:131](../../api/models/client.py#L131) (Client model), [api/models/client.py:102](../../api/models/client.py#L102) (ClientCreate), [api/models/client.py:165-167](../../api/models/client.py#L165-L167) (LinkWorkspaceRequest).
- The `Client.workspace_name` joined field ([client.py:132](../../api/models/client.py#L132)) becomes a list or has to be removed.
- The `LinkWorkspaceRequest` endpoint semantics change: linking a workspace becomes "attach this workspace to this client" instead of "set this client's only workspace."

This is the largest scope item in the doc. It is unavoidable — the Stable Kernel and Ink'd cases cannot be represented otherwise.

## DECISION 2 — F&F as positive client-level tag (revised 2026-05-18)

**Position**: replace the "ignore if unmatched" rule with "sync all subscriptions, tag F&F at the client level, **filter operationally via a view, not scattered WHERE clauses** (Concern A)."

This supersedes the current parity model at [docs/architecture/hypertide-service.md:22-29](../architecture/hypertide-service.md#L22-L29).

### Ingest flow (revised)

```
HT /orders/active returns records
  ↓
group by subscriptionId  (NOT by organizationName — see RESOLVED #1)
  ↓
for each subscriptionId:
  - if client_hypertide_subscriptions.subscription_id matches → known, update last_seen_at, route to client
  - else → INSERT new clients row (client_status='friends_and_family' per DECISION 5),
           INSERT client_hypertide_subscriptions row binding sub → new client,
           operator promotes to 'client' when curated
  ↓
for each domain under that subscription:
  - INSERT/UPDATE domains row with hypertide_* state
  - workspace assignment per RESOLVED #5 routing rule (forwardingDomain → sendingTool+provider → operator)
```

### Operational filtering — via view, not scattered clauses

Scattering `WHERE client_status NOT IN (...)` across every read path is the failure mode this design is supposed to prevent. The next forgotten filter leaks F&F data into kill triggers or rotation logic.

```sql
CREATE VIEW v_operational_clients AS
  SELECT * FROM clients
  WHERE client_status NOT IN ('friends_and_family', 'inactive');

CREATE VIEW v_operational_workspaces AS
  SELECT w.* FROM workspaces w
  JOIN v_operational_clients c ON c.id = w.client_id;

CREATE VIEW v_operational_domains AS
  SELECT d.* FROM domains d
  JOIN v_operational_workspaces w ON w.id = d.workspace_id;
```

**Convention going forward:** operational code (dashboards, kill triggers, rotation, health monitoring, reports for our own GTM work) reads `v_operational_*`. Code that genuinely needs the full picture (financial reporting, drift detection, this plan's change tracker) opts in by reading base tables explicitly. **Inverts the failure mode** — you have to opt INTO seeing F&F, not remember to filter it out.

### What goes away vs what stays

- **GONE**: the "ignore HT-only records" branch in [audit.py:126-128](../../apps/hypertide-worker/src/hypertide_worker/audit.py#L126-L128). Worker syncs all subscriptions; F&F filtering is operational not ingest-time.
- **GONE**: `workspaces.manages_via_hypertide` is redundant once `client_status` carries it. Drop after backfill confirms parity.
- **KEPT (with redefined semantic — Concern C)**: `domains.is_legacy` — original meaning was "acquired outside the HT pipeline" (pre-HT manual provisioning, registrar-direct purchases). That sourcing/lifecycle distinction still matters and is NOT the same as F&F. The misuse for F&F detection goes away; the column does not.

## DECISION 3 — Multi-provider per client

**Position**: provider connection is per-workspace, not per-client. A client can have workspaces on different providers simultaneously (Ink'd). Each workspace owns its provider API key.

Add to `workspaces`:

```
ALTER TABLE workspaces
  ADD COLUMN provider VARCHAR(16) NOT NULL DEFAULT 'emailbison';
  -- values: 'emailbison' | 'instantly'
```

Implications:
- The justification evaluator (DECISION 4) must aggregate inbox health across ALL workspaces under a client, not just one. For Stable Kernel that means union of two EB workspaces' sender_accounts. For Ink'd that means EB + Instantly (when Instantly is wired).
- Existing EB sync code is implicitly scoped to `provider='emailbison'` workspaces. Adding Instantly sync = new worker reading from `provider='instantly'` workspaces, populating the same `sender_accounts` table with provider-tagged rows.
- This decision does not require Instantly to ship now — it just defines the schema so Instantly can be added without another migration.

## DECISION 4 — Change tracking design

**Position**: detect `Done|Active → Cancelled` transitions per audit pass, write to a new event table, correlate to justification, alert on unjustified.

### What "justified" means

A transition is **justified** if our domain-state rules — kill triggers rolled up from inbox-level to domain-level — had already classified the domain as eligible for cancellation/swap. The operator processing the cancel in HT was acting on our system's recommendation.

A transition is **unjustified** if our rules said the domain was healthy. Three possible causes, indistinguishable from data alone:
- (a) HT bug — they cancelled something that shouldn't have been cancelled.
- (b) Operator clicked cancel in HT's dashboard outside our system's recommendation.
- (c) Client contacted HT directly and asked them to cancel.

The alert text must reflect this — *"unexplained from our data, please reconcile"* — not *"HT failed."* Otherwise the first false alarm trains operators to ignore it.

### Where this lives

Inside `apps/hypertide-worker`. No new service.

### Storage

```
CREATE TABLE hypertide_status_events (
  id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  domain_id                   UUID NOT NULL REFERENCES domains(id),
  hypertide_record_id         TEXT NOT NULL,
  hypertide_subscription_id   TEXT,
  previous_status             VARCHAR(16),
  previous_cancellation_type  VARCHAR(24),
  previous_to_be_cancelled    BOOLEAN,
  new_status                  VARCHAR(16),
  new_cancellation_type       VARCHAR(24),
  new_to_be_cancelled         BOOLEAN,
  justification_verdict       VARCHAR(24),     -- 'justified' | 'unjustified' | 'no_signal' | 'evaluator_unavailable'
  justification_evidence      JSONB,           -- snapshot of the inputs the verdict was based on
  detected_at                 TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  sync_audit_log_id           UUID REFERENCES sync_audit_log(id)
);
CREATE INDEX hse_domain_idx       ON hypertide_status_events(domain_id, detected_at DESC);
CREATE INDEX hse_unjustified_idx  ON hypertide_status_events(detected_at DESC)
  WHERE justification_verdict = 'unjustified';
```

### Implementation site

Two viable choices, both defensible:

1. **In the audit's apply phase** ([audit.py:252-306](../../apps/hypertide-worker/src/hypertide_worker/audit.py#L252-L306)): pair old `db_row` state against new `ht_rec` state, INSERT event rows when material fields changed.
2. **DB trigger on `domains`**: `AFTER UPDATE` trigger fires when any of `hypertide_status`, `hypertide_cancellation_type`, `hypertide_to_be_cancelled` changes. Trigger function INSERTs into `hypertide_status_events`.

**Recommended**: DB trigger. Decouples event capture from the worker, automatically captures any future write path (Phase 2 cancellation orchestration, manual operator SQL), and survives audit code refactors. Justification verdict can be filled in by a separate pass.

### First-run flood mitigation

Deploying without protection makes every currently-cancelled domain look like a `NULL → cancelled` transition. Two options:

1. **Suppress NULL-source transitions in the trigger** — events only fire when `previous_status IS NOT NULL`. Simpler.
2. **Seed the events table at install** with current state as "baseline" rows, then trigger fires on real changes thereafter. Cleaner audit story but requires a one-shot script.

**Recommended**: option 1. The baseline isn't actionable anyway.

### Resolution caveat

Audit runs every 24h. If a domain goes `Done → ToBeCancelled → Cancelled` inside one window, we capture only the latest leg. The output is a daily-resolution change detector, not a true event stream. Document this in the runbook so nobody is surprised later.

## DECISION 5 — Default `client_status` by `sending_tool` (revised 2026-05-18; formerly OPEN #2)

**Position**: new HT subscriptions appearing in `/orders/active` without an existing `client_hypertide_subscriptions` binding default by `sending_tool`:

| `sending_tool` | Default `client_status` | Reasoning |
|---|---|---|
| `Email Bison` | `client` | We run the EB account; F&F partners don't use it. Snapshot 2026-05-06: 127 unique subs, all real client orgs (Charm, Linkgraph, SPUI, Bridge, HH variants). |
| `Instantly.ai` | `client` | We run the Instantly account too; partners don't use it. Snapshot: 42 unique subs, all ours (Inkd variants, Sammy, Stable Kernel Network HT, Stone Products Unlimited). Domain extraction lands later — the client row hangs dormant until then but is correctly classified for change-tracking. |
| `Smartlead.ai` | `friends_and_family` | Operator decision 2026-05-18. Even Charm-prefixed orgs (Charm Node, Charm Orchestration, Charm Scaling system) running on Smartlead are not part of CharmOS-managed inbox infra and stay F&F. |
| missing / other / unknown | `friends_and_family` | Safe failure for tools we haven't classified. |

Applies in two places:
- **Seed script** (one-shot operator-run) — binds the 19 existing clients by org-name match first, then classifies remainder by this rule.
- **Hypertide-worker first-sync branch** — same rule when a new sub appears in a future audit.

Why revised from the original "always F&F" default:
- Original rationale was correct (asymmetric error cost; F&F is the safe failure for *unknown* infra), but `sending_tool` is positive evidence of whose infrastructure the sub runs on. Treating an EB or Instantly sub as F&F would mean filtering Ink'd-on-Instantly out of every operational view — wrong in the opposite direction.
- The asymmetric-cost argument still holds for unknown / non-EB-non-Instantly tools; that's where the F&F fallback applies.
- Promotion of a mis-classified Smartlead sub to `'client'` is still one UPDATE; demotion of a mis-classified `'client'` is also recoverable since no kill decisions land until step 8 (kill-trigger wiring).

## DECISION 6 — Persist `qualifies_for_cancellation_at` at kill-evaluator time (formerly OPEN #4)

**Position**: option (3) from the original OPEN #4. The kill-trigger evaluator writes per-domain verdict to a persisted column on `domains` (or a dedicated table) at kill-evaluation time. The change-tracker worker reads it.

```
ALTER TABLE domains
  ADD COLUMN qualifies_for_cancellation_at  TIMESTAMPTZ,  -- when our rules last said "yes"
  ADD COLUMN qualifies_for_cancellation_reason TEXT;      -- which rule fired (kill_trigger or summary)
```

### Why this is the only honest option

Options (1) "worker calls API for verdict per transition" and (2) "duplicate rule logic in worker" both have to **re-derive a verdict at HT-transition time**. But by then the kill that justified the cancellation could be days or weeks in the past. The kill-trigger state AT THAT POINT, not at transition-detection time, is what we need.

Concretely: a domain crosses the complaint-rate threshold on day 1, operator processes the HT cancel on day 4, HT terminates on day 6, our 24h audit detects the transition on day 7. If we re-derive the verdict on day 7, the domain may have additional inboxes promoted (rotation), or the kill might have been reverted, or the rule itself may have evolved (ADR-010 was a real rule change in this codebase). The day-7 verdict isn't the right answer to "was this justified."

Persisting the verdict at the moment the rules fired means the change tracker reads a faithful "yes our system said so at time X" instead of re-litigating ancient rules. The worker stays decoupled — it reads a column, not an API.

### What the kill evaluator writes

When a kill_trigger fires (per docs/KILL-TRIGGERS.md) and crosses domain-burn threshold, the evaluator writes:

```sql
UPDATE domains
SET qualifies_for_cancellation_at = NOW(),
    qualifies_for_cancellation_reason = $1   -- e.g. 'spam_complaint_rate_1.5pct', 'workspace_circuit_breaker', etc.
WHERE id = $2;
```

Idempotent: re-firing on the same domain updates the timestamp. A revert action (e.g. domain promoted back from `dead`) should write NULL to both fields.

### What the change tracker reads (verdict logic)

```
On detected HT transition from active → cancelled for domain D:
  if D.qualifies_for_cancellation_at IS NOT NULL AND D.qualifies_for_cancellation_at < detected_at:
    verdict = 'justified'
    evidence = {qualifies_at, reason}
  elif D.qualifies_for_cancellation_at IS NULL:
    verdict = 'unjustified'
    evidence = "no kill-trigger ever marked this domain for cancellation"
  else:
    verdict = 'unjustified'
    evidence = "kill-trigger fired AFTER the HT transition" — unusual case worth flagging separately
```

## Resolved (this chat, 2026-05-18)

### RESOLVED #1 — HT has no stable organization identifier

**Answer (verified against production HT API):** HT does NOT expose a stable organization ID. The full set of fields on `/orders/active` records is:

```
id, domain, status, paymentStatus, subscriptionId,
forwardingDomain, sendingTool, organizationName, productId, createdAt
```

`verify-revert` adds `currentStatus, toBeCancelled, clientEmail, revertible, reason, cancellationType` — still no org ID. `organizationName` is free text and observably plural per real customer.

**Implication:** the original DECISION 1 schema (`clients.hypertide_organization_id TEXT UNIQUE`) has no source to populate from. DECISION 1 has been revised to bind HT identity via `client_hypertide_subscriptions(subscription_id PK)` — Stripe's subscription ID is stable and is what HT actually keys billing on. `clients.primary_hypertide_organization_name TEXT` (nullable, non-unique) remains as a human label.

### RESOLVED #2 — Default `client_status` is `friends_and_family`

Promoted to **DECISION 5** above. Asymmetric error cost decided it: bad kill decisions are not recoverable; operator promotion is one UPDATE.

### RESOLVED #4 — Verdict is persisted at kill-evaluation time

Promoted to **DECISION 6** above. Options (1) and (2) can't faithfully answer "was this cancellation justified at the time the rules fired" — they have to re-derive a verdict from current rule state, which may have changed. Option (3) — persisted `qualifies_for_cancellation_at` — is the only honest answer.

### RESOLVED #5 — Domain-to-workspace routing rule

**Answer (verified against production HT API):** HT has no workspace ID, but two attributes ARE useful heuristics:

1. **`forwardingDomain`** — for Stable Kernel we empirically observed `stablekernel.com` vs `stablekernel.com/services/market-research` and they DO disambiguate the two SK workspaces. This is the strongest signal where the client has set distinct forwarding domains per workspace.
2. **`sendingTool` + workspace `provider`** — once DECISION 3 (workspaces.provider) is live, `sendingTool='Email Bison'` routes to `provider='emailbison'` workspaces under the client. Strong signal for Ink'd (one workspace per provider).

**Routing rule (in priority order):**

```
1. If a workspace under the client has a forwarding_domain_pattern that
   matches ht_rec.forwardingDomain → that workspace
2. Else if exactly one workspace under the client has provider matching
   the sendingTool→provider map → that workspace
3. Else operator-decided at first ingest, persisted as an explicit
   (hypertide_record_id → workspace_id) mapping so the choice doesn't
   need to be re-made on each audit
```

Implementation requires adding `workspaces.forwarding_domain_pattern TEXT` and a `domain_workspace_overrides(hypertide_record_id PK, workspace_id)` table (the latter optional — could be inline on `domains` if operator overrides are rare).

## OPEN questions / decisions still needed

### OPEN #3 — Instantly extraction sequencing

The change-tracking design's justification evaluator requires our domain-state rules to have a verdict. Those rules read inbox health from `sender_accounts`. For Ink'd, `sender_accounts` is empty/dead because the real infra is on Instantly, which we don't sync.

Until Instantly extraction is built AND DECISION 6's `qualifies_for_cancellation_at` write path is wired into the kill evaluator, Ink'd domain transitions will land in the `unjustified` verdict bucket (per DECISION 6's logic: "no kill-trigger ever marked this domain for cancellation" — because no rules ever ran). Operationally useless for the case that motivated this work.

**Decision needed**: is Instantly extraction in scope for this work, or scheduled separately? If separately, we ship a tracker that can't answer the Ink'd question — knowingly. **Recommendation:** ship the tracker anyway (captures data we don't have today; can re-derive verdicts retroactively once Instantly extraction lands), but label the Ink'd verdicts as `verdict='evaluator_unavailable'` for now to distinguish from real `unjustified` cases.

### OPEN #6 — `manages_via_hypertide` cleanup (`is_legacy` resolved per Concern C)

`workspaces.manages_via_hypertide` becomes redundant under the new model: `client_status NOT IN ('friends_and_family', 'inactive')` is the new filter (carried by the `v_operational_*` views per DECISION 2 revised).

Recommend a follow-up migration to drop `manages_via_hypertide` after the new fields are populated and code references migrated to the views.

**`domains.is_legacy` is NOT dropped** (revised per Concern C). Its original semantic — "domain acquired outside the HT pipeline" — is a sourcing/lifecycle attribute, NOT a F&F flag. Only the misuse for F&F detection goes away.

## What this changes in current docs and code

| Document / file | What changes |
|---|---|
| [docs/architecture/hypertide-service.md](../architecture/hypertide-service.md), "Parity model" section (lines 22-29) | Superseded by DECISION 2 (F&F as positive tag, sync all subscriptions) |
| [docs/architecture/hypertide-service.md:50-51](../architecture/hypertide-service.md#L50-L51) | "Brittle when an org operates across multiple workspaces" footnote is upgraded to first-class model per DECISION 1 |
| [apps/hypertide-worker/HANDOFF.md](../../apps/hypertide-worker/HANDOFF.md) | Add change-tracking runbook section; revise manual interventions section for client-level tagging + `client_hypertide_subscriptions` operator workflow |
| [apps/hypertide-worker/src/hypertide_worker/audit.py:126-141](../../apps/hypertide-worker/src/hypertide_worker/audit.py#L126-L141) | F&F vs incoming split branch removed — replaced by client-status filter at read time |
| [apps/hypertide-worker/src/hypertide_worker/audit.py:223-249](../../apps/hypertide-worker/src/hypertide_worker/audit.py#L223-L249) | Per-domain UPDATE loop now also reads/writes `client_hypertide_subscriptions` (binding new sub IDs to clients-with-default-F&F) |
| [apps/hypertide-worker/src/hypertide_worker/backfill.py:208-225](../../apps/hypertide-worker/src/hypertide_worker/backfill.py#L208-L225) | The hardcoded `suffix_map` workspace-name matcher (Spout, Selery, etc.) is replaced by the RESOLVED #5 routing rule: forwardingDomain → sendingTool+provider → operator-decided override |
| [api/models/client.py:88-167](../../api/models/client.py#L88-L167) | `Client`, `ClientCreate`, `ClientUpdate`, `LinkWorkspaceRequest` all change to reflect 1:many client→workspaces; new `client_status` field; `workspace_id` field removed |
| [api/routes/clients.py](../../api/routes/clients.py) | All `workspace_id` reads/writes migrate to the new FK direction; `LinkWorkspaceRequest` semantics change to "attach workspace to client" |
| **all operational queries on `clients`/`workspaces`/`domains`** (kill triggers, rotation, dashboards, health, reports) | Migrate reads to the new `v_operational_*` views (Concern A) — switching default failure mode from "forgot to filter F&F" to "had to opt in to see F&F" |
| **kill-trigger evaluator** (wherever the rule engine commits a domain-burn decision — see `docs/KILL-TRIGGERS.md` for the rules, code path not yet located in this plan) | Add the UPDATE that writes `domains.qualifies_for_cancellation_at` + `qualifies_for_cancellation_reason` per DECISION 6 |

## Implementation sequencing (revised 2026-05-18)

1. ~~Resolve OPEN #1, #2, #4, #5~~ — **done in this pass**; positions baked in.
2. Ratify or push back on the revised DECISIONS 1-6 with operator owner.
3. ~~Schema migration (DECISION 1 revised)~~ — **applied to prod 2026-05-18 as [`migrations/123_hypertide_data_model_rework.sql`](../../migrations/123_hypertide_data_model_rework.sql)**. Adds `clients.client_status` + `primary_hypertide_organization_name`, `workspaces.client_id` + `provider` + `forwarding_domain_pattern` + `workspaces_provider_check` CHECK, `client_hypertide_subscriptions` table, `v_operational_clients` / `_workspaces` / `_domains` views, and the DECISION 6 columns on `domains` (qualifies_for_cancellation_at + reason). Backfill landed 19/20 workspaces with `client_id`; the 1 unmatched is "Deprecate" (EB workspace_id=21, no parent client — correctly excluded by `v_operational_workspaces`). All 19 existing clients defaulted to `client_status='client'`; `v_operational_clients` returns the same 19. Schema is additive — no DROP COLUMN, follow-up migration cleans up `clients.workspace_id` + `workspaces.manages_via_hypertide` per step 10.
4. ~~**Manual seed step**~~ — **shipped 2026-05-18**. [`scripts/seed_client_hypertide_subscriptions.py`](../../scripts/seed_client_hypertide_subscriptions.py) + [`migrations/124_chs_subscription_created_at.sql`](../../migrations/124_chs_subscription_created_at.sql). 211 chs rows landed (136 bound to existing clients, 16 EB/Instantly new clients, 26 F&F Smartlead, 33 chs into new clients). Variant merges (Ink'd / Sammy / Root Access / Stone→SPUI) cleaned up post-seed; 397 Digital + Bridge promoted to F&F, 4 inactive clients tagged. Final state: 53 clients (21 'client' + 28 F&F + 4 inactive); see [`docs/audits/2026-05-18-ht-seed-merge-candidates.md`](../audits/2026-05-18-ht-seed-merge-candidates.md).
5. ~~Switch `apps/hypertide-worker` ingest to subscription-keyed sync~~ — **shipped 2026-05-18**. [`apps/hypertide-worker/src/hypertide_worker/chs_sync.py`](../../apps/hypertide-worker/src/hypertide_worker/chs_sync.py) — `ensure_chs_rows()` walks every HT sub per audit, touches `last_seen_at` for known subs, classifies + INSERTs for first-sight by `sending_tool`. Legacy "no DB row = F&F" branch removed. 60→68 tests; mypy --strict + ruff clean. Deployed to Coolify 2026-05-18.
6. ~~Migrate operational reads to `v_operational_*` views~~ — **shipped 2026-05-18 (focused minimum)**. Originally framed as Concern A's "biggest risk item" with ~530 call sites; calibration showed most sites are id-keyed lookups (no leakage risk) or correctly admin-scoped (should see all clients). Actual leakage surface area was small. Concrete migrations:
   - [`migrations/132_v_operational_views_tighten.sql`](../../migrations/132_v_operational_views_tighten.sql) — `v_operational_workspaces` now ALSO filters `is_active=TRUE`, matching the existing sync_module pattern. `v_operational_domains` inherits transitively.
   - **sync_modules batch** (9 files): `health_checks`, `lifecycle_tag_sync`, `set_tag_sync`, `sync_oauth`, `workspace_sync_queue`, `slack_audit_v2`, `daily_snapshot`, `tag_op_worker`, `workspace_writes` — all `FROM workspaces WHERE is_active = TRUE` migrated to `FROM v_operational_workspaces`. Behavioral verification confirms identical 11-workspace result set today + future-proofs against operator-assigned F&F workspaces.
   - **api/routes/health.py** (1 file): `analyze_domain_capacity_impact()`'s 3 fleet-wide ESP aggregate queries migrated to `v_operational_domains`.
   - **NOT migrated** (intentional):
     - `apps/hypertide-worker/audit.py` — uses `manages_via_hypertide=TRUE` which includes is_active=FALSE workspaces (Checkout Components, Peaksave, Root Access, Ink'd — 134 HT-tracked domains). Different scope; migrates in step 10 cleanup.
     - Admin CRUD endpoints (`api/routes/{clients,workspaces,domains,subscriptions}.py`) — operators correctly need to see all rows including F&F.
     - Id-keyed lookups (`WHERE id = $1`) — no leakage risk.
     - Reports (`api/routes/reports.py`) — admin-consumed, financial-context reads stay on base tables.
7. ~~Add `domains.qualifies_for_cancellation_at` + `_reason` columns~~ — **shipped 2026-05-18 in migration 123** (combined with the schema rework).
8. ~~Wire kill-trigger evaluator to write the verdict columns~~ — **shipped 2026-05-18**. [`migrations/125_burn_writes_qualifies_for_cancellation.sql`](../../migrations/125_burn_writes_qualifies_for_cancellation.sql) updates the `burn_domain_and_promote()` SQL function to write the verdict atomically with `pool_status='burned'`. Python fallback in [`sync_modules/kill_processor.py`](../../sync_modules/kill_processor.py) mirrored. 32 historical pre-migration burns stay NULL; from-now-forward burns populate. Revert path (operator NULLs columns on resurrection) intentionally manual.
9. ~~Ship change-tracking trigger + `hypertide_status_events` table~~ — **shipped 2026-05-18**. [`migrations/126_hypertide_status_events.sql`](../../migrations/126_hypertide_status_events.sql) creates the event log; [`apps/hypertide-worker/src/hypertide_worker/change_detector.py`](../../apps/hypertide-worker/src/hypertide_worker/change_detector.py) detects cancellations + reappearances per audit pass. Verdict joins `domains.qualifies_for_cancellation_*` within last 90 days. "Worker-side detection" instead of PG trigger because triggers can't see external HT state. 8 new tests for verdict classifier.
10. Cleanup:
    - **10a — drop `workspaces.manages_via_hypertide`** — **shipped 2026-05-18** via [`migrations/133_drop_legacy_ht_columns.sql`](../../migrations/133_drop_legacy_ht_columns.sql) + commit. 4 worker code sites + 1 report query migrated from the per-workspace flag to a per-client `client_hypertide_subscriptions` EXISTS check (HT bills at the client/sub level — chs is more correct than the workspace flag). Views recreated to break the SELECT w.* dependency. Verified identical 673-domain audit scope pre/post.
    - **10b — drop `clients.workspace_id`** — **deferred to a focused follow-up session**. Six remaining call sites need migration first:
      - [`api/database.py`](../../api/database.py#L745-L850) `_backfill_charm_purchase_record` — 5 SQL reads of `c.workspace_id`; one-shot startup backfill for activatecharm.com, currently try/except wrapped (safe if column drops but rots silently). Migrate or delete.
      - [`api/routes/clients.py:278`](../../api/routes/clients.py#L278) — `workspace_id = client.workspace_id` reads the Pydantic field during client creation.
      - [`api/models/client.py`](../../api/models/client.py) — `Client`/`ClientCreate`/`ClientUpdate` Pydantic field. Needs to expose the new `workspaces` list relationship instead.
    - **Keep `domains.is_legacy`** per Concern C; its "acquired outside the HT pipeline" semantic still applies.

**Instantly extraction (OPEN #3)** is a separate workstream. If parallelized, can land between steps 5-9. If serial, the change-tracker ships with Ink'd verdicts labeled `'evaluator_unavailable'` until Instantly lands.

## Out of scope (deliberately)

- HT API endpoint details, request/response shapes, auth — see [[hypertide-api]].
- Phase 2 cancellation orchestration (operator UI, job queue) — see [[hypertide-service]] Phase 2.
- Phase 3 order assembly and charge gating — see [[hypertide-service]] Phase 3.
- Instantly integration design — separate work. This doc only reserves the schema slot.
- Slack alerting wiring — concrete channel / payload / rate-limit decisions belong in the implementation PR for DECISION 4, not this doc.
