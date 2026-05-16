---
title: Client Context Repo Sync — CharmDB Spec
status: spec — pre-implementation
created: 2026-05-15
owners: elliott
related:
  - [[agent-runtime]]
  - [[design-system/brand-brief]]
  - [[design-system/references/ref-paperclip]]
---

# Client Context Repo Sync — CharmDB Spec

**Status:** Spec / pre-implementation. Captures the CharmDB-side data model + sync architecture for pulling per-client Foam-markdown context repos into the analyst-agent runtime.

This is **context engineering** for [[agent-runtime]]: analyst agents need rich client context (voice, banned phrases, ICP, stakeholders, prior decisions, recent AE notes) to make good recommendations. Storing that context as Foam-markdown in per-client GitHub repos gives us version control, AE-friendly editing, security (private repos), and LLM-native format. CharmDB syncs from these repos and exposes a context-query API to agents.

## What Already Exists (don't re-build)

The repo-side scaffolding is already shipped:

| Component | Location | Purpose |
|-----------|----------|---------|
| Template | [`D:/Work/Charm/charm-client-template/`](D:\Work\Charm\charm-client-template\) | v0.3 scaffold — `client.md`, `CLAUDE.md`, `README.md`, MOCs, skill library, folder taxonomy |
| Per-client repos | (private GitHub, one per client) | Scaffolded from template; AEs commit notes/feedback/decisions/reports daily |
| AE workflow | [`charm-client-template/CLAUDE.md`](D:\Work\Charm\charm-client-template\CLAUDE.md) §Daily flow | `git pull` → branch → commit on production → push → branch-review-merge picks up |
| Foam protocol | [`charm-client-template/CLAUDE.md`](D:\Work\Charm\charm-client-template\CLAUDE.md) §Documentation protocol | Frontmatter required, wiki-links both ways, MOC registration, no duplication |
| `client.md` card | repo root | Has `Charm OS record ID`, `Email Bison Workspace ID`, `Hypertide Workspace`, Slack channels, primary contact — links GitHub repo ↔ CharmDB workspace |
| Bison cron | (already in production) | Writes overnight reports into `gtm/reports/` of each client repo — repo is sink for backend-generated data |

## What This Spec Covers (CharmDB side, new build)

| Component | Purpose |
|-----------|---------|
| Workspace → Repo binding | CharmDB knows which GitHub repo belongs to which workspace; sync state per binding |
| Sync mechanism | Webhook (primary) + poll (fallback) → markdown ingestion worker |
| Markdown parser | Frontmatter (gray-matter) + wiki-links (`[[link]]`) + tags (frontmatter + `#inline`) → structured DB records |
| Indexed tables | `workspace_context_repos`, `workspace_context_documents`, `workspace_context_links`, `workspace_context_syncs` |
| Search + retrieval | Postgres FTS v1; pgvector embeddings v2 if needed |
| Context-query API | REST endpoints agents call as tools — search, fetch document, fetch graph, fetch recent |
| Security | Encrypted GitHub access tokens in `secrets` table; webhook HMAC verification; per-workspace token scoping |
| Integration with agent runtime | Skills reference `client.md` fields by name; agents see context staleness; recommendations cite source docs |

---

## Data Model

### `workspace_context_repos`

One row per workspace that has a context repo wired up. Auth is via a single org-wide **GitHub App installation** (see [[#Security Model]]), so the per-repo row doesn't carry credentials — just the App installation ID + the numeric GitHub repo ID (which survives renames).

```sql
CREATE TABLE workspace_context_repos (
  workspace_id          UUID PRIMARY KEY REFERENCES workspaces(id) ON DELETE CASCADE,
  provider              TEXT NOT NULL DEFAULT 'github',                  -- 'github' (future: 'gitlab', 'gitea')
  installation_id       BIGINT NOT NULL,                                 -- GitHub App installation ID (org-scoped)
  github_repo_id        BIGINT NOT NULL,                                 -- Numeric GitHub repo ID (survives rename)
  repo_owner            TEXT NOT NULL,                                   -- e.g. 'hirecharm' (cached for display)
  repo_name             TEXT NOT NULL,                                   -- e.g. 'charm-hypertide' (cached for display)
  branch                TEXT NOT NULL DEFAULT 'main',
  webhook_secret_id     UUID REFERENCES secrets(id),                     -- HMAC verification secret (GitHub App webhook secret, shared org-wide; cached per-row for fast lookup)
  last_synced_at        TIMESTAMPTZ,
  last_commit_sha       TEXT,
  sync_status           TEXT NOT NULL DEFAULT 'never_synced',
                        -- 'never_synced' | 'syncing' | 'ok' | 'failed' | 'auth_failed' | 'drift_detected'
  last_sync_error       TEXT,
  poll_interval_minutes INT NOT NULL DEFAULT 60,
  created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (github_repo_id)
);
```

Repo discovery: when a new client workspace is created, the operator picks the matching repo from a list of repos the GitHub App is installed on (`GET /api/v1/github/installations/{installationId}/repositories`). One repo = one workspace binding; cannot bind one repo to multiple workspaces.

### `workspace_context_documents`

One row per `.md` file in the repo (excluding `.claude/skills/` — those are admin-controlled and not client context).

```sql
CREATE TABLE workspace_context_documents (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  workspace_id    UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  path            TEXT NOT NULL,                       -- repo-relative, e.g. 'feedback/feedback_voice.md'
  content         TEXT NOT NULL,                       -- raw markdown body (excl. frontmatter)
  content_hash    TEXT NOT NULL,                       -- sha256 of full file (frontmatter + body)
  frontmatter     JSONB,                               -- parsed YAML frontmatter as JSON
  title           TEXT,                                -- frontmatter.name OR first H1
  doc_type        TEXT,                                -- frontmatter.type — 'spec'|'decision'|'note'|'feedback'|'moc'|'client-card' etc.
  status          TEXT,                                -- frontmatter.status — 'draft'|'review'|'final'|'stub'
  tags            TEXT[],                              -- frontmatter.tags ∪ inline #hashtags
  created_in_repo DATE,                                -- frontmatter.created
  commit_sha      TEXT NOT NULL,                       -- git SHA of the version pulled
  size_bytes      INT NOT NULL,
  indexed_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  fts             tsvector GENERATED ALWAYS AS (
                    setweight(to_tsvector('english', coalesce(title, '')), 'A') ||
                    setweight(to_tsvector('english', coalesce(array_to_string(tags, ' '), '')), 'B') ||
                    setweight(to_tsvector('english', content), 'C')
                  ) STORED,
  UNIQUE (workspace_id, path)
);

CREATE INDEX idx_context_docs_workspace      ON workspace_context_documents (workspace_id);
CREATE INDEX idx_context_docs_workspace_type ON workspace_context_documents (workspace_id, doc_type);
CREATE INDEX idx_context_docs_fts            ON workspace_context_documents USING gin (fts);
CREATE INDEX idx_context_docs_tags           ON workspace_context_documents USING gin (tags);
CREATE INDEX idx_context_docs_frontmatter    ON workspace_context_documents USING gin (frontmatter);
```

### `workspace_context_links`

Forward links extracted from `[[wiki-links]]`. `to_doc_id` may be NULL if the link points to a doc that doesn't exist yet (Foam supports forward-declared concepts).

```sql
CREATE TABLE workspace_context_links (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  workspace_id      UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  from_doc_id       UUID NOT NULL REFERENCES workspace_context_documents(id) ON DELETE CASCADE,
  to_path           TEXT NOT NULL,                     -- resolved repo-relative path (or 'concept-name' if unresolved)
  to_doc_id         UUID REFERENCES workspace_context_documents(id) ON DELETE SET NULL,
  link_text         TEXT,                              -- '[[link|display text]]' display part, if present
  context_snippet   TEXT,                              -- ~120 chars surrounding the link, for backlink previews
  source            TEXT NOT NULL DEFAULT 'inline',    -- 'inline' (in body) | 'frontmatter' (in related: [])
  UNIQUE (from_doc_id, to_path, source)
);

CREATE INDEX idx_context_links_from_doc        ON workspace_context_links (from_doc_id);
CREATE INDEX idx_context_links_to_doc          ON workspace_context_links (to_doc_id);
CREATE INDEX idx_context_links_workspace_to_path ON workspace_context_links (workspace_id, to_path);
```

### `workspace_context_syncs`

Audit trail of every sync attempt — feeds the Activity Log alongside daemon events + agent runs.

```sql
CREATE TABLE workspace_context_syncs (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  workspace_id      UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  trigger           TEXT NOT NULL,                     -- 'webhook' | 'poll' | 'on_demand' | 'first_install'
  started_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  completed_at      TIMESTAMPTZ,
  from_commit_sha   TEXT,
  to_commit_sha     TEXT,
  status            TEXT NOT NULL DEFAULT 'in_progress',  -- 'in_progress' | 'ok' | 'failed' | 'no_changes'
  docs_added        INT NOT NULL DEFAULT 0,
  docs_updated      INT NOT NULL DEFAULT 0,
  docs_deleted      INT NOT NULL DEFAULT 0,
  docs_unchanged    INT NOT NULL DEFAULT 0,
  links_added       INT NOT NULL DEFAULT 0,
  links_removed     INT NOT NULL DEFAULT 0,
  error_message     TEXT,
  duration_ms       INT
);

CREATE INDEX idx_context_syncs_workspace_started ON workspace_context_syncs (workspace_id, started_at DESC);
```

---

## Sync Architecture

### Primary: GitHub Webhook (push)

When a PR merges to `main` (or any push to `main` if branch protection allows direct pushes), GitHub POSTs a webhook to:

```
POST {CHARM_API_URL}/api/v1/webhooks/github/context-sync
Headers:
  X-GitHub-Event: push
  X-Hub-Signature-256: sha256=<hmac>
Body: GitHub push event JSON
```

CharmDB API:
1. Looks up the matching `workspace_context_repos` row by `(repo_owner, repo_name, branch)`.
2. Verifies `X-Hub-Signature-256` HMAC against the decrypted `webhook_secret_id`.
3. If signature valid and commit SHA differs from `last_commit_sha`, enqueues a sync job.
4. Returns `202 Accepted` (fire-and-forget; the sync worker handles the actual work).

Replay protection: discard events whose payload `head_commit.timestamp` is more than 24h old.

### Fallback: Hourly Poll

A `context_sync_scheduler` worker runs every 5 minutes and selects:

```sql
SELECT workspace_id FROM workspace_context_repos
WHERE sync_status NOT IN ('syncing', 'auth_failed')
  AND (
    last_synced_at IS NULL
    OR last_synced_at < now() - (poll_interval_minutes || ' minutes')::interval
  )
ORDER BY last_synced_at NULLS FIRST
LIMIT 10
FOR UPDATE SKIP LOCKED;
```

For each selected workspace, enqueue a poll-trigger sync job. This catches webhook misses (webhook endpoint down, signing failure, missed delivery) and handles repos without webhooks.

### Sync Worker (the job processor)

For each sync job:

1. **Insert sync row** in `workspace_context_syncs` with `status='in_progress'`.
2. **Update `workspace_context_repos.sync_status='syncing'`** (advisory lock — prevents concurrent syncs of the same repo).
3. **Fetch ref:** `git ls-remote <auth-url> refs/heads/<branch>` → get current commit SHA. Compare to `last_commit_sha`:
   - Equal → `status='no_changes'`, update `last_synced_at`, done.
   - Different → proceed.
4. **Shallow clone or sparse-checkout** the repo at the new commit. Two viable approaches:
   - **A. Shallow clone** (`git clone --depth=1 --branch <branch>` to ephemeral dir). Simple, works everywhere.
   - **B. GitHub Contents API** (`GET /repos/{owner}/{repo}/contents/{path}?ref=<sha>`) — no git binary needed, rate-limited but fine for small repos.

   **Recommendation: A (shallow clone)** for v1 — handles binary files, attachments, scales to large repos better. Use a working dir like `/tmp/charm-sync/<workspace_id>/`.
5. **Walk `.md` files** (excluding `.claude/`, `node_modules/`, `.git/`, hidden dirs). For each file:
   - Parse frontmatter with `gray-matter` (Node) or `python-frontmatter`.
   - Compute SHA256 of full file content.
   - If `content_hash` matches existing row → `docs_unchanged++`, skip.
   - Otherwise → upsert into `workspace_context_documents`, extract wiki-links, replace `workspace_context_links` rows for this doc.
6. **Detect deletes:** any `path` in DB but not in the new commit → delete the row (cascade removes its links).
7. **Resolve unresolved links:** for any `workspace_context_links` row with `to_doc_id IS NULL`, try to resolve `to_path` against current docs (Foam wiki-links resolve by basename — `[[client]]` matches any file whose name is `client.md`).
8. **Update `workspace_context_repos`** with `last_commit_sha`, `last_synced_at`, `sync_status='ok'`.
9. **Finalize `workspace_context_syncs`** with counts + duration.
10. **Emit event** to `agent_run_log` so dashboards / agent runtime see the new context. Optionally wake interested agents (e.g., Account Manager).

### Failure handling

- Auth failure (401/403 from GitHub) → `sync_status='auth_failed'`, do NOT retry until operator rotates the token.
- Network failure → mark `failed`, retry on next poll (exponential backoff up to 6h).
- Parse failure on a single doc → log to `last_sync_error`, skip that doc, continue.
- Webhook signature mismatch → return 401, log the event for security audit.

---

## Markdown Parser

### Frontmatter

YAML between `---` delimiters at file top. Parse with `gray-matter` or equivalent. Extract:

- `name` → `documents.title`
- `description` → kept in `frontmatter` jsonb for FTS weight
- `type` → `documents.doc_type` (enum-ish: `spec`, `decision`, `research`, `guide`, `reference`, `pattern`, `moc`, `index`, `client-card`, `note`, `feedback`)
- `tags` → first source for `documents.tags`
- `created` → `documents.created_in_repo`
- `status` → `documents.status`
- `related` (array of `"[[link]]"` strings) → emit as `source='frontmatter'` rows in `workspace_context_links`

If frontmatter is missing or unparseable, log a warning and store an empty `frontmatter='{}'::jsonb`. Don't fail the doc.

### Wiki-links

Regex: `\[\[([^\]|]+?)(?:\|([^\]]+))?\]\]` (matches `[[link]]` and `[[link|display]]`).

For each match:
- Capture group 1 → `to_path` (raw — basename of the target; resolution happens in step 7 above)
- Capture group 2 → `link_text` (optional display text)
- Surrounding ~120 chars → `context_snippet`
- Source → `'inline'`

### Tags

Two sources, unioned:
- `frontmatter.tags` (array of strings)
- Inline `#hashtag` patterns in body (regex `(?<!\w)#([a-z][a-z0-9_-]+)` — case-sensitive lowercase; avoid false positives on `#` headings or URL fragments)

### What we DON'T parse v1

- PDFs / images in `assets/` — store nothing about them. v2 may add OCR.
- Code blocks — kept inline in `content`; FTS will pick them up if relevant.
- HTML embedded in markdown — kept inline.
- Heading hierarchy structure (h1/h2/h3 tree) — kept as part of `content`; not separately indexed v1.

---

## Context-Query API (for analyst agents)

These are the endpoints agent skills will call as tools. Auth: same as agent runtime — short-lived JWT in `Authorization: Bearer <CHARM_API_KEY>`. Scoped to the workspace the agent runs against (cross-workspace queries denied unless the agent has a global scope).

### Search

```
GET /api/v1/workspaces/{workspaceId}/context/search?q=<query>&type=<doc_type>&tag=<tag>&limit=20
```

Postgres FTS rank-ordered. Returns:
```json
{
  "results": [
    {
      "path": "feedback/feedback_voice.md",
      "title": "Voice — say technical, not corporate",
      "doc_type": "feedback",
      "tags": ["voice", "tone"],
      "snippet": "...the client corrected us on Friday — they want 'engineer-to-engineer' tone, not 'sales-to-marketer'...",
      "score": 0.78,
      "updated_at": "2026-05-12T14:32:00Z"
    }
  ],
  "total": 3,
  "context_freshness": {
    "last_synced_at": "2026-05-15T09:14:00Z",
    "last_commit_sha": "a3b7c9d",
    "minutes_since_sync": 47
  }
}
```

`context_freshness` is critical: agents must know how stale their context is. A recommendation made off 3-day-old context should be flagged.

### Fetch document

```
GET /api/v1/workspaces/{workspaceId}/context/document?path=feedback/feedback_voice.md
```

Returns full content + frontmatter + tags + outbound links + inbound backlinks.

### Backlink graph

```
GET /api/v1/workspaces/{workspaceId}/context/graph?path=client.md&depth=2
```

Returns the local backlink graph around a given doc — outbound + inbound + linked-to-linked (BFS to depth=2). Useful for agents that want to navigate Foam-style.

### Recent

```
GET /api/v1/workspaces/{workspaceId}/context/recent?since=2026-05-10&type=feedback,decision
```

Returns documents updated (committed) since a date, filtered by type. Use case: Performance Analyst checks "any new feedback or decisions in the last 7 days that should inform my analysis?"

### Client card (convenience)

```
GET /api/v1/workspaces/{workspaceId}/context/client-card
```

Returns the parsed `client.md` as structured JSON — first-class access to IDs, voice rules, banned phrases, ICP, stakeholders. Skills depend on this heavily; making it a dedicated endpoint avoids repeated path lookups.

---

## Security Model

### GitHub App (day-one)

Decided 2026-05-15. We have an org GitHub (`hirecharm`), so PATs and deploy keys are skipped — a single GitHub App installation handles all client repos under the org.

**App registration (one-time):**
1. Register a GitHub App in the `hirecharm` org settings: name "Charm Context Sync"
2. **Permissions:** `Repository contents: Read`, `Metadata: Read`, `Pull requests: Read` *(for surfacing AE branch activity)*, `Webhooks: Read & Write`
3. **Subscribe to events:** `Push`, `Pull request` *(for AE-branch visibility)*, `Repository` *(rename/delete detection)*, `Installation` *(new client repo added → auto-create workspace binding)*
4. **Webhook URL:** `{CHARM_API_URL}/api/v1/webhooks/github/context-sync`
5. **Webhook secret:** random 32-byte string, stored encrypted in `secrets` table (single org-wide secret, cached per row in `workspace_context_repos.webhook_secret_id`)
6. **Install** on `hirecharm` org → select "All repositories" (catches new client repos as they're scaffolded from `charm-client-template`)
7. **Download App private key** (PEM) → store encrypted in `secrets` as `github_app_private_key`

**Three secret types in `secrets` table for this feature:**

| Secret type | Scope | Purpose | Rotation |
|-------------|-------|---------|----------|
| `github_app_private_key` | Global (org-wide) | Sign JWTs for GitHub API auth | Manual, rare (only on key compromise) |
| `github_webhook_secret` | Global (org-wide, cached per workspace) | HMAC-verify incoming webhooks | Manual on compromise |
| (none per workspace) | — | Installation tokens are minted on demand from the App private key; no per-workspace credential storage | — |

**Auth flow at request time:**
1. Sync worker needs to clone repo for workspace X
2. Looks up `installation_id` from `workspace_context_repos`
3. Signs a JWT with `github_app_private_key`, exp 10 min, iss = App ID
4. `POST /app/installations/{installation_id}/access_tokens` with JWT → returns installation token (exp 1 hour)
5. Uses installation token in `Authorization: Bearer ...` for git clone + GitHub API calls
6. Token expires automatically; next sync mints a fresh one (cache for ≤ 50 min)

**Why this is better than PAT day-one:**
- No per-workspace tokens to provision / rotate / revoke
- No user dependency (no "Bob owned the PAT and left")
- Installation events auto-detect new client repos → auto-create `workspace_context_repos` rows (subject to workspace-binding confirmation by operator)
- GitHub audit log shows "Charm Context Sync App did X" — clean attribution

### Webhook HMAC

GitHub App posts webhooks signed with the global webhook secret. Verify on every request:

```python
expected = "sha256=" + hmac.new(decrypted_webhook_secret, body, hashlib.sha256).hexdigest()
if not hmac.compare_digest(expected, request.headers["X-Hub-Signature-256"]):
    return 401
```

Reject events with `installation.id` not matching any known `workspace_context_repos.installation_id` (or the global installation row, for `Installation` events themselves).

### Per-workspace scoping

Agent JWTs are scoped to a workspace (`CHARM_WORKSPACE_ID` env var). The context-query API enforces:

- Workspace A's agent → can only query workspace_id=A's context
- Global-scoped agents (rare — e.g., a future cross-workspace synthesizer) → must have an explicit `scope: global` claim in the JWT

### What's NOT in the repo (and shouldn't be)

Per template convention: `client.md` already says "API key reference: TBD — secret store name, never the key itself." The repo never contains live credentials — only references to keys stored in CharmDB's `secrets` table. The sync worker doesn't extract or care about credential references; it just indexes them as text. Agents that need a credential call the secrets API directly.

---

## Integration with Agent Runtime

This spec is **a data source for [[agent-runtime]]**, not a separate runtime. Analyst agents consume client context as one input among others (DB metrics, EB API state, Hypertide API state).

### How skills use context

Example: `skills/burn-velocity-analysis/SKILL.md` (Performance Analyst skill) would say:

> Before running burn-velocity analysis, fetch the client's voice + tone preferences from the context repo so your recommendations match how the client wants to be addressed:
>
> ```
> GET /api/v1/workspaces/{CHARM_WORKSPACE_ID}/context/client-card
> ```
>
> Also check for any recent (last 14 days) feedback about deliverability complaints:
>
> ```
> GET /api/v1/workspaces/{CHARM_WORKSPACE_ID}/context/search?q=deliverability+complaint&since=2026-05-01
> ```
>
> If `context_freshness.minutes_since_sync > 240` (4h), include a caveat in your recommendation: "Context is N hours stale — operator may have newer AE notes not yet pulled."

### Context citation in recommendations

When an agent surfaces a `request_confirmation` interaction (paperclip pattern), the payload should include cited context docs:

```json
{
  "kind": "request_confirmation",
  "payload": {
    "prompt": "Rotate these 5 domains?",
    "summary": "...",
    "cited_context": [
      { "path": "decisions/DECISION_burn-threshold.md", "commit_sha": "a3b7c9d", "relevance": "policy gate" },
      { "path": "feedback/feedback_aggressive-rotation.md", "commit_sha": "a3b7c9d", "relevance": "client preference" }
    ]
  }
}
```

The operator sees these citations inline in the recommendation card. Clicking a citation opens the doc (read-only, rendered) so the operator can verify the agent's grounding before approving.

### Activity log integration

Sync events surface in the workspace Activity Log:

```
2026-05-15 09:14  context-sync  ok  +2 docs, +1 deleted, +7 links  (commit a3b7c9d ← f12e8a4)
2026-05-15 09:14  agent-run     Performance Analyst woke (context-changed trigger)
```

The "context-changed" trigger optionally wakes interested agents — opt-in per agent config.

---

## Implementation Roadmap

| Phase | Scope | Depends on |
|-------|-------|------------|
| **0** | Frontend redesign carries the Context surface in mockup form (workspace card shows "Context: 47m fresh"; workspace detail has Context sub-page) | — |
| **1a** | **GitHub App registration** in `hirecharm` org. Install on org with "All repositories." Capture App ID, installation ID, private key, webhook secret. Store private key + webhook secret encrypted in `secrets`. | Existing `secrets` table |
| **1b** | DB migrations: `workspace_context_repos`, `workspace_context_documents`, `workspace_context_links`, `workspace_context_syncs`. | Phase 1a |
| **2** | Sync worker: GitHub-App-token mint → shallow clone → parse → upsert. Poll-only trigger. Operator wires first workspace by picking from the App's installed-repos list. | Phase 1b |
| **3** | Context-query API (`/search`, `/document`, `/recent`, `/client-card`). Returns structured JSON with `context_freshness`. | Phase 2 |
| **4** | GitHub webhook endpoint at `/api/v1/webhooks/github/context-sync` + HMAC verification. Handle `push`, `repository`, `installation` events. | Phase 3 |
| **5** | Integration with agent runtime — first skill that uses context (`burn-velocity-analysis` for Performance Analyst). Cite context docs in `request_confirmation` payloads. | [[agent-runtime]] Phase 3, this spec Phase 3 |
| **6** | Backlink graph endpoint (`/context/graph`) + UI in workspace detail to render the Foam graph for AE / operator browsing. | Phase 3 |
| **7** | Vector embeddings (pgvector) for semantic search if FTS is insufficient for agent retrieval quality (especially on long Day AI transcripts). | Phase 5 (driven by agent recall measurements) |
| **8** | Auto-binding flow: when an `installation` webhook fires for a new repo added under `hirecharm`, surface a "New repo detected — bind to which workspace?" prompt in the operator dashboard. | Phase 4 |

## Open Questions

1. **`.claude/skills/` ingestion:** The skill library inside client repos is admin-controlled, mostly Charm methodology. Skip ingesting these into context (recommended — they're not client data; they're our methodology), or index them so agents can reference Charm-internal patterns? *Recommendation: skip v1; index v2 if agents need methodology access.*

2. **`assets/` binary handling:** PDFs, images, brand kits. Out of scope v1 (don't index). v2 could OCR PDFs or describe images using Claude. For now, store the path (file existed at this commit) but no content.

3. **Cross-repo references:** The template mentions `charm-microsoft-infra` as a sibling repo. Some docs cross-reference between client repos and shared sibling repos. v1 treats these as unresolved links (`to_doc_id=NULL`); v2 could ingest shared sibling repos into a separate `shared_context_documents` table.

4. **Day AI transcripts handling:** ~~`notes/transcripts/` is the Day AI landing zone~~ **DECIDED 2026-05-15:** Day AI writes markdown transcripts directly to the client repo at `notes/transcripts/`. CharmDB ingests them as-is alongside any other doc — no summarization, no separate handling, no special endpoint. Sync mechanism is "pull git, get latest context." A 1-hour call transcript is ~50–100KB markdown — Postgres TEXT + tsvector handle this fine. If FTS retrieval quality drops with very long transcripts, address with pgvector embeddings (already on the roadmap as Phase 7), not with sync-time summarization.

5. **Bison cron output handling:** `gtm/reports/` is populated by an existing backend cron. Do we ingest its output as context (so agents see recent reports the AE has been working with), or skip (it's CharmDB-sourced data that the agent can query directly)? *Recommendation: ingest — having the report in the AE's reading context matters for the agent to understand what the AE has been looking at.*

6. **Sync triggers waking agents:** Should every sync event wake interested agents (Account Manager wakes when client.md changes), or should agents only wake on heartbeat schedule? *Recommendation: opt-in per agent — `wake_on_context_change: ['client.md', 'decisions/**']`.*

7. **Delete safety:** If a `.md` file is removed from the repo (e.g., AE accidentally `git rm`), the document and its links are deleted from CharmDB. The agent runtime might already be mid-analysis citing that doc. Mitigations: keep deleted docs in a `_deleted` shadow table for 30 days; warn agents in `cited_context` if the cited commit_sha is older than current.

8. **Repo discovery:** Operator-initiated (operator clicks "wire a repo" in workspace settings, paste URL + token), or template-driven (when a new workspace is created from a client onboarding, auto-provision a repo from `charm-client-template` and wire it)? *Recommendation: both. Operator wire-up for existing clients (already have a repo); template auto-provision for new client onboarding.*

## See Also

- [[agent-runtime]] — the consumer of context (analyst agents read context as a data source)
- [[design-system/brand-brief]] — UI surfaces (workspace Context sub-page, freshness indicator on workspace card)
- [[design-system/references/ref-paperclip]] — paperclip Approval/Recommendation mechanic that cites context
- [`charm-client-template/CLAUDE.md`](D:\Work\Charm\charm-client-template\CLAUDE.md) — repo-side conventions (frontmatter, wiki-links, MOCs, AE workflow)
- [`charm-client-template/client.md`](D:\Work\Charm\charm-client-template\client.md) — `client.md` schema (Charm OS record ID → CharmDB workspace binding)
- [docs/concepts/esp-aware-data-interpretation.md](../concepts/esp-aware-data-interpretation.md) — required reading for any analyst skill that interprets ESP-split data
