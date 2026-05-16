---
name: WorkspaceCard
category: charm
status: generated
batch: 5
created: 2026-05-15
---

# WorkspaceCard

Home grid card. The control-plane summary for one client workspace.

## Purpose

Top-level surface on the operator dashboard. Each of the ~5 active client workspaces gets one card. Surfaces, at a glance:

- **Internal infra:** live/total domains, EOD reapply status, monthly spend
- **External integrations:** day.ai (and others as wired) — connected / drift / disconnected
- **Analyst agents:** active count
- **Pending recommendations:** count badge (the "go fix this" signal)
- **Context freshness:** [[design-system/components/context-freshness-pill]] in the footer
- **Attention state:** healthy / amber / red — drives the offset shadow

## Shadow Strategy

This card follows the decided shadow rule (per `/design-brand-consult` Phase 4 Q3):

- `attentionState === "healthy"` → outlined-flat, no shadow
- `attentionState !== "healthy"` → `--shadow-flat` (4px 4px 0 ink) — the offset shadow signals "this one matters"

Hover on any card adds `--shadow-flat` (or upgrades existing shadow), signaling "pickable."

## Tokens Used

- Color: [[design-system/tokens/colors]] — `--moss`/`--honey`/`--rust` for attention state; `--amber` for pending; integration pills use `--moss`/`--honey`/`--storm`
- Typography: [[design-system/tokens/typography]] — Fraunces h3 for workspace name, mono for slug + dollar amounts
- Spacing: [[design-system/tokens/spacing]] — `--space-6` card padding, `--space-5` between rows
- Effects: [[design-system/tokens/effects]] — `--radius-lg` (14px), `--border-bold` (1.5px ink), conditional `--shadow-flat`

## Usage

```tsx
import { WorkspaceCard } from "@/components/charm";

<WorkspaceCard
  workspace={{
    id: "ws-hypertide",
    name: "Hypertide",
    slug: "ws-hypertide",
    domainsLive: 87, domainsTotal: 142,
    lastEventAt: new Date(),
    lastEventType: "warmup_disable fired",
    eodReapplyEnabled: true,
    monthlySpendCents: 4700,
    agentsActive: 3,
    pendingRecommendations: 2,
    contextSync: { status: "ok", lastSyncedAt: new Date(Date.now() - 47 * 60 * 1000) },
    integrations: [
      { name: "day.ai", status: "connected" },
      { name: "EmailBison", status: "connected" },
      { name: "Hypertide", status: "drift" },
    ],
    attentionState: "amber",
  }}
  onOpen={(id) => router.push(`/workspaces/${id}`)}
/>
```

## Guidelines

- DO arrange cards in a responsive grid (`grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6`) on the home page
- DO drive `attentionState` from the back-end synthesis (pending recommendations + drift + over-budget + auth-failed context = amber/red)
- DO keep integrations as compact pills — don't expand them inline; deep-link into Integrations sub-page on click
- DON'T render more than ~10 cards in this view — beyond that, use a table view
- DON'T omit the freshness pill — operator trust depends on knowing context staleness

## See Also

- [[design-system/components/index]] | [[design-system/components/context-freshness-pill]]
- [[design-system/brand-brief]] §Workspace = Client Control Plane
- [[../architecture/agent-runtime]] · [[../architecture/client-context-sync]]
