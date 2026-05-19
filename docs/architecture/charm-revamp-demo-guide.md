# Charm revamp demo guide

Quick walkthrough of what changed in this pass. Frontend-only — no database mutations have been applied yet (migrations 119-121 are on disk, waiting for the next charm-api deploy).

## Open the dev server

If the dev server isn't already up:

```powershell
cd D:\Work\Charm\charm-email-os\charm-email-os
pnpm dev
```

Then open **http://localhost:3000**.

## What to click

### 1. Home — workspace list (unchanged)
- URL: `/`
- No changes here. Pick any workspace to enter.

### 2. Workspace shell — **NEW: operator-CEO subheader**
- URL: `/workspaces/{workspace-id}` (e.g. click any workspace from home)
- **What's new:** Under the workspace title there's now a small italicized line:
  > *"You're the CEO of {Workspace Name} — agents propose, you approve."*
- This appears on every workspace page (Overview, Projects, Tasks, Assets, etc.) because it's wired into the workspace `layout.tsx`.

### 3. Assets tab — **NEW: template-aware rendering with icons + descriptions**
- URL: `/workspaces/{workspace-id}/assets`
- **What's new:**
  - Filter chips now show a lucide icon per template (📊 Analysis, 🔍 Research, 💬 Review, etc.)
  - Hovering a chip shows the template description as a tooltip
  - List rows show the full template title (e.g. "Analysis Report" not just "Analysis") with an icon-prefixed badge
  - Hovering a badge shows the template's purpose
- Note: today, all this is fed from a local constant in `assets/page.tsx` that mirrors the canonical seed in [migration 120](../../migrations/120_document_templates.sql). When the backend ships the `document_templates` table, the constant becomes an API fetch — the UX stays the same.

### 4. Task detail page — **NEW: Run agent disabled-button, Sources rail, fixed back-links**
- URL: `/tasks/{task-id}` (click any task from a workspace)
- **What's new:**
  - The "Prepare agent run" button (copy-paste shim) is gone. In its place: a disabled **"Run agent"** button with tooltip *"Agent runtime ships in Phase 1 (local helper daemon)."* This is the signal that copy-paste is over and the real runtime is the next step.
  - The "All tasks" back-link now points to `/workspaces/{id}/tasks` when the task has a workspace (was: root `/tasks`, which has been removed).
  - **Documents tab:** if any document has cited context (set via `task_documents.cited_context`), a **Sources rail** now renders alongside the markdown body. Each source shows the path, a 7-char commit SHA (if any), and the relevance note.
  - Today, none of our seeded documents have `cited_context` populated, so the rail won't show yet. When you (or an agent) save a document with citations, it appears automatically. To see it during the demo: open a document, edit the body manually + add `cited_context` via the API.

### 5. Orphaned root pages — **REMOVED**
- URLs that used to work but now return 404:
  - `/tasks` (root list) — superseded by `/workspaces/{id}/tasks`
  - `/projects` (root list) — superseded by `/workspaces/{id}/projects`
  - `/campaigns` (root list) — superseded by per-workspace campaigns
- Detail pages `/tasks/[id]` and `/projects/[id]` still work; they're the canonical destinations from workspace cards.

## What's intentionally still ad-hoc

These are Phase 1 / Phase 2 deliverables, not in this pass:

- **No live agent runtime.** Click "Run agent" → button is disabled. Phase 1 ships the local helper.
- **No @-mention auto-wake.** Comments still parse `@AgentName` into `mentioned_agent_ids` but no agent wakes from it. Phase 1.
- **No document-scoped chat UX.** Migration 119 added the columns; the "Discuss this revision" button on the Documents tab is the Phase 0 part 2 task that needs the API to accept the new params first.
- **Pending decisions** in Home Panels still works against the existing `task_interactions` table — no change.

## Pre-deploy checklist (when you're ready to ship the migrations)

1. Run `py scripts/check_migration_status.py` against production CharmDB to see what's applied vs pending.
2. Read each pending migration file — especially [121_operator_ceo_prompts.sql](../../migrations/121_operator_ceo_prompts.sql), which UPDATEs the 4 seeded agents' prompts (guarded by an original-seed WHERE clause so operator edits are preserved).
3. Deploy charm-api to Coolify. Migrations auto-run on startup inside transactions.
4. Re-run `check_migration_status.py` to confirm everything applied.

## References

- [charm-revamp-plan.md](./charm-revamp-plan.md) — the 3-phase plan this pass executes
- [skill-outputs-contract.md](./skill-outputs-contract.md) — the agent → doc_key → template mapping
- [paperclip-reference.md](./paperclip-reference.md) — what we lifted from paperclip
