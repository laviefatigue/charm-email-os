---
name: ContextFreshnessPill
category: charm
status: generated
batch: 5
created: 2026-05-15
---

# ContextFreshnessPill

Reflects the state of a workspace's GitHub-context-repo sync. Visible on workspace cards (home grid) and the workspace detail page header so the operator always knows how stale their context is.

## Purpose

Maps `workspace_context_repos.sync_status` + `last_synced_at` (see [[../architecture/client-context-sync]] §Data Model) to a single inline pill. Computes tone from age:

| State | Computed Tone | Threshold |
|-------|---------------|-----------|
| `ok` + ≤ 60 min since sync | Fresh (moss outline) | "Fresh · 47m" |
| `ok` + 60–360 min | Stale (honey outline) | "Stale · 3h 12m" |
| `ok` + > 360 min | Drift (rust outline) | "Stale · 9h" |
| `syncing` | Amber pulse | "Syncing…" |
| `drift_detected` | Drift (rust outline) | "Drift detected" |
| `failed` | Drift (rust outline) | "Sync failed" |
| `auth_failed` | **Filled rust** | "Auth failed" — operator must rotate token |
| `never_synced` | Muted (ink-soft outline) | "Never synced" |

## Tokens Used

- Color: [[design-system/tokens/colors]] — `--moss`, `--honey`, `--rust`, `--amber`, `--ink-soft`, `--cream-light`
- Effects: [[design-system/tokens/effects]] — `--radius-sm` (6px), 1.5px outline

## Usage

```tsx
import { ContextFreshnessPill } from "@/components/charm";

<ContextFreshnessPill status="ok" lastSyncedAt={workspace.contextSync.lastSyncedAt} />
<ContextFreshnessPill status="auth_failed" />
```

## Guidelines

- DO display this on every workspace surface — the operator needs to know freshness *before* trusting a recommendation
- DO surface auth-failed prominently (filled rust signals "fix me now")
- DON'T compute freshness manually elsewhere — this component owns the thresholds and labels

## See Also

- [[design-system/components/index]] | [[design-system/tokens/colors]]
- [[../architecture/client-context-sync]] — sync architecture
- [[design-system/components/workspace-card]] (consumes this)
