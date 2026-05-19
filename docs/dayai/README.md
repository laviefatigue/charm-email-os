# `docs/dayai/` — Day.AI integration + per-client repo documentation

Hub for everything related to the Day.AI -> charm-email-os -> per-client
GitHub repo pipeline.

## Read these in order

1. **`HANDOFF_client_repo_pipeline.md`** — technical handoff. What was built,
   current deployed state (Coolify app, env vars, postgres tables), file
   index, quick recipes, decisions log. Start here if you're picking up
   the work.

2. **`CONCEPT_client_repo.md`** — what the per-client repo is FOR and how
   it's USED. The role in the agency operating model, the four audiences
   (humans in VS Code, Claude Code agents, automation scripts,
   charm-email-os frontend), what goes in vs. what stays in the source
   system, daily/weekly workflows, the never-delete discipline. Read
   this before designing new automations that touch client repos.

3. **`SPEC_secrets.md`** — the auth keystone. `secrets`
   table + `api/services/github_app.py` helper. Every worker and API
   route that talks to GitHub uses this. Implementation companion to
   the canonical spec's §Security Model. Read before building
   anything that touches GitHub.

4. **`../architecture/client-context-sync.md`** — **canonical**
   architecture for how charm-email-os reads + writes per-client repo
   content (workspace_context_* tables, sync worker, context-query
   API, GitHub App webhook). Read this before touching the workspace
   Context tab or the consumption-side pipeline. *Lives under
   `docs/architecture/`, not `docs/dayai/`, because it predates this
   folder and is owned by the broader charm-email-os architecture
   sweep.*

5. **`SPEC_charm_os_repo_access.md`** — **superseded** by
   client-context-sync.md (above). Kept as a redirect stub.

6. **`ROADMAP_dayai_automation.md`** — future automations built on top of
   the `dayai/` package and per-client repos. Concrete catalog of
   workers, syncs, triggers, and agents — with dependencies + sequencing.
   Use this to pick the next thing to build.

## Related code locations

| Path | What |
|---|---|
| `dayai/` | Reusable Day.AI client package (auth, MCP, client, objects) |
| `dayai_watcher_worker.py` | Worker — closed-won detector |
| `Dockerfile.dayai-watcher` | Runtime image |
| `requirements-dayai.txt` | Worker dependencies |
| `migrations/093_dayai_watcher_state.sql` | Schema |
| `scripts/dayai/` | One-off scripts (synthesizers, onboarders) — reference impls to extend |

## Related external repos

| Repo | What |
|---|---|
| `HireCharm/client-template` | Template repo — every new client repo clones from here |
| `HireCharm/client-sammy` | Worked example with full enrichment |
| `charm-kb` (separate clone) | Agency-wide decisions, runbooks, skills library (NOT per-client) |

## Conventions

- **Doc filenames** — UPPER_SNAKE_CASE with leading category:
  `HANDOFF_*` (transition docs), `CONCEPT_*` (vision/role docs),
  `ROADMAP_*` (future-work catalogs), `RUNBOOK_*` (operational
  procedures), `DECISION_*` (frozen choices with tradeoffs)
- **Frontmatter** on every doc (matches Foam convention used in client repos)
- **Cross-references** via `[[wiki-links]]` where docs exist in the same folder
