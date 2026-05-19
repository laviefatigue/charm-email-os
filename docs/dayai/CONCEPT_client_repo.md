# GitHub as a Per-Client Context Engine

> Why each Charm client gets a private GitHub repo, what it's FOR, who
> reads it, and how it powers the agency operating model.
>
> Paired with `HANDOFF_client_repo_pipeline.md` (technical state) and
> `ROADMAP_dayai_automation.md` (future build catalog). Read this one
> before designing anything that touches a client repo.

---

## 1. The headline

**Each active client gets a private `HireCharm/client-<slug>` repo that
serves as their longitudinal context engine.**

A context engine is something that:
- Accumulates relevant information over time without losing it
- Is loaded into a working session (human or agent) at the start of work
- Has stable structure so consumers know where to look
- Has typed metadata so automations can parse and act on it
- Powers downstream reasoning rather than performing actions itself

For Charm, this engine is a git repository hosted on GitHub, navigated
in VS Code with Foam, written to by humans and automations, read by
Claude Code sessions when doing client work.

Three years from now, every meaningful thing Charm knows about a
client lives in their repo. Every decision, every campaign result,
every client correction, every meeting summary, every onboarding
artifact. The repo IS the institutional memory per client.

---

## 2. Why GitHub specifically

We considered (briefly) and rejected other shapes:

| Option | Why not |
|---|---|
| A database table per client | Loses the file-as-document UX, no diffing, hard to navigate, can't open in VS Code, no Foam graph |
| Notion / Confluence / Obsidian Sync | Vendor lock-in, no real diff/branch model, weak agent integration, hard to script bulk operations |
| Slack canvases | Ephemeral feel, no version history, search is mediocre, can't grep |
| Shared drive (Google Drive, Dropbox) | No version control, no schema enforcement, no programmatic templating, secrets bleed in |

What GitHub gives us:

- **Branch + diff + commit history** — every change is auditable, attributable, revertable
- **Templates** — `HireCharm/client-template` is marked `is_template: true`,
  one API call clones the whole structure to a new client repo
- **The Charm Onboarder GitHub App** has `administration:write` +
  `contents:write` so we can create + populate repos programmatically
- **Foam + VS Code = the read interface** — wiki-links, backlinks,
  graph view, search, all free
- **Claude Code already opens repos** — agents have native fluency with
  git-backed working dirs; no special integration needed
- **Frontmatter is a free typed schema** — any script can `import frontmatter`
  and read structured values without inventing a new format
- **`git clone` is the universal interface** — any human, any laptop, any
  AE pulls the same thing the agents pull
- **Private repos by default** — controlled access at org level, no
  client-facing exposure

The cost is small: ~50 lines of Python to clone + populate from template
(see `scripts/dayai/onboard_client_repo.py`), and we already had to set
up the Charm Onboarder GitHub App for other reasons.

**Net: GitHub gives us a versioned, type-safe, agent-readable, human-
friendly per-client knowledge graph for free.**

---

## 3. What the engine is for (not for)

### IS for

- **Loading context** at the start of any human or agent work on a client
- **Accumulating** notes, meeting summaries, decisions, feedback,
  campaign artifacts, post-mortems
- **Holding the canonical typed identity** (`client.md` frontmatter
  with all IDs, dates, package state) that every automation reads
- **Cross-referencing** — wiki-links between meeting -> insight ->
  feedback rule build the graph
- **Handover** — AE rotation, vacation cover, future-you-in-3-months
  all start from `CLAUDE.md` + `client.md` + the last few notes

### NOT for

- **Executing actions.** The dashboard runs campaigns. charm-email-os
  manages inboxes. EmailBison sends mail. The repo doesn't push,
  doesn't fetch, doesn't trigger.
- **Source of truth for live state.** Day.AI owns deal state, Postgres
  owns workspace state, EmailBison owns sender state. The repo holds
  cached + accumulated views, not authoritative state.
- **Client-facing material.** Clients never see this repo. Don't put
  things you can't say to the wrong audience.
- **Storing secrets.** Frontmatter has fields like
  `emailbison_workspace_id: 8` (the public-ish numeric ID) and
  references like "API key in env var `WORKSPACE_API_KEY_8`" — but
  never the key itself.
- **Replacing the dashboard or the DB.** It complements both.

---

## 4. The four audiences

The engine is read by four different consumers. Design with all four
in mind.

### Audience A — Humans (AEs, admins) in VS Code with Foam

- Clone repo locally, open in VS Code, Foam extension activates
- Read `CLAUDE.md` -> `client.md` -> the relevant shelf
- Write back: meeting notes, feedback rules, decisions, campaign
  artifacts, post-mortems
- **Daily flow:** `git pull` -> work on a branch -> commit as you
  produce -> push when done

### Audience B — Claude Code sessions (AE-initiated)

- AE: "Sammy is concerned about cold-call attribution. Draft a response."
- Claude Code loads `CLAUDE.md`, follows wiki-links to the relevant
  files, reads context, uses skills in `.claude/skills/` when the task
  matches one, drafts the response
- Writes back: commits the draft into the right shelf (e.g.
  `notes/responses/sammy-attribution-<date>.md`)

For an agent to work well, the repo's content must be:
- **Discoverable** via Foam wiki-links from `CLAUDE.md`
- **Typed** via frontmatter (one file says "I'm a meeting", another
  says "I'm a feedback rule" — agent decides relevance without inferring)
- **Bounded per file** (one rule per feedback file, one decision per
  DECISION file) so the agent finds answers without parsing 10 KB to
  find one fact

### Audience C — Automation scripts

- `dayai_watcher_worker.py` (today): detects closed-won, will eventually
  write to the repo
- Future: meeting sync worker, daily refresh worker, value-change
  detector — all read + write `HireCharm/client-*/`
- Scripts read `client.md` frontmatter via the YAML parser of choice:

  ```python
  import frontmatter
  data = frontmatter.load("client.md")
  eb_id = data["emailbison_workspace_id"]   # int 8, ready for EB API
  domain = data["domain"]                    # "withsammy.ai"
  opp_id = data["dayai_opp_id"]              # UUID — for Day.AI joins
  ```

This is why the frontmatter contract (`HANDOFF` §4) matters —
automation reliability depends on stable typed keys, not prose parsing.

### Audience D — charm-email-os UI (the Context + Assets sections)

The charm-email-os frontend renders a per-client **Context** tab and
**Assets** tab that pull live content directly from
`HireCharm/client-<slug>`. This is the operator-facing surface — the
Charm team browses client context inside the dashboard they already use,
without cloning a repo or opening VS Code.

Direction is **bidirectional**:

- **Read**: frontend calls `GET /api/clients/{id}/context` and
  `GET /api/clients/{id}/assets`, charm-email-os backend reads
  from GitHub using the Charm Onboarder App, renders markdown +
  asset previews.
- **Write**: when an AE uploads a file via the Assets tab or saves a
  note from the Context tab, `POST /api/clients/{id}/assets` (or the
  context equivalent) commits the change into the client repo. The
  repo stays the source of truth; the frontend is a thin operator
  surface over it.

Architectural constraint: charm-email-os does NOT mirror the repo
into its own database. The first version reads from GitHub on demand
(via the Charm Onboarder App's installation token, which is minted from
the PEM stored in `app_credentials`). Caching gets added when — and
only when — a real rate-limit or latency problem appears. Premature
caching is the failure mode to avoid; the repo IS the database.

Why this audience matters for design:
- **The frontend is a write path now**, not just a read path. Files
  authored via the UI land in the repo via API, alongside files written
  by AEs in VS Code and by automation workers. All three writers share
  the same file conventions (frontmatter, naming, locations).
- **Latency budget is interactive**, not batch. A page load with N
  repo reads needs to feel like a normal page load. Keeps the data
  shape simple, no deeply-nested directory walks per render.
- **Asset uploads need a path through this layer.** Drop-zone in the
  UI → multipart upload → API → repo commit. See
  `SPEC_charm_os_repo_access.md` for the route shape.

See `SPEC_charm_os_repo_access.md` for the full direct-access pattern
(API routes, `clients.context_repo` column, helper module).

---

## 5. What goes IN vs stays in the source system

The engine holds **either** a cached snapshot of an external source, **or**
content that originates in the repo and has no external system of record.

| Data | Source of truth | What lives in the repo |
|---|---|---|
| Day.AI opps (live) | Day.AI CRM | Daily-synced snapshot in `notes/status.md` + `notes/insights.md` |
| Day.AI meeting transcripts | Day.AI | Copy in `notes/meetings/` (NEXT STEP — currently empty) |
| EmailBison campaigns + metrics | EmailBison + charm-email-os DB | Daily report drops in `gtm/reports/` (future cron) |
| Inboxes, domains, package state | charm-email-os DB | Frontmatter snapshot in `client.md` (refreshed on sync) |
| API keys, passwords | env vars / secret store | References ("`workspace_id=X, key in env var Y`") — never the value |
| AE observations, call notes, hand-written feedback | nowhere else | First-class content in `notes/`, `feedback/`, `decisions/` |
| Brand assets, client-shared docs | client-shared drives | Copies in `assets/` (preserved as received) |
| Campaign copy, sequences, lists | gtm/ + charm-email-os DB + EmailBison | Generation artifacts + strategy doc + final approved copy in `gtm/campaigns/` |

**The rule:** every field has ONE source of truth. The repo either holds
the source (AE notes, decisions, feedback) or caches a snapshot pointing
at the source (Day.AI status, DB IDs, EB metrics). Never duplicate
without specifying which copy wins on conflict.

### Read path: charm-email-os does NOT mirror the repo

The charm-email-os frontend (Audience D) reads the client repo **on
demand** via the GitHub API — there is no `client_repo_content`
mirror table, no sync worker pulling files into Postgres. The repo is
the storage layer; charm-email-os is a thin operator surface over it.

This is a deliberate trade-off:
- **+** Zero sync complexity. No "is the cache stale?" questions. No
  webhook plumbing. No reconciliation jobs.
- **+** The repo's git history IS the audit trail — no separate event
  log needed.
- **-** Page renders cost N GitHub API calls (one per file shown).
- **-** GitHub rate limit (5,000 req/hr per installation) is the
  ceiling. With ~20 active clients and modest browse traffic, that's
  multiple orders of magnitude of headroom — but it's a finite budget.

Caching gets added **only when** we observe rate-limit pressure or
unacceptable page latency in production. The default is direct access.

If/when caching is needed, the pattern is documented in
`SPEC_charm_os_repo_access.md` §"When to add caching."

---

## 6. The accumulation discipline (binding)

Text artifacts in the repo are **never deleted.** This is enforced, not
aspirational.

Why it matters:
- The "what worked last campaign" loop in `gtm/reports/` depends on
  history being there
- "We tried that pitch in March, the client pushed back" only exists
  if the original pitch + the feedback are both still in the repo
- Decisions reference past decisions; deleting one breaks the chain
- An AE in 6 months reads 50+ commits to onboard — every commit matters

What CAN be deleted:
- Validated noise (screenshots after the extracted insight has been
  written to a text file)
- Build artifacts (already gitignored)
- Anything explicitly marked `type: ephemeral` in frontmatter (current
  template has no such type)

What CANNOT be deleted:
- Any `.md` with frontmatter
- Anything in `notes/`, `decisions/`, `feedback/`, `gtm/`,
  `onboarding/`, `assets/`
- Raw transcripts in `notes/transcripts/` and meeting markdown in
  `notes/meetings/`

Mistakes during AE work: instead of deleting, append a clarifying note
or write a `decisions/DECISION_<topic>.md` explaining the reversal.

---

## 7. Daily/weekly workflows the engine supports

Use these as sanity checks: does the change you're about to make make
these flows easier?

### Flow A — AE morning startup
1. `git pull` (overnight Day.AI sync + EB report cron may have written
   new files)
2. Open in VS Code; Foam loads the graph
3. Read `client.md` for ID anchors + current package state
4. Skim `notes/status.md` for what's changed
5. Read last 3 files in `notes/` for context drift
6. Start work

### Flow B — AE preps for a client call
1. Open `notes/insights.md` for Buyer Voice + Goals + current pain
   points
2. Open `notes/meetings/` for what was said last call (or
   `notes/transcripts/` for raw)
3. Open `feedback/` for accumulated client rules
4. Skim recent `gtm/campaigns/` for what's been pitched
5. Write call prep into `notes/call-prep-<date>.md` if substantial

### Flow C — Agent generates a new campaign
1. Claude reads `client.md` for ICP + package state + primary contact
2. Reads `notes/insights.md` for buyer voice + competitors
3. Reads `feedback/` for accumulated rules
4. Reads `gtm/reports/` for what last campaign accomplished
5. Reads `.claude/skills/gtm/campaign-strategy/` and follows the skill
6. Writes draft into `gtm/campaigns/YYYY-MM-DD_<slug>/`

### Flow D — Hand off a client between AEs
1. Outgoing AE writes `notes/handoff_YYYY-MM-DD_to_<newae>.md` with
   current focus, open threads, watch-outs
2. Incoming AE clones repo, opens `CLAUDE.md`, then the handoff doc
3. No 30-minute walking-through-shared-doc meeting needed. The repo IS
   the handover.

### Flow E — Client correction in a call
1. AE on call, client says "stop using 'optimize' — sounds like AI"
2. AE creates `feedback/feedback_word_optimize.md` with frontmatter +
   one-paragraph rule + reasoning +
   `related: ["[[client]]", "[[gtm-moc]]"]`
3. Commits within the hour
4. Next campaign Claude generates auto-respects the rule because the
   skill reads from `feedback/` before generating

### Flow F — Daily Day.AI sync (NEXT STEP work)
1. Cron (or watcher trigger) fetches new/updated meetings via
   `get_meeting_recording_context`
2. Writes new `notes/meetings/YYYY-MM-DD_<title-slug>.md` files
3. Refreshes `notes/status.md` from Day.AI's Status property
4. Refreshes `notes/insights.md` from Buyer Voice / Goals / Decision
   Process
5. Updates `client.md` `last_synced` field
6. Commits with message like `sync: dayai snapshot YYYY-MM-DD (3 new
   meetings)`

### Flow G — Cross-client pattern detection (future)
1. Agent reads across all `HireCharm/client-*` repos
2. Surfaces patterns: "3 clients raised cold-call attribution concerns
   this week"
3. Writes to `charm-kb/insights/CROSS_CLIENT_<date>.md`
4. This is only possible BECAUSE per-client context is structured
   files, not opaque CRM records

---

## 8. How the engine fits with the rest of Charm

```
                        +-------------------+
                        |     Day.AI CRM    |   <- source: meetings, opps, contacts
                        +-------------------+
                                 |
                       reads via |  dayai/ Python package (this repo)
                                 v
+----------------+      +-------------------+      +------------------+
| charm-email-os |<====>|  client-<slug>    |<---->|  AE in VS Code   |
|  backend +     | gh   |  GitHub repo      |      |  + Claude Code   |
|  Postgres      | App  |  CONTEXT ENGINE   |      |                  |
+----------------+      +-------------------+      +------------------+
        |                       ^
        | renders                | also written by:
        v                        |   - dayai-watcher reconciler (onboarding)
+----------------+               |   - daily Day.AI sync worker
|  charm-email-os|               |   - meeting sync worker
|  React UI      |               |   - future EmailBison report cron
|  Context tab   |               |
|  Assets tab    |               |
+----------------+               v
                          +-------------------+
                          |  Chris's          |
                          |  copywriting      |
                          |  dashboard        |
                          +-------------------+
                                 |
                       executes  |
                                 v
                          email outbound

+----------------+
|  EmailBison    |  <- source: send/reply metrics, sender state
|  (campaigns,   |
|   inboxes)     |
+----------------+
```

The `<====>` line is the charm-email-os ↔ repo connection: backend
reads + writes via the Charm Onboarder App (PEM stored in
`app_credentials` table). Every other writer also goes through that
same helper. **One credential, one helper, every service.**

Three layers, separated by role:

- **Source-of-truth systems** — Day.AI (CRM), Postgres (clients +
  workspaces), EmailBison (campaigns + inboxes). They hold the live
  authoritative state.
- **Context engine** — `HireCharm/client-<slug>` GitHub repos. They
  hold accumulated knowledge + cached snapshots + typed identity.
- **Execution layer** — Chris's copywriting dashboard. It does the
  actual outbound work, reading context from the engine when needed.

**Don't conflate layers.** Don't put execution logic in the repo
(no scripts that send emails from there). Don't put context in the
dashboard (no campaign-strategy notes living only in dashboard state).
Don't make the repo authoritative for things Day.AI owns.

---

## 9. What an agent should be able to answer from a well-maintained repo

If you're designing the next automation, test it against these. A
well-onboarded `client-sammy` should let a Claude Code agent answer
all of these without external lookups:

- **Identity** — "What's Sammy's EmailBison workspace ID?" -> read
  frontmatter
- **People** — "Who's the primary contact at Sammy?" -> client.md +
  contacts.md
- **State** — "How many inboxes does Sammy have running?" -> client.md
  frontmatter (`inbox_count`)
- **Recent context** — "What did we discuss with Sammy last week?" ->
  `notes/meetings/`
- **Strategy** — "What are Sammy's stated goals?" -> `notes/insights.md`
- **Constraints** — "Are there words we should avoid in Sammy's copy?"
  -> `feedback/`
- **History** — "When did Sammy close? Who was the AE?" ->
  client.md frontmatter
- **Comparison** — "How did Sammy's last campaign compare to the one
  before?" -> `gtm/reports/` + `gtm/campaigns/`
- **Decisions** — "Why are we sending from .ai domains for Sammy?"
  -> `decisions/DECISION_<topic>.md`

If a question requires the agent to scrape Day.AI directly, the
engine isn't doing its job. The repo should have the answer staged
via sync.

If a question requires the agent to write to a system of record (push
a campaign to EmailBison, update a Day.AI deal stage), that's NOT the
repo's job — it's the dashboard or the charm-email-os API.

---

## 10. Skills, conventions, and the template

### Skills (`.claude/skills/`)

The template ships with skills like:
- `.claude/skills/gtm/campaign-copywriting/SKILL.md`
- `.claude/skills/gtm/campaign-strategy/SKILL.md`
- `.claude/skills/gtm/personalization-subagent-pattern/SKILL.md`

These contain `{{variable_name}}` placeholders that look like template
substitutions but are NOT — they're the variable syntax the skill USES
when authoring outreach copy. They stay literal in every client repo.

Skills exist in the per-client repo (not in a global location) because:
- An AE in VS Code invokes them with full client context already loaded
- A Claude Code agent reading `CLAUDE.md` finds them via the skill index
- They get SAME behavior across clients because the skill version is
  stamped in `client.md.frontmatter.template_version`

When skills update at the template level, all client repos should be
refreshed — currently manual, eventually a maintenance script that
diffs `template_version` and PRs the delta.

### Frontmatter convention

Every `.md` file in the repo opens with YAML frontmatter:

```yaml
---
name: <human-readable title>
description: <one-line purpose>
type: <client-card|decision|note|reference|guide|meeting|feedback|...>
tags: [<topic>, ...]
created: YYYY-MM-DD
status: <draft|active|superseded>
related: ["[[other-doc]]", ...]
---
```

`client.md` has the most elaborate frontmatter — it's the canonical
machine-readable identity record (see `HANDOFF` §4).

### Wiki-links

Cross-reference via `[[doc-name]]`. Foam builds the backlink graph.
Every doc should have outward `related:` links AND be linked from at
least one MOC (Map of Content) or index doc. Orphan docs are
invisible docs.

### The template version stamp

`client.md.frontmatter.template_version` tracks which template version
generated the repo. When the template updates, this enables drift
detection — automation can PR the diff into every client repo to keep
them current.

---

## 11. Slug rules

The slug determines the repo name: `HireCharm/client-<slug>`.

Current rule (in use):
- Lowercase
- Strip non-alphanumeric
- Hyphen-separate words

| Source name | Slug | Repo |
|---|---|---|
| Sammy | `sammy` | `HireCharm/client-sammy` |
| Stable Kernel Market Research | `stable-kernel-market-research` | `HireCharm/client-stable-kernel-market-research` |
| Ink'd | `inkd` | `HireCharm/client-inkd` |
| Search Atlas | `search-atlas` | `HireCharm/client-search-atlas` |

Gotchas:
- Duplicate name candidates in the DB (`Stable Kernel` AND
  `Stable Kernel Market Research`) — slug collision risk. Manual
  decision: one repo or two? Document in `decisions/`.
- Long slugs > 40 chars are a smell. Codify a max-length + truncation
  rule before bulk rollout.
- Reserved GitHub repo names (`client-template` is the template
  itself; never create `HireCharm/client-template-test` etc).

Codify the rule in `scripts/dayai/onboard_client_repo.py` before bulk
rollout. Until then, manual slug per client.

---

## 12. When in doubt

- **Need to add a new file type?** Pick the shelf
  (`notes/`, `decisions/`, etc.), match existing naming convention,
  give it frontmatter, link from a MOC.
- **Need to add a new automation that writes to the repo?** Read this
  doc + `HANDOFF`, then design. Most failures come from treating the
  repo as a database instead of a knowledge engine.
- **Need to add a new field to `client.md` frontmatter?** Update the
  contract in `HANDOFF` §4, propagate to the template, write a
  migration that backfills existing client repos. Frontmatter is a
  typed schema — treat changes as schema changes.
- **Want to delete something?** Don't. Write a `decisions/` doc
  explaining the supersession, link back to the prior content.
- **Wondering if some data belongs in the repo?** See §5. If it has
  a system of record elsewhere, the repo holds a snapshot/reference,
  not the truth. If it originates with the AE, it's first-class repo
  content.
- **Want to add a new automation that READS from many client repos?**
  Use the frontmatter — every key is stable + typed. Don't grep prose.

---

## 13. The eventual operating model

Where this is all heading (described in `ROADMAP_dayai_automation.md`
§Tier 5 in more detail):

**Claude Code becomes the operating layer for agency work.** Every
routine task either:
- Runs as automation against the per-client engines (Tiers 1-4 in the
  roadmap), or
- Is invoked by an AE through a skill that has full client context
  already loaded

The engine makes this possible. Without per-client context staged in
parseable files with typed identity, agents have to scrape four
systems for every request and the latency + brittleness kills the
pattern.

With the engine populated, Claude Code is one git-pull away from
useful work on any client, for any AE, at any time.

That's the destination. Each Day.AI automation we build, each script
that writes into a client repo, each skill in `.claude/skills/`
incrementally moves the agency in that direction.

---

## See also

- `README.md` — index for this folder
- `HANDOFF_client_repo_pipeline.md` — what was built, current state,
  next step
- `ROADMAP_dayai_automation.md` — future automations on this foundation
- `HireCharm/client-template` — the template repo
- `HireCharm/client-sammy` — the worked example
