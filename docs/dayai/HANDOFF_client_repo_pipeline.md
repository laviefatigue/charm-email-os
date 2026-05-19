# Day.AI -> Client Repo Pipeline — Handoff

> **Status as of 2026-04-24** (with architectural decisions logged
> 2026-05-18). This document is the entry point for anyone picking up
> the Day.AI client-repo pipeline work. Read it before touching
> `dayai/`, `dayai_watcher_worker.py`, or the `HireCharm/client-*` repos.
>
> **2026-05-18 update — load-bearing decisions made:**
>
> 1. Charm Onboarder GitHub App PEM moves from local file to a new
>    `secrets` DB table. Spec: `SPEC_secrets.md`.
> 2. Watcher wiring approach is **Option C** (separate reconciler
>    worker) — *not* Option A's charm-api endpoint as the original
>    text below suggests. See §6 for the updated rationale.
> 3. charm-email-os gains a per-client **Context** + **Assets** UI
>    fed directly from the repo via the GitHub App helper. Spec:
>    `SPEC_charm_os_repo_access.md`.
> 4. First bulk-pass scope: all clients with `onboarding_complete=true`
>    (~13). Day.AI data populates for the 4 with matching opps; null
>    for the rest. See `ROADMAP` Tier 1.3.
>
> **Next concrete step:** ship `secrets` + `github_app.py`
> (ROADMAP Tier 1.0). Without it, no Coolify worker and no
> charm-email-os route can talk to GitHub. After that: template v0.4
> promotion, then productionize the synthesizer/onboarder into
> `apps/client-repo-reconciler/`.

---

## 1. What's been built

Two halves of one pipeline, both proven in isolation, not yet wired together.

### Half A: `dayai-watcher` (live, polling, in `DETECT_ONLY` mode)

Long-running Python worker that polls Day.AI for opportunities in "won"
stages, diffs against Postgres state, and (when `DETECT_ONLY=false`) is
intended to trigger client onboarding.

**Status:** running healthy in Coolify; first poll captured 14 closed-won
opportunities; subsequent polls confirm dedup works.

### Half B: per-client GitHub repos (`HireCharm/client-<slug>`)

Each active client gets a private repo cloned from `HireCharm/client-template`
and enriched with real data from Day.AI + `charm-email-os` DB + EmailBison.
Identity lives in YAML frontmatter on `client.md` so any script can parse it.

**Status:** working example exists at `HireCharm/client-sammy`. Template
itself (`HireCharm/client-template`) has NOT yet been updated with the new
shape — promotion is pending.

### What ties them together

```
Day.AI Closed-Won transition (detected by Half A)
       |
       v
Create client record in charm-email-os clients table       <-- NOT YET WIRED
       |
       v
Create HireCharm/client-<slug> repo + enrich from sources  <-- Half B (manual today)
       |
       v
Sync meeting summaries into notes/meetings/*.md            <-- NEXT STEP
       |
       v
AE/Claude opens repo in VS Code, reads context             <-- where it pays off
```

The two halves work today; the connection between them is the next deliberate
build.

---

## 2. Architecture

### Reusable Day.AI package — `dayai/`

Anything that needs to read Day.AI goes through this package. Add new use
cases as sibling workers; do not re-implement OAuth or MCP elsewhere.

```
charm-email-os/dayai/
  __init__.py        # public exports: DayAIClient, OpportunitySnapshot
  auth.py            # OAuth2 refresh-token flow (POST /api/oauth)
                     # AccessTokenCache holds + auto-refreshes
  mcp.py             # JSON-RPC 2.0 wrapper around POST /api/mcp
                     # ALLOWED_TOOLS frozen set — read-only enforced
                     # in Python before requests leave the process
  client.py          # high-level async DayAIClient
                     # list_opportunities_in_stages, whoami, call_tool
  objects.py         # OpportunitySnapshot + normalize_opportunity
```

**Read-only by contract.** `dayai.mcp.ALLOWED_TOOLS` enforces this in code.
Adding a mutation tool requires explicit security review per
`charm-kb/docs/SECURITY_FOLLOWUPS.md` §2.3. The current allowlist is:

- `search_objects`
- `get_meeting_recording_context`  <-- needed for the next step
- `read_crm_schema`
- `keyword_search`
- `whoami`

### Worker — `dayai_watcher_worker.py`

Top-level worker module, matches the pattern of `emailbison_sync_worker.py`.

- Long-running async loop, polls every `POLL_INTERVAL_SECONDS` (default 600)
- Reads opportunities in stages listed in `WATCHED_WON_STAGE_IDS`
- For each opp:
  - First time seen -> insert into `dayai_watcher_state`, increment `newly_won`
  - Subsequent polls -> update `last_poll_saw_at` + `dayai_snapshot`
- Every cycle writes one row to `dayai_watcher_runs` (start, end, counts, errors)
- `DETECT_ONLY=true` (default): logs `detected_would_post` for each newly-won
  but does NOT POST to charm-api. Used during the 1-2 week observation window.
- `DETECT_ONLY=false`: POSTs to `CHARM_API_URL/api/clients/pending-from-dayai`
  — that endpoint does not exist yet (Gate 2 work).

### Schema — migration `093_dayai_watcher_state.sql` (applied)

Two tables:

- `dayai_watcher_state` — one row per opp ever observed in a watched stage.
  Primary key `opp_id`. Tracks first_seen, last_poll_saw, sent_to_charm,
  charm_client_id (FK-pending), full `dayai_snapshot` JSONB.
- `dayai_watcher_runs` — one row per poll cycle. Includes counts +
  error_messages array.

Both `IF NOT EXISTS`. Migration runner picks up automatically on charm-api
startup.

### Runtime image — `Dockerfile.dayai-watcher`

Minimal Python 3.11 + `httpx` + `asyncpg`. No browser, no Playwright. Long-
running `CMD ["python", "dayai_watcher_worker.py"]` — does not exit between
polls (this is the key fix for the restart loop the Node version hit).

Healthcheck verifies Postgres reachable.

---

## 3. Current deployed state (as of 2026-04-24)

### Coolify app: `dayai-watcher`

| Field | Value |
|---|---|
| UUID | `nockc840c0c0o084co44cwc4` |
| Project | Charm Email OS (`xccs4w0csw0kwwksc0wocgc4`) |
| Source | HireCharm Coolify GitHub App (source_id=3, UUID `d5c84ce1-d54b-4f6a-ab6d-98fa2cde3102`) |
| Repo | `HireCharm/charm-email-os` |
| Branch | `master` |
| Dockerfile | `/Dockerfile.dayai-watcher` |
| Base directory | `/` |
| Status | `running:healthy`, restart_count=0 |
| Mode | `DETECT_ONLY=true` |

### Env vars (already set on the Coolify app)

| Key | Source / notes |
|---|---|
| `DAY_AI_BASE_URL` | `https://day.ai` |
| `CLIENT_ID` | Day.AI OAuth — `d:/Work/Charm/.secrets/dayai-oauth.env` |
| `CLIENT_SECRET` | same |
| `REFRESH_TOKEN` | same |
| `WATCHED_WON_STAGE_IDS` | `bef2d697-5f90-4b8e-a421-b6ee3e359aed` (Closed Won) |
| `POSTGRES_HOST` | `dgg04wg80480s4w8w84owg0c` (internal hostname) |
| `POSTGRES_PORT` | `5432` |
| `POSTGRES_DB` | `postgres` |
| `POSTGRES_USER` | `charm` |
| `POSTGRES_PASSWORD` | copied from charm-api's env |
| `CHARM_API_URL` | `https://api.wizardgrimoire.cloud` |
| `CHARM_API_TOKEN` | empty (only required when `DETECT_ONLY=false`) |
| `DETECT_ONLY` | `true` |
| `LOG_LEVEL` | `info` |

### First poll log evidence

```
poll start detect_only=True stage_ids=1
fetched 14 opportunities across 1 stage(s)
detected_would_post x 14 (Poolify, ottoresults, searchatlas, stablekernel,
  messagewecare, stellargrowth, workwithvermamedia, barrenabranding,
  carabinercomms, astragtm, withsammy, krishnapryor, unileadlabs, didin)
poll end seen=14 newly_won=14 sent_to_charm=0 errors=0
```

### Database state

Run from the postgres terminal in Coolify (or any psql with `charm` creds):

```sql
SELECT COUNT(*) FROM dayai_watcher_state;
-- expected: 14 (until new closed-won transitions occur)

SELECT opp_id, first_seen_at, sent_to_charm_at, dayai_snapshot->>'title'
  FROM dayai_watcher_state
  ORDER BY first_seen_at DESC LIMIT 5;

SELECT id, started_at, ended_at, opportunities_seen, newly_won, errors
  FROM dayai_watcher_runs
  ORDER BY started_at DESC LIMIT 10;
```

---

## 4. The client-repo half (worked example: `HireCharm/client-sammy`)

### What the template provides today

`HireCharm/client-template` (marked `is_template: true`) ships with:

- `CLAUDE.md` — Foam orchestrator with documentation protocol
- `README.md` — AE-facing entry point
- `client.md` — identity card (currently uses literal `TBD` values)
- `dashboard/`, `decisions/`, `docs/`, `feedback/`, `gtm/`, `notes/`, `onboarding/`, `assets/` — content shelves
- `.claude/skills/gtm/` — admin-controlled skill library (campaign-copywriting,
  campaign-strategy, personalization patterns)
- One literal `{{CLIENT_NAME}}` placeholder across 5 files (9 instances total)

### What `client-sammy` looks like after enrichment

The Sammy repo demonstrates the target shape. Visit
`https://github.com/HireCharm/client-sammy`. Two key adds beyond the
template:

1. **`client.md` rewritten** with YAML frontmatter as the canonical
   machine-readable identity record:

   ```yaml
   ---
   # Identity (seeds for downstream automation: workspace naming, domain generation)
   slug: "sammy"
   domain: "withsammy.ai"
   organization_name: "UBUILDA PTY LTD"

   # Charm OS IDs (UUID strings)
   charm_client_id: "4ac7f374-8751-4d89-8017-7dfca23fb5f8"
   charm_workspace_id: "bbfee135-bff8-4b02-9270-e7946725ab14"

   # EmailBison (NUMERIC ID — used in EB API URLs)
   emailbison_workspace_id: 8
   emailbison_workspace_name: "Sammy"

   # Day.AI (UUID strings)
   dayai_opp_id: "4ebe8c77-fa12-4df9-84d2-733725aa186a"
   dayai_organization_id: "withsammy.ai"
   dayai_owner_user_id: "287e7365-cf31-4578-b3fa-6024f6b30c31"
   dayai_owner_email: "chris@hirecharm.com"

   # Dates (ISO 8601)
   closed_won_date: "2026-02-23"
   onboarded_date: "2026-01-14"
   last_contacted_date: "2026-04-20"
   next_step_date: "2026-04-20"

   # Primary contact (parsed from Day.AI roles array)
   primary_contact_name: "Krishna"
   primary_contact_email: "krishna@withsammy.ai"
   primary_contact_roles: ["PRIMARY_CONTACT", "CHAMPION", "SUPPORTER"]

   # ... (package state, slack/hypertide keys present even when null, etc.)
   ---
   ```

2. **Four new files** generated from Day.AI data:
   - `notes/contacts.md` — full roster (5 client / 2 Charm / 4 external) with role assignments
   - `notes/status.md` — current deal status + risks + next step
   - `notes/insights.md` — Buyer Voice (client quotes), Goals, Decision Process, Competitors
   - `onboarding/dayai-opp.md` — audit snapshot with summary table + truncated raw JSON

### The frontmatter contract (binding for parsers)

Every key listed in the Sammy `client.md` frontmatter must stay present in
all client.md files going forward. Use `null` for unfilled values — do not
omit. This keeps `frontmatter.load("client.md")["slack_client_channel_id"]`
from raising `KeyError`.

```python
import frontmatter
data = frontmatter.load("client.md")
data["emailbison_workspace_id"]   # 8 — int, ready for EB API URLs
data["domain"]                     # "withsammy.ai" — seed for domain gen
data["primary_contact_email"]      # "krishna@withsammy.ai"
data["dayai_opp_id"]              # UUID — for Day.AI joins
data["slack_client_channel_id"]   # None — fill later
```

### Pending: promote the shape to `HireCharm/client-template`

What needs to happen before bulk rollout:

1. Open a PR against `HireCharm/client-template` that:
   - Rewrites `client.md` to the new frontmatter shape with every value as
     either `"{{PLACEHOLDER}}"` (strings) or `null` (so the template still
     parses as YAML)
   - Adds `notes/contacts.md`, `notes/status.md`, `notes/insights.md`,
     `onboarding/dayai-opp.md` as skeleton templates
   - Bumps `template_version` to `0.4`
2. Update `scripts/dayai/onboard_client_repo.py` (in this folder) to
   parameterize what's currently hardcoded for Sammy.

---

## 5. NEXT STEP (the work this handoff exists to enable)

> Extract Day.AI meeting recording summaries into per-client repos, then
> verify a Claude Code agent can fetch + analyze them.

### Day.AI MCP tool to use

`get_meeting_recording_context` — already in the allowlist.

Input shape (based on the SDK signature and the Node watcher's exploration):

```json
{
  "objectId": "<meeting-uuid>"
}
```

But meetings aren't usually known in advance — they need to be discovered.
Two viable discovery paths:

**Path A: find meetings via opp relationships.**
The Day.AI opp has 17+ relationships (we saw them on Sammy). Among them are
contacts; meetings are typically attached to contacts and organizations as
`native_meetingrecording` objects. Use `search_objects` with a relationship
filter:

```python
await client.call_tool("search_objects", {
    "queries": [{
        "objectType": "native_meetingrecording",
        "where": {
            "relationship": "attendee",
            "targetObjectType": "native_organization",
            "targetObjectId": "<client-domain>",  # e.g. "withsammy.ai"
            "operator": "eq"
        }
    }],
    "propertiesToReturn": "*",
    "includeRelationships": True
})
```

**Path B: find meetings via organization domain.**
Iterate `native_organization` -> meetings. Useful for backfill across multiple
clients.

Either path returns a list of meeting summary objects. For full transcripts,
call `get_meeting_recording_context` per meeting.

### Where the meetings go in the repo

Proposed layout (not yet enforced — adopt or adjust):

```
notes/
  meetings/
    YYYY-MM-DD_<slug-of-title>.md
    YYYY-MM-DD_<slug-of-title>.md
    ...
```

Each meeting file:

```markdown
---
name: <meeting title>
type: meeting
created: <recording date>
dayai_meeting_id: <UUID>
dayai_meeting_url: <Day.AI permalink>
attendees: ["jane@client.com", "chris@hirecharm.com", ...]
duration_minutes: 45
related: ["[[client]]", "[[contacts]]", "[[insights]]"]
---

# <meeting title>

**When:** <ISO date>
**Attendees:** Jane Doe (client.com), Chris Booth (hirecharm.com)

## Summary

<Day.AI's generated summary — usually present>

## Action items

<Day.AI's action item list if any>

## Transcript

<transcript text — long, hence trailing position>
```

### Suggested implementation outline

A new module — start in `dayai/queries.py` since the operation is reusable
(future automations beyond client repos will want meeting data too).

```python
# dayai/queries.py (new file)

from .client import DayAIClient

async def meetings_for_organization(
    client: DayAIClient, domain: str
) -> list[dict]:
    """Find native_meetingrecording objects where the organization
    (keyed by domain) is an attendee. Returns list of meeting summary
    dicts as Day.AI returns them."""
    result = await client.call_tool("search_objects", {
        "queries": [{
            "objectType": "native_meetingrecording",
            "where": {
                "relationship": "attendee",
                "targetObjectType": "native_organization",
                "targetObjectId": domain,
                "operator": "eq"
            }
        }],
        "propertiesToReturn": "*",
        "includeRelationships": True
    })
    bucket = result.get("native_meetingrecording") or {}
    return bucket.get("results") or []


async def meeting_full_context(
    client: DayAIClient, meeting_id: str
) -> dict:
    """Fetch full meeting context including transcript via the dedicated
    MCP tool. Returns the raw payload (caller normalizes for display)."""
    return await client.call_tool(
        "get_meeting_recording_context", {"objectId": meeting_id}
    )
```

Then a new worker or one-shot script (start as a script under
`scripts/dayai/`, promote to worker once stable):

```python
# scripts/dayai/sync_meetings_to_client_repo.py (sketch)

async def sync_one_client(charm_client_id: str):
    # 1. Read client.md frontmatter from HireCharm/client-<slug>
    #    via GitHub API to get domain + dayai_opp_id
    # 2. dayai = DayAIClient.from_env()
    # 3. meetings = await meetings_for_organization(dayai, domain)
    # 4. for each meeting:
    #      full = await meeting_full_context(dayai, meeting["objectId"])
    #      build markdown
    #      check if file exists in repo (by slug + date)
    #      if not, add to a batched commit
    # 5. Commit all new meeting files atomically via git-data API
    #    (reuse pattern from scripts/dayai/onboard_client_repo.py)
```

Idempotency: name files deterministically
(`YYYY-MM-DD_<title-slug>.md`) and skip if already in the repo.

Rate limits: Day.AI is generous in observation but be mindful — sleep
~200ms between `get_meeting_recording_context` calls. For 14 clients with
maybe 5-20 meetings each, total ~200 calls, ~40 seconds.

### Testing with an agent (the validation step)

Once meetings land in `client-sammy/notes/meetings/`:

1. Clone `HireCharm/client-sammy` locally
2. Open in Claude Code
3. Ask an agent something only meetings would answer, like:
   - "What pain points has Sammy raised about their existing sales tooling?"
   - "Who from Sammy attended the most meetings? What's their role?"
   - "When did we last discuss the AirCall->HubSpot attribution issue?"
4. Confirm the agent finds answers by reading
   `notes/meetings/*.md` files (not making things up).

This validates the whole pipeline end-to-end: Day.AI -> repo -> AE
context. **That's the goal.**

---

## 6. Open gotchas + things the next session needs to handle

### Slug strategy for tricky names

DB has names like `Ink'd`, `Stable Kernel Market Research`, and a duplicate
`Stable Kernel`. Slug rule used so far for Sammy: lowercase, strip
non-alphanumeric, hyphen-separate. Codify before bulk rollout.
Suggested algorithm in `scripts/dayai/onboard_client_repo.py`.

### Tying watcher detection -> repo creation — **decided 2026-05-18: Option C**

The watcher detects newly-won opps but does nothing with that signal
beyond logging. Three options were on the table:

- **A**: when `DETECT_ONLY=false`, POST to charm-api's
  `/api/clients/pending-from-dayai` endpoint (does not exist yet).
  Endpoint inserts into clients table + calls a GitHub service to
  create the repo. **Rejected** because it couples a synchronous
  GitHub commit (slow, can fail) to an HTTP-layer API endpoint, and
  because it requires building a new API surface we don't otherwise
  need.
- **B**: watcher calls a Python function directly. **Rejected**
  because it bloats the watcher container with GitHub commit logic
  + the PEM credential surface area, when the watcher should stay a
  pure detector.
- **C** ✅: separate `client-repo-reconciler` worker. Reads
  `dayai_watcher_state WHERE sent_to_charm_at IS NULL`, runs the
  productionized synthesize/onboard flow, marks done. Doubles as the
  backfill tool for the existing 14 opps. Watcher stays a pure
  detector. New focused Coolify app — matches the "modular micro-SaaS
  sharing one DB" pattern.

`DETECT_ONLY=true` stays as-is permanently. The watcher's "post to
charm-api" code path becomes dead code we can remove in a follow-up.

Implementation lands as ROADMAP Tier 1.4. See `SPEC_secrets.md`
for the auth primitive the reconciler depends on.

### Bulk rollout for existing clients

19 clients in DB (1 is "Test Workspace", 1 is "Charm" = HireCharm itself).
14 closed-won opps in Day.AI. Overlap: 4 (Search Atlas, Stable Kernel,
Barrena, Sammy). Decisions needed:

- Do we create repos for **all 18 real DB clients**, **just the onboarded=Y
  ones**, or **only those with matching Day.AI opps**?
- For DB-only clients (no Day.AI opp), what data populates `dayai_*` fields?
  Use `null` — the frontmatter contract permits.

### Day.AI API quota / rate limits

Not measured. Be conservative: sleep between calls in batch jobs. If hit:
back off + retry. The `dayai.mcp` layer already retries once on 401 (token
expiry).

### EmailBison numeric ID lookup

Use `GET /api/workspaces/{workspace_id_uuid}` -> response includes
`emailbison_workspace_id`. The clients endpoint does NOT include it directly.
This is a separate lookup per client.

### Template version tracking

`client.md` frontmatter has `template_version: "0.4"`. When the template
updates, automation should detect drift between client repos and the current
template version. Currently no enforcement — flag for future.

### Charm Onboarder GitHub App credentials — **migrating to DB 2026-05-18**

- App ID: `3480661`
- Installation ID on HireCharm: `126503394`
- Permissions: `administration: write`, `contents: write`, `members: write`,
  `organization_administration: write`, `pull_requests: write`
- PEM (current location): `d:/Work/Charm/.secrets/charm-onboarder.pem`
- PEM (target location after Tier 1.0 ships): `secrets` row
  with `name = 'charm_onboarder_github_app_pem'`
- All scopes needed for repo creation, file commits, and team management

Migration plan:
1. Ship `migrations/136_secrets.sql`
2. INSERT the PEM as one row (manual one-time from a trusted host)
3. Ship `api/services/credentials.py` + `api/services/github_app.py`
4. Every new service consuming GitHub uses the `gh_client(pool)`
   helper — never the file path
5. Local file at `d:/Work/Charm/.secrets/charm-onboarder.pem` becomes
   the offline backup; not used by any service

See `SPEC_secrets.md` for the full design (security trade-offs,
rotation procedure, future credentials that migrate here).

### Coolify Web Terminal limitation

The Coolify UI Terminal tab requires a WebSocket connection that fails from
Playwright/automation contexts. For interactive psql access, use a regular
browser (or charm-email-os's migration_runner for schema changes — preferred
path for migrations).

---

## 7. File index — where to look in this repo

| Path | What it is |
|---|---|
| `dayai/` | Reusable Day.AI client package (auth, MCP, client, objects) |
| `dayai_watcher_worker.py` | The watcher worker — long-running, polls every 10 min |
| `Dockerfile.dayai-watcher` | Image for the watcher; mirrors `Dockerfile.emailbison-sync` pattern |
| `requirements-dayai.txt` | httpx + asyncpg |
| `migrations/093_dayai_watcher_state.sql` | Schema (applied to prod) |
| `docs/dayai/HANDOFF_client_repo_pipeline.md` | This file |
| `docs/dayai/CONCEPT_client_repo.md` | Vision: per-client repos as context engines + four audiences |
| `docs/dayai/SPEC_secrets.md` | DB-stored PEM + `github_app.py` helper |
| `docs/dayai/SPEC_charm_os_repo_access.md` | charm-email-os Context/Assets UI direct access pattern |
| `docs/dayai/ROADMAP_dayai_automation.md` | Tiered build catalog |
| `scripts/dayai/synthesize_client_repo.py` | Reference: parameterize Sammy synthesizer |
| `scripts/dayai/onboard_client_repo.py` | Reference: atomic-commit helper using git-data API |
| `scripts/dayai/README.md` | Pointer to this handoff |

External / related references:

| Location | What it is |
|---|---|
| `HireCharm/client-template` | The template repo (needs promotion to v0.4 shape) |
| `HireCharm/client-sammy` | Worked example with full enrichment |
| `d:/Work/Charm/.secrets/dayai-oauth.env` | Day.AI OAuth creds |
| `d:/Work/Charm/.secrets/charm-onboarder.env` + `.pem` | GitHub App creds |
| `d:/Work/Charm/charm-kb/runbooks/RUNBOOK_coolify_dayai_watcher_deploy.md` | Original deploy runbook (predates Python pivot — read with caveats) |
| `d:/Work/Charm/charm-kb/docs/SECURITY_FOLLOWUPS.md` | Security policies including the read-only Day.AI binding |

---

## 8. Quick recipes (copy-paste useful)

### Run a one-shot poll manually (for debugging)

```bash
# From inside the dayai-watcher container's terminal (Coolify UI Terminal tab,
# in a regular browser since WebSocket is needed):
python dayai_watcher_worker.py --once
```

### Re-pull Sammy's full Day.AI snapshot

```python
import asyncio, os
from dayai import DayAIClient

# env vars loaded as usual from .env or process env
async def main():
    async with DayAIClient.from_env() as client:
        identity = await client.whoami()
        print(identity)
        opps = await client.list_opportunities_in_stages(
            ["bef2d697-5f90-4b8e-a421-b6ee3e359aed"]
        )
        for opp in opps:
            print(opp.id, opp.title, opp.domain)

asyncio.run(main())
```

### Check what's in `dayai_watcher_runs` (via charm-api psql terminal)

```sql
SELECT id, started_at, ended_at - started_at AS duration,
       opportunities_seen, newly_won, sent_to_charm, errors
  FROM dayai_watcher_runs
  ORDER BY started_at DESC LIMIT 20;
```

### Add a new MCP tool to the allowlist

Edit `dayai/mcp.py`:

```python
ALLOWED_TOOLS: frozenset[str] = frozenset({
    "search_objects",
    "get_meeting_recording_context",
    "read_crm_schema",
    "keyword_search",
    "whoami",
    "<new_tool_name>",  # add here; requires security review per SECURITY_FOLLOWUPS §2.3
})
```

Mutation tools (anything `create_*`, `update_*`, `delete_*`, `send_*`,
`batch_*`) are prohibited by policy — read-only only.

---

## 9. Decisions log (chronological, this work)

| Date | Decision | Why |
|---|---|---|
| 2026-04-23 | Use HireCharm/dayai-watcher (Node) as first attempt | Existing Day.AI SDK is TypeScript; quickest path to first detection |
| 2026-04-24 | Pivot to Python module in charm-email-os | Node version's Dockerfile CMD was one-shot; Docker restart-looped on first deploy (~10 polls/min). Architectural mismatch: separate repo + scheduled-task expectation vs. Coolify's running-container model. Python rewrite matches the emailbison_sync pattern, shares DB pool, single repo. |
| 2026-04-24 | Read-only at code level (ALLOWED_TOOLS frozenset) | Day.AI scope minimization deferred; code-level enforcement is primary control per SECURITY_FOLLOWUPS §2.3 |
| 2026-04-24 | client.md frontmatter = canonical machine-readable record | Per user feedback: values must be usable as DB-style typed seeds for downstream automation (workspace naming, domain generation). YAML frontmatter beats prose for parser consumption. |
| 2026-04-24 | EmailBison workspace ID stored as NUMERIC | `emailbison_workspace_id: 8`, not the local UUID. The numeric ID is what EB API URLs use. |
| Pending | Promote v0.4 client.md shape to HireCharm/client-template | Done currently only on client-sammy; not yet in the template itself |
| 2026-05-18 | Watcher wiring = Option C (separate reconciler worker) | Avoids coupling client-row creation to synchronous GitHub commit in API layer; watcher stays a pure detector; reconciler doubles as backfill tool for the 14 existing opps |
| 2026-05-18 | Bulk rollout scope = all `onboarding_complete=true` clients (~13) | Day.AI data populates for the 4 with matching opps; null for the rest. Establishes the repos as the spine without forcing field-invention for missing-side cases |
| 2026-05-18 | Move Charm Onboarder PEM to `secrets` DB table | Enables Coolify workers AND charm-email-os backend to mint installation tokens from a single source; matches the modular-micro-SaaS-sharing-one-DB pattern; precedent set by `workspace_api_keys` table |
| 2026-05-18 | charm-email-os Context + Assets UI reads/writes repo directly (no cache) | Repo is source of truth; charm-email-os is a thin operator surface. GitHub rate limit (5k/hr) has plenty of headroom for internal AE traffic. Caching layer documented in `SPEC_charm_os_repo_access.md` §8 as future work if pressure appears |
| 2026-05-18 | EmailBison report-to-repo cron designed now, built after Tier 1 | Performance metrics + conversations need to live side-by-side in the repo for the "marry them" agent flow, but Tier 1 (repos exist + populated) must ship first |

---

## 10. Glossary

- **Day.AI** — AI-native CRM where Charm tracks deals. Provides MCP-over-HTTP for read access.
- **MCP** — Model Context Protocol. Day.AI exposes its tools (search_objects, etc.) over JSON-RPC 2.0 at `/api/mcp`.
- **Closed Won stage** — Day.AI pipeline stage with UUID `bef2d697-5f90-4b8e-a421-b6ee3e359aed`. Polling target for the watcher.
- **Charm Onboarder App** — GitHub App in HireCharm org with write scope. Used to create client repos from template.
- **HireCharm Coolify App** — separate GitHub App with read-only scope. Used by Coolify to clone HireCharm repos for builds.
- **Foam** — VS Code extension for wiki-link knowledge graphs. The client repos use Foam conventions for cross-references.
- **DETECT_ONLY** — env var on the watcher. `true` = observe + log only; `false` = actually POST to charm-api.
- **Frontmatter contract** — the keys defined in `client.md`'s YAML header. Stable; all keys present even when null.

---

## End

If anything in here is wrong or unclear, fix it in place and commit. This
file is the entry point for the next person picking up the work, including
future-you.
