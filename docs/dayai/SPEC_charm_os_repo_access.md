# ⚠️ Superseded — see `docs/architecture/client-context-sync.md`

> **Status:** This document is **superseded** as of 2026-05-19.
>
> An earlier (and more elaborate) canonical spec for how
> charm-email-os reads + writes per-client GitHub repos already
> exists at:
>
> [`docs/architecture/client-context-sync.md`](../architecture/client-context-sync.md)
>
> That spec is the source of truth. It uses a **DB-mirror**
> architecture (sync worker + `workspace_context_documents` /
> `workspace_context_links` / `workspace_context_syncs` tables) with
> full-text search and backlink graphs, keyed by `workspace_id`. The
> Context tab in the workspace UI
> ([`app/workspaces/[id]/context/page.tsx`](../../charm-email-os/app/workspaces/[id]/context/page.tsx))
> is the surface it powers.
>
> The original content of this file proposed a **direct-read** pattern
> keyed by `client_id`, with new `clients.context_repo` column +
> `app/clients/[clientId]/context|assets/` routes. That proposal
> conflicted with the canonical spec on architecture (direct-read vs
> DB-mirror), keying (client vs workspace), and route placement
> (clients vs workspaces). The canonical spec wins on all three.
>
> **Where to go for what:**
>
> | Topic | Canonical doc |
> |---|---|
> | Workspace ↔ repo binding | [client-context-sync.md §Data Model](../architecture/client-context-sync.md#data-model) |
> | Sync architecture (webhook + poll) | [client-context-sync.md §Sync Architecture](../architecture/client-context-sync.md#sync-architecture) |
> | Markdown parser, frontmatter, wiki-links | [client-context-sync.md §Markdown Parser](../architecture/client-context-sync.md#markdown-parser) |
> | Context-query API for agents + UI | [client-context-sync.md §Context-Query API](../architecture/client-context-sync.md#context-query-api-for-analyst-agents) |
> | Auth (GitHub App, webhook HMAC) | [client-context-sync.md §Security Model](../architecture/client-context-sync.md#security-model) |
> | Implementation companion (table shape, helper module) | [SPEC_secrets.md](SPEC_secrets.md) |
>
> What this PR-branch's work **does** contribute (and stays in scope):
>
> - The **creation** side of the pipeline (Charm Onboarder App → repo
>   provisioning from template → enrichment with 5 v0.4 files) lives
>   upstream of the canonical sync spec. The reconciler worker
>   (ROADMAP Tier 1.4) creates repos; the canonical sync worker
>   ingests them. These are complementary, not competing.
> - The `secrets` table + `github_app.py` helper (Tier 1.0) is the
>   shared auth primitive both pipelines consume. Spec'd in
>   [SPEC_secrets.md](SPEC_secrets.md).
>
> Do not extend this file. New work on the consumption side belongs
> in client-context-sync.md or a sibling doc next to it.
