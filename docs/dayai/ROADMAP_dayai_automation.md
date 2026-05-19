# Day.AI Automation — Roadmap

> Catalog of future automations built on the `dayai/` package and
> per-client GitHub repos. Each item lists what it does, which Day.AI
> tools it uses, what it writes to where, what unblocks it, and what
> unblocks if it ships.
>
> Sequenced roughly by dependencies. Items earlier in the doc unlock
> items later. Use this to pick what to build next.

---

## Anchor: what's live today (2026-04-24, updated 2026-05-18)

| Component | Status | Notes |
|---|---|---|
| `dayai/` Python package | ✅ shipped | OAuth refresh + MCP wrapper + typed client, read-only by contract |
| `dayai_watcher_worker.py` | ✅ shipped, deployed, polling | Detects closed-won every 10 min; `DETECT_ONLY=true` (stays this way — wiring is via reconciler, not watcher post) |
| Migration 093 (state + runs tables) | ✅ applied | Tracks per-opp detection + per-poll audit |
| `HireCharm/client-sammy` enrichment | ✅ proof-of-concept | Manual one-off via `scripts/dayai/synthesize_client_repo.py` |
| `client.md` frontmatter contract (v0.4) | ✅ defined, NOT yet on template | Lives only in `client-sammy` so far; template promotion pending |
| `HireCharm/client-template` v0.3 -> v0.4 | ⬜ pending | Promote the shape; backfill existing client repos against new template |
| `app_credentials` table + `github_app.py` helper | ⬜ pending | New Tier 1.0 — keystone for every downstream worker + the charm-email-os frontend |
| `client-repo-reconciler` worker (Option C) | ⬜ pending | Replaces the un-built `/api/clients/pending-from-dayai` endpoint. Doubles as backfill tool |
| Bulk repo creation for the 13 onboarded=true clients | ⬜ pending | Scope decided 2026-05-18 |
| charm-email-os Context + Assets UI pages | ⬜ pending | Per-client tabs reading + writing the repo directly via the GitHub App helper |

**Architectural decisions logged 2026-05-18** (see HANDOFF §9):
- Watcher wiring = Option C (reconciler worker, not API endpoint)
- PEM moves to DB (`app_credentials` table)
- charm-email-os reads/writes the repo directly, no mirror table
- First bulk scope = `onboarding_complete=true` clients

---

## Tier 1 — finishes the current pipeline (this is the immediate work)

> **Sequencing decided 2026-05-18:** 1.0 must ship first (keystone
> primitive). After that, 1.1 → 1.2 → 1.3 is the operationally
> tightest order (template fixed → tooling productionized → bulk run).
> 1.4 (reconciler) and 1.5 (meeting sync) follow once repos exist.
> 1.6 (charm-email-os UI) can land in parallel with 1.4/1.5 since it
> only needs 1.0 + 1.3.

### 1.0 PEM-in-DB + `github_app.py` helper — **keystone**
**Status:** designed in `SPEC_app_credentials.md`; not built.

**What it does**
Lands the `app_credentials` table + `api/services/credentials.py` +
`api/services/github_app.py`. Migrates the Charm Onboarder PEM from
local file to one DB row. Every downstream worker AND the charm-email-os
backend uses the `gh_client(pool)` helper for GitHub access — no more
PEM env vars.

**Writes to**
- `migrations/112_app_credentials.sql`
- `api/services/credentials.py` (~20 lines)
- `api/services/github_app.py` (~80 lines)
- One-time SQL INSERT to seed the PEM

**Unblocks** — literally every other Tier 1 item. No Coolify worker
or charm-email-os route can talk to GitHub until this ships.

**Effort estimate** — 3-4 hrs (migration + service modules + seed +
smoke test from a charm-api shell).

### 1.1 Promote `client.md` v0.4 to `HireCharm/client-template`
**Status:** content exists in `client-sammy`; not yet in template.

**What it does**
Updates `HireCharm/client-template` so new repos clone with the v0.4
frontmatter shape — every key present, values as `"{{PLACEHOLDER}}"`
(strings) or `null` (other types).

**Writes to**
- `HireCharm/client-template/client.md` (rewrite)
- `HireCharm/client-template/notes/contacts.md` (new skeleton)
- `HireCharm/client-template/notes/status.md` (new skeleton)
- `HireCharm/client-template/notes/insights.md` (new skeleton)
- `HireCharm/client-template/onboarding/dayai-opp.md` (new skeleton)

**Idempotency** — manual PR + merge.

**Unblocks** — bulk repo creation (Tier 1.3) can use straight template
substitution instead of post-hoc enrichment.

**Effort estimate** — 1-2 hrs (write + PR review).

### 1.2 Productionize synthesize/onboard scripts → `apps/client-repo-reconciler/`
**Status:** Sammy-hardcoded scripts exist in `scripts/dayai/`; need parameterization.

**What it does**
Promotes the two PoC scripts in `scripts/dayai/` into a real Python
module at `apps/client-repo-reconciler/`:
- Takes `charm_client_id` (and optionally `dayai_opp_id`) as input
- Fetches the clients row + workspace + EB workspace from charm-email-os DB directly
- Fetches the Day.AI opp via the existing `dayai/` package
- Renders the 5 enriched files
- Uses `github_app.gh_client(pool)` from Tier 1.0 — no hardcoded PEM path
- Creates repo from template if missing (via `POST /repos/HireCharm/client-template/generate`)
- Commits the files atomically via git-data API
- Marks `dayai_watcher_state.sent_to_charm_at` if applicable
- CLI mode (one-shot) + library mode (called by the worker in 1.4)
- Codifies the slug rule from `CONCEPT_client_repo.md` §11

**Writes to**
- `apps/client-repo-reconciler/` (new Python module)
- `Dockerfile.client-repo-reconciler` (new)
- `requirements-client-repo-reconciler.txt` (new)

**Unblocks** — Tier 1.3 (bulk run) and Tier 1.4 (worker mode).

**Effort estimate** — 4-6 hrs.

### 1.3 Bulk repo creation + enrichment for the 13 onboarded=true clients
**Status:** Sammy done as smoke test; 12+ others not done.

**Scope (decided 2026-05-18):** all clients with
`onboarding_complete=true` in the clients table. Excludes Test
Workspace + Charm itself. Day.AI data populates for the 4 with
matching closed-won opps; null for the other 9 (frontmatter contract
permits null).

**What it does**
Runs the productionized reconciler from Tier 1.2 in one-shot CLI mode
against each of the 13 clients:
1. Dry-run first: report what would be created vs. skipped
2. Live run: create repos + commit enriched files
3. Verify each repo: clone, parse `client.md` frontmatter, confirm
   contract compliance

**Idempotency** — skip if `HireCharm/client-<slug>` already exists.
(Sammy exists, will be skipped; the other 12 are net-new.)

**Unblocks** — Tier 1.5 (meeting sync) and Tier 1.6 (charm-email-os UI)
can target real repos. The bulk run also catches slug-rule edge cases
before they bite in the live `client-repo-reconciler` worker.

**Effort estimate** — 2-3 hrs (dry-run + live + verification).

### 1.4 `client-repo-reconciler` worker (Coolify-deployed, Option C)
**Status:** worker detects, nothing acts.

**What it does**
Long-running Coolify app that wraps the Tier 1.2 module in a poll loop:
1. Read `dayai_watcher_state WHERE sent_to_charm_at IS NULL`
2. For each unprocessed opp: run the synthesize/onboard flow
3. Mark `sent_to_charm_at` on success
4. Sleep N minutes, repeat

Matches the `dayai-watcher` deployment shape — separate Coolify app,
shared Postgres, no HTTP between them. Watcher stays a pure detector;
this worker handles the action half. The dead `post_to_charm_api`
code path in `dayai_watcher_worker.py` can be removed in a follow-up.

**Writes to**
- `apps/client-repo-reconciler/worker.py` (poll loop wrapper)
- Coolify app config (new service)

**Unblocks** — automatic onboarding when a deal closes in Day.AI.
No human-in-the-loop step.

**Effort estimate** — 3-4 hrs once Tier 1.2 ships (mostly Coolify
config + smoke test).

### 1.5 Meeting summary sync into client repos
**Status:** designed in `HANDOFF_client_repo_pipeline.md` §5; not built.

**What it does**
For each client repo, pulls Day.AI meeting recordings linked to the
client's organization, writes each as a markdown file in
`notes/meetings/YYYY-MM-DD_<title-slug>.md` with frontmatter +
summary + transcript.

**Day.AI tools used**
- `search_objects` with relationship filter:
  `where: { relationship: "attendee", targetObjectType: "native_organization", targetObjectId: <domain>, operator: "eq" }`
- `get_meeting_recording_context` per meeting for full transcript + summary

**Writes to**
`notes/meetings/*.md` in each `HireCharm/client-<slug>` repo.

**Idempotency** — file name is `YYYY-MM-DD_<title-slug>.md`. Skip if
already exists with the same `dayai_meeting_id` in frontmatter; otherwise
overwrite (for content drift, like an updated summary).

**Unblocks**
- AE prep flow (Flow B in `CONCEPT_client_repo.md` §5)
- Agent testing: clone any client repo, ask "what did the contact say in
  the last call?", agent finds the answer in `notes/meetings/`
- Cross-client analysis (Tier 3) — meetings are the raw input

**Effort estimate** — 4-6 hrs to ship and validate.

### 1.6 charm-email-os Context + Assets UI
**Status:** designed in `SPEC_charm_os_repo_access.md`; not built.

**What it does**
Adds two new tabs to `app/clients/[clientId]/` in charm-email-os:
- **Context** — file-explorer of markdown content in the client repo,
  with markdown preview + frontmatter sidebar
- **Assets** — grid of asset files with upload dropzone and soft-delete
  (move to `assets/.archived/`)

Backend routes per `SPEC_charm_os_repo_access.md` §3. Reads + writes
GitHub directly via the Tier 1.0 helper. No mirror table, no sync
worker. Caching deferred per spec §8.

**Writes to**
- `migrations/113_clients_context_repo.sql` (add `context_repo` column)
- `api/services/client_repo.py` (~150 lines)
- `api/routes/client_repo.py` (~120 lines)
- `charm-email-os/app/clients/[clientId]/context/` (frontend pages)
- `charm-email-os/app/clients/[clientId]/assets/` (frontend pages)

**Unblocks** — operators can browse client context inside the
dashboard they already use. Assets created in the UI flow into the
same repo workers write to.

**Effort estimate** — 8-12 hrs (backend ~4, frontend ~6).

---

## Tier 2 — bigger primitives and endpoints

### 2.1 ~~`/api/clients/pending-from-dayai` endpoint~~ — **rejected 2026-05-18**

Originally Tier 2.1. **Rejected** in favor of the reconciler worker
(Tier 1.4). Reasons logged in `HANDOFF` §6: couples synchronous GitHub
commits to an HTTP layer, requires building a new API surface only
this one worker would use, and inflates the API failure surface
without operational benefit.

The reconciler-worker pattern is the kept choice. Removed from active
roadmap; preserved here only so future readers know this path was
considered and why it was discarded.

### 2.2 `dayai/queries.py` — high-level query primitives
Pull common Day.AI lookup patterns into reusable functions in the package
so workers don't re-implement them.

Examples:
```python
async def meetings_for_organization(client, domain) -> list[Meeting]
async def meeting_full_context(client, meeting_id) -> MeetingTranscript
async def contacts_for_opp(client, opp_id) -> list[Contact]
async def opps_by_owner(client, owner_email) -> list[OpportunitySnapshot]
async def stage_history(client, opp_id) -> list[StageTransition]
```

**Used by** every Tier 1 + Tier 3 worker.

**Effort estimate** — 3-4 hrs (and grows incrementally with each new
worker).

### 2.3 Charm-side `dayai_sync_worker.py` — daily refresh worker
Long-running worker that refreshes per-client snapshots daily.

**What it does**
- For each row in `clients` table with `dayai_opp_id`:
  - Re-pull opp via Day.AI
  - Re-render `client.md`, `notes/status.md`, `notes/insights.md`,
    `notes/contacts.md` from current state
  - Compare to existing repo content; if changed, commit refresh
  - Update `last_synced` in frontmatter

**Schedule** — daily, off-peak (say 04:00 UTC).

**Idempotency** — content-diff before commit. If nothing changed, no
commit.

**Effort estimate** — 4-6 hrs.

### 2.4 `dayai_value_change_worker.py` — stage/field-change detector
Sister worker to dayai-watcher, but watches for OPP TRANSITIONS rather
than presence-in-stage.

**What it does**
- Polls opps in non-Closed-Won stages every N min
- Compares against `dayai_watcher_state.dayai_snapshot.properties.stageId`
- On change: writes to a new `dayai_stage_transitions` table + triggers
  appropriate downstream (Slack alert, repo update, etc.)

**Triggers built later** (Tier 3):
- "Deal moved to Negotiation" -> Slack notification
- "Deal moved to Lost" -> archive client repo? mark inactive? (policy decision)
- "Deal moved to Closed Won" -> already covered by dayai-watcher (consolidate? share state?)

**Effort estimate** — 4-6 hrs for the detector; per-trigger workers
separate.

---

## Tier 3 — automations that USE the per-client repos

These all assume Tier 1 is done (client repos exist and are enriched).

### 3.1 Slack daily digest per client
**What it does**
Every morning (06:00 client tz), posts a per-client digest in Slack:
- "Sammy: 3 new meetings, last contact 2 days ago, next step due today"
- Pulls from `client.md` frontmatter + `notes/status.md`
- Channel: `client.md`'s `slack_client_channel_id` field (currently
  null — separate work to populate)

**Reads from** — every client repo's frontmatter + status.md
**Writes to** — Slack (no repo writes)
**Effort** — 3-4 hrs.

### 3.2 Call prep generator
**What it does**
On AE command (e.g. via slash command `/prep sammy`):
1. Pull Day.AI for upcoming meetings (next 24 hrs)
2. Pull recent meeting transcripts from repo
3. Pull `notes/insights.md` for buyer voice + goals
4. Pull `feedback/` for accumulated rules
5. Compose prep doc, save to `notes/call-prep-<date>.md`
6. Post link in Slack

**Reads from** — Day.AI + client repo
**Writes to** — client repo (`notes/`) + Slack
**Effort** — 6-10 hrs (UX details vary).

### 3.3 Cross-client pattern analysis agent
**What it does**
Periodically (weekly?), agent reads across all `HireCharm/client-*` repos
and surfaces patterns:
- "3 clients raised concerns about cold-call attribution this week"
- "Construction-vertical clients are converging on Loom demos as next-step"
- "Two clients hit the same EmailBison rate limit on Wednesday"

**Reads from** — every client repo (`notes/insights.md`, recent meetings,
feedback/)
**Writes to** — `charm-kb/insights/CROSS_CLIENT_<date>.md`

This is one of the highest-leverage outputs — only possible BECAUSE
we have per-client context as parseable files.

**Effort** — 8-12 hrs (mostly prompt + agent design work).

### 3.4 Campaign generation triggered by Day.AI signal
**What it does**
When Day.AI flags an opp's `Next Step` as "Send outbound campaign,"
auto-generates draft via campaign-copywriting skill, opens PR on the
client repo for AE review.

**Reads from** — Day.AI Next Step field + `notes/insights.md` +
`feedback/` + `gtm/reports/` (prior campaign results)
**Writes to** — `gtm/campaigns/YYYY-MM-DD_<slug>/` in client repo as a PR
**Effort** — 12-16 hrs (depends on copywriting skill maturity).

### 3.5 Asset extraction pipeline
**What it does**
When AE drops a client-shared file in `assets/` (brand guide, deck,
spec PDF), an automation parses the file and writes structured
extracts to `notes/extracts/<asset-name>.md`.

**Reads from** — files in `assets/` (PDFs, decks, .md, etc.)
**Writes to** — `notes/extracts/`
**Effort** — 4-8 hrs (depends on file types).

### 3.6 Onboarding form sync
**What it does**
When a client submits the onboarding form (hosted at
`onboard.laviefatigue.com`), the submission lands in
`onboarding/form-<date>.md` in the client repo + triggers downstream
(charm-email-os DB update, Slack notify).

**Reads from** — onboarding form webhook
**Writes to** — client repo `onboarding/` + Slack + charm-email-os DB
**Effort** — 4-6 hrs.

---

## Tier 4 — cross-system orchestration (post-foundation)

### 4.1 Automatic Slack channel creation per new client
On client creation (Tier 1.4), also create a dedicated
`#client-<slug>` Slack channel, invite Charm team members, set topic
from `client.md`. Write back `slack_client_channel_id` to client.md
frontmatter.

### 4.2 Bison workspace -> client.md sync
When EmailBison creates a workspace, write the numeric ID back to
`client.md`. Currently a one-time lookup; should be a closing loop.

### 4.3 Coolify dashboard config per client
Some clients get custom dashboards. When provisioned via
`api/routes/clients.py:create_workspace_for_client`, write the
dashboard URL to `client.md.custom_dashboard_url`.

### 4.4 Hypertide workspace linkage
Same pattern for the Hypertide service. `hypertide_workspace_ref` field
in `client.md` populated when account provisioned.

### 4.5 Decision flow: closed lost
When a Day.AI opp moves to Closed Lost, what happens?
- Archive the client repo? (preserve, but mark inactive)
- Move workspace to read-only?
- Update `client.md.status: lost`?

Document the policy as a `decisions/DECISION_closed_lost_handling.md`
before building automation.

---

## Tier 5 — the "agentic agency" picture

The endpoint of this work: Claude Code is the operating layer for
agency work. Every routine task either runs as automation (Tiers 1-4)
or is invoked by an AE through a skill that has full context.

**What it looks like in practice**

```
AE: "Sammy is concerned about our cold-call attribution.
     Draft a response."

Claude Code:
  1. Loads `HireCharm/client-sammy` context (CLAUDE.md + client.md +
     last 5 notes/meetings + feedback/)
  2. Sees `notes/insights.md` mentions Sammy is on construction
     vertical + AirCall/HubSpot attribution is an open blocker
  3. Pulls last 3 meeting transcripts via dayai/queries.py to find
     direct quotes about the attribution issue
  4. Reads `feedback/feedback_word_optimize.md` to avoid banned words
  5. Drafts response using `.claude/skills/gtm/objection-handling/`
  6. Writes to `notes/responses/sammy-attribution-<date>.md`
  7. Returns the draft, points to source quotes for review

AE: edits, commits, sends. Decision logged in `decisions/` if novel.
```

This is only possible because:
- The repo has typed, discoverable context (Tier 1)
- Skills are versioned and admin-controlled (Tier 1.2)
- Day.AI is read-accessible via clean primitives (Tier 2.2)
- Automations have populated the shelves (Tiers 3.*)

**That's the long-term destination this Day.AI work serves.**

---

## Sequencing recommendation (updated 2026-05-18)

The new order, optimized for operationalizing across all clients (not
just proving on Sammy):

1. **Tier 1.0** — `app_credentials` + `github_app.py` (3-4 hrs) ✦ keystone
2. **Tier 1.1** — Promote template to v0.4 (1-2 hrs)
3. **Tier 1.2** — Productionize scripts → `apps/client-repo-reconciler/` (4-6 hrs)
4. **Tier 1.3** — Bulk create the 13 onboarded=true client repos (2-3 hrs)
5. **Tier 1.4** — Deploy `client-repo-reconciler` as Coolify worker (3-4 hrs)
6. **Tier 1.5** — Meeting summary sync (4-6 hrs)
7. **Tier 1.6** — charm-email-os Context + Assets UI (8-12 hrs)
8. **Tier 2.2** — `dayai/queries.py` primitives (3-4 hrs) — emerges from 1.5
9. **Tier 2.3** — Daily sync worker (4-6 hrs)

Total: ~32-47 hrs to fully autonomous pipeline + operator UI. Tier 1.6
can land in parallel with 1.4/1.5 once 1.0 + 1.3 are done (it only
needs the helper + repos to exist).

If you have ~1 day: just Tier 1.0. Unblocks everything else.

If you have ~3 days: Tier 1.0 → 1.1 → 1.2 → 1.3. Gets the 13 client
repos created and populated, even without the reconciler worker
running yet — the bulk command does the same work one-shot.

Tier 2+ items are incremental value-adds once Tier 1 is solid.
