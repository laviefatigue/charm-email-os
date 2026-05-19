# Schema — Client Repo File Types

> Authoritative spec for every file type that lives in a
> `HireCharm/client-<slug>` repo. Anything writing a file (human or
> automation) MUST follow the schema. Anything reading a file MAY
> rely on it.
>
> Paired with `CONCEPT_client_repo.md` (vision) and
> `HANDOFF_client_repo_pipeline.md` (technical handoff).
>
> When you add a new file type, document it here in the same PR. When
> you change a schema, bump `template_version` in `client.md` and
> document the migration path.

---

## 1. The frontmatter contract (universal)

Every `.md` file in a client repo opens with YAML frontmatter. Minimum
keys for ALL types:

```yaml
---
name: <human-readable title>
description: <one-line purpose — shown to Claude when deciding relevance>
type: <one of the types below>
created: YYYY-MM-DD
status: <draft|active|superseded|stub|cross-ref>
related: ["[[other-doc]]", "[[another]]"]
---
```

Per-type frontmatter extends this base. The `type` field is the dispatch
key — agents and automations route behavior by it.

### Universal frontmatter rules

1. **Keys defined in the schema are required, even when null.** Don't
   omit keys; use `null` or `""` so parsers don't break on `KeyError`.
2. **String values that contain `:` or `[`** must be JSON-quoted in
   YAML: `description: "Why we chose Approach A: tradeoffs"` not bare.
3. **Lists are inline JSON arrays:** `tags: ["dayai", "meeting"]`. Avoid
   the dash-list form in frontmatter — harder for some parsers.
4. **Dates are ISO 8601:** `created: 2026-04-24` (date-only OK) or
   `created: "2026-04-24T18:00:00Z"` (full datetime quoted).
5. **`related` is required and SHOULD have at least one link.** Empty
   `related: []` means the doc is an orphan — usually a smell.

---

## 2. Type catalog

The known types, with the canonical location and schema for each. New
types add a row here in the same PR.

| `type` | Location | Owner | Schema section |
|---|---|---|---|
| `client-card` | `/client.md` (one per repo) | onboarding flow + daily sync | §3 |
| `index` | `/README.md` (one per repo) | template | §4 |
| `guide` | `/CLAUDE.md`, `dashboard/CLAUDE.md`, `gtm/CLAUDE.md`, etc. | template | §5 |
| `meeting` | `notes/meetings/*.md` | meeting sync worker (Tier 1.1) | §6 |
| `reference` | `notes/contacts.md`, `notes/status.md`, `notes/insights.md`, `onboarding/dayai-opp.md`, `docs/REFERENCE_*.md` | daily sync worker / onboarding flow | §7 |
| `note` | `notes/*.md` (free-form, including handoffs, call-prep) | AE (humans) | §8 |
| `transcript` | `notes/transcripts/*.md` | Day.AI sync / manual paste | §9 |
| `feedback-rule` | `feedback/feedback_*.md` | AE (humans) | §10 |
| `decision` | `decisions/DECISION_*.md` | AE (humans) | §11 |
| `campaign` | `gtm/campaigns/<date>_<slug>/` (folder, multiple files) | gtm skill | §12 |
| `report` | `gtm/reports/<date>_<slug>.md` | EmailBison cron (Tier 3) | §13 |
| `list` | `gtm/lists/<date>_<slug>/` (folder, CSVs + meta) | sourcing run | §14 |
| `onboarding-submission` | `onboarding/form_<date>.md` | onboarding form sync (Tier 3.6) | §15 |
| `asset` | `assets/<filename>` (raw files) | AE (humans) | §16 |

---

## 3. `client-card` — `/client.md`

The canonical machine-readable identity record. Most elaborate schema.

### Frontmatter

```yaml
---
# Foam metadata
name: "<client display name>"
type: "client-card"
status: "active"
created: <onboarded_date>
related: ["[[CLAUDE]]", "[[README]]", "[[contacts]]", "[[status]]", "[[insights]]", "[[dayai-opp]]"]

# Identity (seeds for downstream automation)
slug: "<slug>"                              # lowercase, hyphenated; matches repo name
domain: "<primary domain>"                   # seed for similar-domain generation
organization_name: "<legal entity>"          # from Day.AI

# Charm OS IDs (UUID strings)
charm_client_id: "<uuid>"                    # clients.id
charm_workspace_id: "<uuid>"                 # clients.workspace_id (local UUID)

# EmailBison (NUMERIC ID — used in EB API URLs)
emailbison_workspace_id: <int>               # NOT a UUID
emailbison_workspace_name: "<string>"
emailbison_sender_account_count: <int>

# Day.AI (UUID strings or domain-keyed strings)
dayai_opp_id: "<uuid>"
dayai_organization_id: "<domain>"            # Day.AI often uses domain as objectId
dayai_owner_user_id: "<uuid>"                # Charm AE's Day.AI user UUID
dayai_owner_email: "<email>"

# Dates (ISO 8601 date-only)
closed_won_date: "YYYY-MM-DD"
onboarded_date: "YYYY-MM-DD"
last_contacted_date: "YYYY-MM-DD"
next_step_date: "YYYY-MM-DD"

# Primary contact (parsed from Day.AI roles array)
primary_contact_name: "<string>"
primary_contact_email: "<email>"
primary_contact_roles: ["PRIMARY_CONTACT", "CHAMPION", ...]

# Charm OS package state (clients row snapshot)
package_name: "<string>"
package_inbox_target: <int>
inbox_count: <int>
connected_inbox_count: <int>
domain_count: <int>
campaign_count: <int>
sync_enabled: <bool>

# Slack / Hypertide / dashboard (null until populated)
slack_client_channel_id: null|"<string>"
slack_notifications_channel_id: null|"<string>"
hypertide_workspace_ref: null|"<string>"
custom_dashboard_url: null|"<https url>"

# Template provenance
template_version: "0.4"                      # bump when template schema changes
last_synced: "YYYY-MM-DD"                    # set by daily sync worker
---
```

### Body
Human-readable narrative reproducing the same data with cross-references.
Used for AE reading; agents prefer the frontmatter.

### Owners
- Onboarding flow creates the file on repo creation
- Daily sync worker updates `last_synced` + any DB/Day.AI-sourced fields
- AE / future automation writes back `slack_client_channel_id` etc. when
  the value materializes

### Invariants
- File location: always `/client.md` at repo root
- All keys defined here MUST be present (use `null` if no value)
- Schema changes require `template_version` bump + backfill migration

---

## 4. `index` — `/README.md`

AE-facing entry doc. Points at `CLAUDE.md` for the orchestrator.

### Frontmatter
```yaml
---
name: "<client> — Charm Client Repo"
description: "Public-facing entry point for AEs opening this repo"
type: "index"
created: <date>
status: "active"
related: ["[[CLAUDE]]", "[[client]]"]
---
```

### Body
- Welcome / orientation paragraph
- "For AEs: first time opening this repo" numbered list
- "Daily loop" (`git pull` -> branch -> commit -> push)
- Navigation anchors (links to MOCs)
- Template version + provenance

### Invariants
- Always at `/README.md`
- No client-specific automation reads or writes this — keep it human-only

---

## 5. `guide` — orchestrator + workstream `CLAUDE.md` files

Files: `/CLAUDE.md`, `dashboard/CLAUDE.md`, `gtm/CLAUDE.md`, etc.

### Frontmatter
```yaml
---
name: "<client> — Client Context Repository" (or workstream name)
description: "<one-line>"
type: "guide"
tags: [claude-md, orchestrator|workstream, root|<workstream>]
created: <date>
status: "draft|active"
related: ["[[README]]", "[[client]]", "[[<relevant moc>]]"]
---
```

### Body
- Orientation prose
- Repo map / workstream map
- Documentation protocol (binding rules)
- Skill library pointers
- "How to work in this repo" instructions

### Invariants
- Top-level `CLAUDE.md` is loaded first by Claude Code sessions; keep it
  comprehensive but focused on navigation
- Workstream `CLAUDE.md` (e.g., `gtm/CLAUDE.md`) covers JUST that
  workstream

---

## 6. `meeting` — `notes/meetings/<date>_<slug>.md`

Per-meeting record. Written by the meeting sync worker (Tier 1.1).

### Frontmatter
```yaml
---
name: "<meeting title from Day.AI>"
type: "meeting"
created: "YYYY-MM-DD"                  # recording date
status: "active"
related: ["[[client]]", "[[contacts]]", "[[insights]]"]

# Day.AI source
dayai_meeting_id: "<uuid>"             # native_meetingrecording objectId
dayai_meeting_url: "<https permalink>" # if available
dayai_recording_url: "<https url>"     # if available

# Meeting metadata
recording_date: "YYYY-MM-DDTHH:MM:SSZ" # full datetime
duration_minutes: <int>
attendees: ["email1@client.com", "email2@hirecharm.com", ...]
attendee_count: <int>

# Charm-side classification
charm_attendees: ["chris@hirecharm.com", ...]
client_attendees: ["krishna@withsammy.ai", ...]
external_attendees: ["random@example.com", ...]
---
```

### Body
```markdown
# <meeting title>

**When:** <human-readable date + time>
**Duration:** <N> minutes
**Attendees:** Krishna Pryor (Sammy), Chris Booth (Charm), ...

## Summary

<Day.AI's generated summary — usually present, single paragraph or
short bullets>

## Action items

- <action 1>
- <action 2>

## Decisions surfaced

<if Day.AI captured any>

## Transcript

<full transcript text — long, hence last>
```

### Invariants
- Filename: `notes/meetings/YYYY-MM-DD_<title-slug>.md` (ISO date,
  hyphenated slug from meeting title)
- Idempotent: re-sync overwrites if `dayai_meeting_id` matches; skips
  otherwise
- Never deleted

---

## 7. `reference` — sync-managed reference files

Sub-types based on filename:
- `notes/contacts.md` — contact roster (synced from Day.AI relationships)
- `notes/status.md` — current deal status (synced from Day.AI Status)
- `notes/insights.md` — Buyer Voice / Goals / Decision Process /
  Competitors (synced from Day.AI custom properties)
- `onboarding/dayai-opp.md` — audit snapshot of the closed-won opp at
  onboarding time
- `docs/REFERENCE_<topic>.md` — agency-internal reference docs (e.g.,
  API integrations)

### Frontmatter (common)
```yaml
---
name: "<title>"
type: "reference"
tags: [<topic>, dayai, ...]
created: <date>
status: "active"
related: [...]
---
```

### Body
Markdown narrative + tables. No specific schema beyond the type label;
the file's filename signals the sub-type.

### Sub-type notes

**`notes/contacts.md`** — three sections: Client-side, Charm team,
External / ambiguous. Each is a markdown table with columns
`Name | Email | Role(s) | Notes`. Roles come from Day.AI's `roles`
array (PRIMARY_CONTACT, CHAMPION, SUPPORTER, BUYER, DECISION_MAKER,
DIRECT_BENEFIT, OWNER_EMAIL, OTHER, IGNORE).

**`notes/status.md`** — sections: Timeline, Status, Risks. Content
sourced from Day.AI `Status`, `Risks`, `Last Contacted`, `Next Step`,
`Close Date` properties. Refreshed each sync; do not edit manually.

**`notes/insights.md`** — sections: Buyer Voice, Goals, Decision
Process, Competitors. Sourced from corresponding Day.AI custom
properties. The most useful single file for agents generating
campaigns.

**`onboarding/dayai-opp.md`** — written once at onboarding; never
refreshed (it's the historical snapshot). Includes summary table +
relationships count + truncated raw JSON.

### Invariants
- Sync-managed files have a header note: `do not edit manually — edits
  will be overwritten on next sync`
- AE additions go in `notes/`, NOT in these synced files

---

## 8. `note` — free-form AE notes

`notes/*.md` (excluding the synced reference files above).

Examples:
- `notes/call-prep-2026-04-24.md` — AE prep doc for an upcoming call
- `notes/handoff_2026-04-24_to_jane.md` — AE handover
- `notes/observation-2026-04-24-sammy-asked-about-X.md` — AE captured
  in-call observation

### Frontmatter
```yaml
---
name: "<title>"
type: "note"
tags: [<topic>, ...]
created: "YYYY-MM-DD"
status: "draft|active"
related: ["[[client]]", "[[<other>]]"]
---
```

### Body
Free-form markdown. No required sections. The discipline is:
- One topic per file (split if it grows)
- Date in filename when chronology matters (`YYYY-MM-DD_<topic>.md`)
- Cross-link aggressively via `[[wiki-links]]`

### Invariants
- Never deleted (per accumulation discipline)
- If superseded, write a new note that explains supersession +
  `related` link to the old one; don't delete the old one

---

## 9. `transcript` — raw call transcripts

`notes/transcripts/*.md`. The "Day AI landing zone" per the template.
Distinct from `meeting` type because transcripts are RAW input data, not
synthesized records.

### Frontmatter (minimal, frontmatter optional for purely raw dumps)
```yaml
---
name: "<source identifier>"
type: "transcript"
tags: [transcript, raw, dayai]
created: "YYYY-MM-DD"
status: "active"
source: "day.ai"|"otter"|"manual-paste"
related: ["[[client]]"]
---
```

### Body
Raw transcript text. No required structure.

### Invariants
- Lives in `notes/transcripts/`
- If a synthesized insight is extracted, it goes in a NEW file (likely
  `feedback/` or `notes/insights.md` via sync) — the transcript stays
  put

---

## 10. `feedback-rule` — one client rule per file

`feedback/feedback_<topic>.md`. The accumulation backbone — every
client correction over time becomes one of these.

### Frontmatter
```yaml
---
name: "<short rule summary>"
type: "feedback-rule"
tags: [feedback, <topic>]
created: "YYYY-MM-DD"
status: "active"
source: "<where the rule came from — e.g., call 2026-04-24>"
applies_to: [<workstreams, e.g. gtm, dashboard, all>]
related: ["[[client]]", "[[<relevant moc>]]"]
---
```

### Body
```markdown
# <rule one-liner>

## Rule

<the rule — one paragraph max. Tight, actionable.>

## Why

<the reason — client's own words if quoted, your interpretation
otherwise. This is what lets future Claude sessions judge edge cases.>

## Source

<where this came from — call with X on date Y, email from Z,
written feedback in form W. Citable trail.>

## How to apply

<concrete examples — say this, don't say that. Optional but
high-value when the rule has edge cases.>
```

### Invariants
- One rule per file
- Filename uses `feedback_<topic>.md` to be greppable
- Skills (especially `.claude/skills/gtm/campaign-copywriting/`)
  read this folder before generating output

---

## 11. `decision` — frozen choice with tradeoffs

`decisions/DECISION_<topic>.md`. Captures decisions made about THIS
client — not agency-wide decisions (those live in `charm-kb`).

### Frontmatter
```yaml
---
name: "<decision title>"
type: "decision"
tags: [decision, <topic>]
created: "YYYY-MM-DD"
status: "accepted|proposed|superseded"
supersedes: ["[[DECISION_previous]]"]   # if applicable
superseded_by: ["[[DECISION_newer]]"]   # if applicable
related: ["[[client]]", "[[<context>]]"]
---
```

### Body
```markdown
# <decision title>

## Context

<situation that called for a decision>

## Decision

<what we decided — one paragraph>

## Why

<reasoning — tradeoffs considered, what we optimized for>

## Alternatives considered

- Option A — <why not>
- Option B — <why not>

## Consequences

<what this means going forward — what we are now committed to,
what flexibility we give up>

## Revisit when

<conditions under which this decision should be revisited — e.g.,
"if client grows past 3 workspaces", "after Q3 review">
```

### Invariants
- Accepted decisions are NEVER deleted, only superseded
- A superseded decision keeps its file; a new file marks
  `supersedes: [...]`
- Cross-reference both directions (`supersedes` + `superseded_by`)

---

## 12. `campaign` — folder per campaign

`gtm/campaigns/YYYY-MM-DD_<campaign-slug>/`. Folder, not single file.

### Folder structure
```
gtm/campaigns/2026-04-24_construction-trades-q2/
  README.md                  # campaign-level overview (type: campaign)
  strategy.md                # strategy doc (type: guide)
  sequences/
    sequence-a.md            # one file per sequence variant
    sequence-b.md
  lists/
    target-list.csv          # raw prospect list (asset)
    list-meta.md             # list metadata + sourcing run reference
  drafts/                    # raw drafts before approval
  approved/                  # final approved copy
  assets/                    # images, attachments
```

### Top-level `README.md` frontmatter
```yaml
---
name: "<campaign name>"
type: "campaign"
tags: [gtm, campaign, <topic>]
created: "YYYY-MM-DD"
status: "draft|active|completed|archived"
started: "YYYY-MM-DD"
ended: "YYYY-MM-DD"|null
related: ["[[client]]", "[[gtm-moc]]", "[[<prior campaign>]]"]

# Strategy
sequence_count: <int>
prospect_count: <int>
icp_segment: "<string>"

# Outcomes (filled when campaign concludes)
emails_sent: <int>|null
reply_count: <int>|null
positive_reply_count: <int>|null
booked_meeting_count: <int>|null
---
```

### Invariants
- One campaign per dated folder
- Outcome metrics filled when campaign concludes (could be by report
  cron in Tier 3)
- Prior campaigns NEVER deleted — the feedback loop reads them

---

## 13. `report` — auto-generated campaign performance reports

`gtm/reports/YYYY-MM-DD_<campaign-slug>.md`. Written by the EmailBison
cron worker (Tier 3.x — not yet built).

### Frontmatter
```yaml
---
name: "<report title>"
type: "report"
tags: [report, gtm, <campaign-slug>]
created: "YYYY-MM-DD"
status: "active"
related: ["[[<campaign README>]]", "[[client]]"]

# Source
emailbison_campaign_id: <int>
report_period_start: "YYYY-MM-DD"
report_period_end: "YYYY-MM-DD"

# Metrics
emails_sent: <int>
delivered: <int>
open_rate: <float>
reply_rate: <float>
positive_reply_count: <int>
bounce_count: <int>
unsubscribe_count: <int>
---
```

### Body
Tables + analysis. Format produced by the cron writer.

### Invariants
- Auto-generated, do not edit manually (changes overwritten)
- One report per campaign per period (could be daily, could be
  campaign-end summary)
- Never deleted — historical performance is the feedback loop

---

## 14. `list` — sourcing run output

`gtm/lists/YYYY-MM-DD_<sourcing-slug>/`. Folder per sourcing run.

### Folder
```
gtm/lists/2026-04-24_construction-builders-aus/
  list.csv               # the prospects (CSV; type: asset)
  meta.md                # provenance + sourcing parameters (type: reference)
  filters-applied.md     # what filters we used (type: reference)
```

### `meta.md` frontmatter
```yaml
---
name: "<sourcing run name>"
type: "reference"
tags: [list, sourcing, <vertical>]
created: "YYYY-MM-DD"
status: "active"
related: ["[[client]]", "[[<related campaign>]]"]

# Source
source: "apollo|sales-navigator|clay|manual|..."
prospect_count: <int>
quality_grade: "A|B|C|D"|null   # filled after first campaign uses it
---
```

---

## 15. `onboarding-submission` — form responses

`onboarding/form_<date>.md`. Written by the onboarding form sync
(Tier 3.6 — not yet built).

### Frontmatter
```yaml
---
name: "Onboarding form — <client>"
type: "onboarding-submission"
tags: [onboarding, form, intake]
created: "YYYY-MM-DD"
status: "active"
related: ["[[client]]", "[[dayai-opp]]"]

# Source
form_id: "<onboard.laviefatigue.com submission id>"
submitted_by_email: "<email>"
submitted_at: "YYYY-MM-DDTHH:MM:SSZ"
---
```

### Body
The submitted form, preserved verbatim. Question -> answer format.

### Invariants
- Preserved exactly as received (no cleanup, no edits)
- One file per submission; if client resubmits, new file with new
  timestamp (don't overwrite)

---

## 16. `asset` — raw client-shared files

`assets/<filename>`. Brand guides, decks, PDFs, exports. No
frontmatter (binary files); a sibling `<filename>.meta.md` may carry
the metadata.

### Sibling `<filename>.meta.md` (optional but recommended for substantial assets)
```yaml
---
name: "<original filename>"
type: "asset"
tags: [asset, <category>]
created: "YYYY-MM-DD"
status: "active"
related: ["[[client]]"]

source_asset: "<filename>"
source: "shared by <name> on <date> via <channel>"
content_type: "brand-guide|deck|spec|export|other"
---
```

### Body
Optional human notes about the asset (what it is, when to use it,
related context).

### Invariants
- Raw assets preserved as received — never edited
- Future Tier 3.5 will auto-extract key facts from assets into
  `notes/extracts/<asset-name>.md`

---

## 17. How automations should write files

### General contract for any worker writing to a client repo

1. **Read `client.md` frontmatter first** to know which client you're in
2. **Use the typed file paths above** — don't invent locations
3. **Validate frontmatter before commit** — at minimum, the
   required base fields (`name`, `type`, `created`, `status`,
   `related`)
4. **Idempotent commits** — content-diff before commit; skip if
   nothing changed
5. **Atomic commits via git-data API** — see
   `scripts/dayai/onboard_client_repo.py` for the pattern
6. **Commit message format**:
   ```
   <category>: <one-line summary>

   <details: what files, why, source of data>

   <if automated: signature line indicating the worker>
   ```
7. **Never delete** — see `CONCEPT_client_repo.md` §6

### Specifically for sync workers (Day.AI, EmailBison, etc.)

- Track `last_synced` in the file's frontmatter
- Include the source ID (`dayai_meeting_id`, `emailbison_campaign_id`,
  etc.) so re-sync can identify the same record
- Refresh, don't append: if you re-sync, regenerate the file (don't
  add new sections to an existing one — that creates drift)
- Refresh frequency: document in the worker's docstring

---

## 18. How automations should read files

### Universal read pattern

```python
import frontmatter
from pathlib import Path

def load_client_files(client_repo: Path, type_filter: str | None = None):
    """Yield (path, post) for every .md file with frontmatter, optionally filtered by type."""
    for p in client_repo.rglob("*.md"):
        try:
            post = frontmatter.load(p)
        except Exception:
            continue
        if "type" not in post.metadata:
            continue  # skip docs without proper frontmatter
        if type_filter and post.metadata["type"] != type_filter:
            continue
        yield p, post

# Examples:
client_md = frontmatter.load("HireCharm/client-sammy/client.md")
eb_id = client_md.metadata["emailbison_workspace_id"]   # 8

# Find every meeting:
for p, post in load_client_files(Path("HireCharm/client-sammy"), "meeting"):
    print(p, post.metadata.get("recording_date"), post.metadata.get("attendees"))

# Find every feedback rule:
rules = list(load_client_files(Path("HireCharm/client-sammy"), "feedback-rule"))
```

### Cross-client read pattern

```python
clients_root = Path("/path/to/cloned/HireCharm")
for client_repo in clients_root.glob("client-*"):
    client_md = client_repo / "client.md"
    if not client_md.exists():
        continue
    data = frontmatter.load(client_md).metadata
    if data.get("sync_enabled"):
        # do something with this client
        ...
```

---

## 19. Schema versioning

When a schema in this doc changes (new field, renamed field, removed
field):

1. Bump `client.md.frontmatter.template_version` in
   `HireCharm/client-template/client.md` (e.g., 0.4 -> 0.5)
2. Write a migration entry in this doc (§20)
3. Backfill via maintenance script that iterates every
   `HireCharm/client-*` and applies the migration
4. Test the migration on `client-sammy` first

Schema changes are NEVER silent. Every change has a documented
migration path.

---

## 20. Schema migration log

When schemas change, log the migration here. Format:

```
### v0.X -> v0.Y (YYYY-MM-DD)
- Added: <new field with rationale>
- Removed: <old field, where its data moved>
- Renamed: <old name> -> <new name>

Migration script: <path or PR link>
Tested on: <client repo(s)>
Backfill commit: <commit SHA when rollout completed>
```

### v0.3 -> v0.4 (2026-04-24)
- Restructured `client.md` from prose-with-TBDs to YAML
  frontmatter-as-canonical-record
- Added: `emailbison_workspace_id` (NUMERIC, from `/api/workspaces/{uuid}`),
  `organization_name`, `dayai_organization_id`, `dayai_owner_user_id`,
  `dayai_owner_email`, `primary_contact_roles` (list), package state
  snapshot fields, `slack_*`, `hypertide_*`, `custom_dashboard_url`,
  `last_synced`
- Added files: `notes/contacts.md`, `notes/status.md`,
  `notes/insights.md`, `onboarding/dayai-opp.md`

Migration script: `scripts/dayai/synthesize_client_repo.py` (currently
hard-coded to Sammy; needs parameterization)
Tested on: `HireCharm/client-sammy`
Backfill commit: pending bulk rollout (Roadmap Tier 1.3)

---

## See also

- `README.md` — index for this folder
- `CONCEPT_client_repo.md` — what the engine is for
- `HANDOFF_client_repo_pipeline.md` — technical handoff
- `ROADMAP_dayai_automation.md` — future work catalog
