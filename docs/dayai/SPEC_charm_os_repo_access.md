# Spec — charm-email-os ↔ client repo access pattern

> How charm-email-os's backend reads from and writes to per-client
> GitHub repos to power the **Context** and **Assets** sections of
> the frontend. Direct GitHub access, no mirror table, no sync worker
> — at least until rate-limit or latency pressure forces a change.
>
> Paired with `SPEC_app_credentials.md` (the auth primitive this spec
> consumes) and `CONCEPT_client_repo.md` §4 Audience D (the
> architectural framing).

---

## 1. Architectural shape (one paragraph)

The GitHub repo is the source of truth. charm-email-os is a thin
operator surface over it. Frontend renders by calling
`GET /api/clients/{id}/context/...`; uploads land via
`POST /api/clients/{id}/assets`. Backend uses
`api/services/github_app.py` to authenticate and proxies bytes to/from
GitHub. The `clients` table gets one column — `context_repo` — that
points the backend at the right repo. No `client_repo_content` mirror
table, no sync worker, no webhooks. If/when we feel rate-limit pain,
caching gets bolted on at the API layer; the data model doesn't change.

---

## 2. Connecting a client record to its repo

### Schema change — `migrations/113_clients_context_repo.sql`

```sql
-- Migration 113: Add context_repo pointer to clients table
--
-- Explicit "this client's GitHub context repo" pointer. Stored as
-- the full owner/name string (e.g. "HireCharm/client-sammy") so
-- backend code doesn't need to know about the slug-vs-name distinction.
-- Nullable: legacy clients may not have a repo yet; new clients get
-- it populated by the onboarding flow.

ALTER TABLE clients
    ADD COLUMN IF NOT EXISTS context_repo TEXT;

CREATE INDEX IF NOT EXISTS idx_clients_context_repo
    ON clients (context_repo) WHERE context_repo IS NOT NULL;

COMMENT ON COLUMN clients.context_repo IS
    'GitHub repo holding this client''s context engine. Format: "owner/name", e.g. "HireCharm/client-sammy". NULL for clients that don''t have a repo yet.';
```

### Why an explicit column, not slug-derivation

The pattern `f"HireCharm/client-{slugify(client.name)}"` is tempting
but breaks the moment:
- A client's display name changes (`slugify` is no longer stable)
- Two clients have similar names producing the same slug
- A client repo gets renamed in GitHub for any reason
- An admin manually creates a repo with a non-standard name

Explicit storage of the resolved repo name handles all of these. The
onboarding flow does the slugification ONCE on repo creation and
writes the result into `context_repo`. Everything else reads.

---

## 3. API surface

All routes scoped under `/api/clients/{client_id}/`. Authentication
piggybacks on the existing client-record auth — if you can read the
client, you can read its repo content; if you can edit the client,
you can write to its repo.

### 3.1 Context routes (markdown content)

| Route | Purpose | Returns |
|---|---|---|
| `GET /api/clients/{id}/context` | List markdown files in the repo, top-level + recursive into `notes/`, `decisions/`, `feedback/`, `onboarding/`, `gtm/` (NOT `assets/`, NOT `.claude/`) | `{ files: [{ path, frontmatter, last_modified, sha }] }` |
| `GET /api/clients/{id}/context/file?path=<repo-relative-path>` | Read one file's full content + parsed frontmatter | `{ path, content, frontmatter, sha }` |
| `PUT /api/clients/{id}/context/file` | Create or update a markdown file (body: `{ path, content, message? }`) | `{ path, sha, commit_url }` |

Frontmatter parsed server-side using `python-frontmatter`. Frontend
sees clean JSON; doesn't need to parse YAML.

### 3.2 Asset routes (raw files)

| Route | Purpose | Returns |
|---|---|---|
| `GET /api/clients/{id}/assets` | List files in `assets/` of the repo with size, mime hint, last_modified | `{ files: [{ name, path, size, mime_type, last_modified }] }` |
| `GET /api/clients/{id}/assets/file?path=<filename>` | Stream a single asset file. Content-Type set from filename + GitHub's content-type. | streaming bytes |
| `POST /api/clients/{id}/assets` | Multipart upload — drops file into `assets/<filename>` in the repo | `{ name, path, sha, commit_url }` |
| `DELETE /api/clients/{id}/assets/file?path=<filename>` | Move file to `assets/.archived/<filename>_<timestamp>` (NEVER hard-delete — accumulation discipline from CONCEPT §6 applies to assets too) | `{ archived_path }` |

Important: the DELETE is a **soft move into `.archived/`** because
`CONCEPT_client_repo.md` §6 forbids deleting content. Same rule applies
to assets — historical brand guides etc. stay accessible.

### 3.3 Repo metadata route

| Route | Purpose | Returns |
|---|---|---|
| `GET /api/clients/{id}/repo` | Repo-level info: `context_repo` value, `client.md` frontmatter parsed, template_version, last_synced, commit count, default branch | `{ repo, client_frontmatter, template_version, ... }` |

This is what powers the top of the Context tab — the identity card.

---

## 4. Backend implementation outline

New file: `api/services/client_repo.py`

```python
"""Direct read/write access to a client's HireCharm/client-<slug> repo.

Thin wrappers over GitHub's contents + git-data APIs. Uses
api/services/github_app.py for auth. No caching at this layer —
caching, if added later, lives in a separate layer (see §8).
"""
from __future__ import annotations
import base64

import frontmatter
import httpx

from .github_app import gh_client


class ClientRepoError(Exception):
    pass


async def list_context_files(pool, context_repo: str) -> list[dict]:
    """Tree-walk repo for .md files in known content shelves."""
    async with await gh_client(pool) as gh:
        # Use the git tree API (recursive=1) — one call returns the whole tree
        # Then filter to the shelves we care about
        ...


async def read_file(pool, context_repo: str, path: str) -> dict:
    """Fetch a single file's content + parse frontmatter (for .md)."""
    async with await gh_client(pool) as gh:
        resp = await gh.get(f"/repos/{context_repo}/contents/{path}")
        resp.raise_for_status()
        data = resp.json()
        body = base64.b64decode(data["content"]).decode("utf-8")
        if path.endswith(".md"):
            post = frontmatter.loads(body)
            return {
                "path": path,
                "content": post.content,
                "frontmatter": dict(post.metadata),
                "sha": data["sha"],
            }
        return {"path": path, "content": body, "frontmatter": None, "sha": data["sha"]}


async def write_file(
    pool, context_repo: str, path: str, content: str, message: str
) -> dict:
    """Create or update a file via the contents API."""
    async with await gh_client(pool) as gh:
        # GET current sha (if exists) for the update path
        existing = await gh.get(f"/repos/{context_repo}/contents/{path}")
        sha = existing.json()["sha"] if existing.status_code == 200 else None

        body = {
            "message": message,
            "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
        }
        if sha:
            body["sha"] = sha

        resp = await gh.put(f"/repos/{context_repo}/contents/{path}", json=body)
        resp.raise_for_status()
        out = resp.json()
        return {
            "path": path,
            "sha": out["content"]["sha"],
            "commit_url": out["commit"]["html_url"],
        }


async def upload_asset(
    pool, context_repo: str, filename: str, bytes_: bytes, message: str
) -> dict:
    """Upload a binary asset into assets/<filename>."""
    path = f"assets/{filename}"
    async with await gh_client(pool) as gh:
        body = {
            "message": message,
            "content": base64.b64encode(bytes_).decode("ascii"),
        }
        resp = await gh.put(f"/repos/{context_repo}/contents/{path}", json=body)
        resp.raise_for_status()
        out = resp.json()
        return {
            "name": filename,
            "path": path,
            "sha": out["content"]["sha"],
            "commit_url": out["commit"]["html_url"],
        }


async def archive_asset(
    pool, context_repo: str, filename: str, message: str
) -> dict:
    """Move assets/<filename> to assets/.archived/<filename>_<timestamp>."""
    # Implementation: read current, write to archived path, delete original.
    # Three commits in sequence (could batch via git-data API for atomicity).
    ...
```

Routes in `api/routes/client_repo.py` are thin handlers calling these
service functions and shaping the response.

---

## 5. Frontend shape

Two new pages under `charm-email-os/app/clients/[clientId]/`:

```
charm-email-os/app/clients/[clientId]/
  context/
    page.tsx          # browse + read .md context files
    [...path]/
      page.tsx        # single-file view (markdown render + frontmatter sidebar)
  assets/
    page.tsx          # grid of asset thumbnails + upload dropzone + download
```

Behavior:

- **Context tab**: file-explorer style left rail (collapsible by shelf:
  notes/, decisions/, feedback/, etc.), markdown preview on the right,
  frontmatter rendered as a sidebar pill set. Edit-in-place hidden
  behind a "Edit in GitHub" button until proven needed in-UI.
- **Assets tab**: grid of asset cards. Click to download. Drop-zone at
  top for upload. Right-click → "Archive" (soft-delete via the
  DELETE route).

Both pages call only the API routes in §3 — no direct GitHub access
from the browser.

---

## 6. Failure modes + defaults

| Failure | What happens | Recovery |
|---|---|---|
| `context_repo` is NULL on client record | Both tabs show "No context repo yet — create one?" CTA. Button kicks off the reconciler for this client. | Operator action |
| GitHub API 5xx | API route returns 502 with `{ retry_after_seconds }`. Frontend shows banner "GitHub temporarily unavailable, retry in N seconds." | Auto-retry on client; manual retry button |
| GitHub API 429 (rate limit) | API route returns 429 with rate-limit headers. Frontend shows "Rate limit hit, retry at HH:MM." Heavy clue we need caching. | See §8 |
| Installation token expired mid-flight | `github_app.py` cache TTL is 55 min; tokens valid for 60. Window is narrow. If we hit it: retry once after force-refreshing the cache. | Automatic |
| File doesn't exist (404) | Return 404 from the API route. Frontend shows "Not found" page in the context viewer. | Operator can create via Edit button |
| Concurrent edit (two writers, second commit fails with sha mismatch) | API route returns 409. Frontend shows "Out of date — reload?" | User reloads, re-edits |

No retries inside the API layer for read paths — failures surface to
the user immediately. Write paths get one retry on transient errors
(connection reset, etc.), no retry on 4xx.

---

## 7. What this spec does NOT cover

- **Search across all clients.** Out of scope for v1. If you want to
  "find all clients with feedback_word_optimize," that's a separate
  cross-repo search service (ROADMAP Tier 3.3). The per-client browse
  flow doesn't need it.
- **Branch/PR workflow.** All writes go directly to `main`. The git
  history IS the audit trail; we don't need a review workflow for AE
  uploads. (Workers commit directly too.)
- **Inline markdown editing.** v1 = view + upload assets. Editing
  markdown happens in VS Code / Claude Code. We can add inline edit
  later if AEs ask for it.
- **Permissions inside the repo.** All Charm employees with
  charm-email-os access see the same content; GitHub-side access is
  controlled at the org/team level, not per-file.
- **Cross-repo aggregations.** "Show me all decisions across all
  clients tagged with #pricing" — a future cross-client index, not
  this spec.

---

## 8. When to add caching (and what shape it would take)

The default is direct access. Caching gets added **only when** we
observe one of:

1. **Rate-limit pressure** — repeated 429s, or sustained usage above
   ~3,000 req/hr (60% of the 5,000/hr ceiling)
2. **Latency complaints** — page-load p95 > 1.5s attributed to
   GitHub fetches
3. **GitHub outage exposure** — operators want to keep reading client
   context during a GitHub incident

If/when one of these happens, the shape of caching:

- A new table `client_repo_content_cache` (sha + path + content +
  frontmatter JSONB + cached_at) populated by either:
  - A scheduled poller (every N minutes, walk each repo's tree, fetch
    changed blobs)
  - A GitHub webhook on `push` events (more reactive, more setup)
- Read path: API routes check cache first, fall back to GitHub, write
  back to cache on cache miss
- Write path: writes still go directly to GitHub; cache invalidates
  the affected rows in the same transaction

Documenting this here so anyone hitting the breakpoint knows the shape
to build, without having to re-derive it. **But don't build it now.**
Every direct-access feature is one less moving part.

---

## 9. Integration with the rest of the pipeline

This spec is the consumer side of `SPEC_app_credentials.md`. Other
consumers of the same `github_app.py` helper:

- `apps/client-repo-reconciler/` (ROADMAP Tier 1.4) — creates repos +
  pushes enriched files when watcher detects closed-won
- `apps/dayai-meeting-sync/` (ROADMAP Tier 1.5) — writes
  `notes/meetings/*.md` daily
- `apps/dayai-daily-sync/` (ROADMAP Tier 2.3) — refreshes
  `client.md` + `notes/status.md` + `notes/insights.md` daily
- Future `apps/eb-report-sync/` (ROADMAP Tier 2.x) — writes weekly
  `gtm/reports/*.md` with performance metrics

All four reuse `gh_client(pool)` — no service rolls its own auth.

---

## End

Build order: `app_credentials` table + `github_app.py` ship first
(`SPEC_app_credentials.md`), then this spec's pieces land on top:

1. Migration 113 (clients.context_repo column)
2. `api/services/client_repo.py` (service module from §4)
3. `api/routes/client_repo.py` (route handlers from §3)
4. Frontend pages under `app/clients/[clientId]/context/` and `/assets/`

Each can land as its own PR. The schema change is reversible (just a
nullable column add); the rest is additive.
