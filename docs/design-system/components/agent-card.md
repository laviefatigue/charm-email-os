---
name: AgentCard
category: charm
status: generated
batch: 5
created: 2026-05-15
---

# AgentCard

Per-workspace analyst-agent card. The unit cell of the "Agents" sub-page inside a workspace.

## Purpose

Represents one row in the `agents` table (see [[../architecture/agent-runtime]] §Data Model). Surfaces status, last-run timing, adapter type, monthly cost utilization, and pending recommendations awaiting operator nod.

## Layout

- Bold-outlined card (`--border-bold`, 1.5px ink) — outline-carries-hierarchy
- Copper icon tile (agent identity), Fraunces h4 name, body description
- Status row: dot-icon + "Last run 2h ago" + mono adapter type
- Embedded [[design-system/components/cost-budget-meter]] (sm size)
- Pending recommendations footer (only when count > 0) — amber badge + inline summary
- Hover: `--shadow-flat-sm` for the "this is a card you can pick up" feel (no shadow at rest — composed inside a workspace detail page that already has structure)

## Agent Status Tones

| Status | Color | Icon |
|--------|-------|------|
| `active` | moss | Activity |
| `running` | amber | Activity |
| `idle` | ink-soft | CircleDashed |
| `paused` | ink-soft | Pause |
| `error` | rust | AlertCircle |
| `terminated` | ink-soft | Pause |

## Tokens Used

- Color: [[design-system/tokens/colors]] — `--moss`, `--amber`, `--rust`, `--copper`, `--ink`, `--ink-soft`, `--cream-light`
- Typography: [[design-system/tokens/typography]] — Fraunces for name (h4), Manrope for body, mono for adapter type
- Spacing: [[design-system/tokens/spacing]] — `--space-5` internal padding, `--space-4` row gap
- Effects: [[design-system/tokens/effects]] — `--border-bold`, `--shadow-flat-sm` on hover

## Usage

```tsx
import { AgentCard } from "@/components/charm";

<AgentCard
  agent={{
    id: "perf-analyst-hypertide",
    name: "Performance Analyst",
    description: "Burn velocity + kill-cascade forensics",
    status: "active",
    adapterType: "claude_local",
    lastRunAt: new Date(Date.now() - 2 * 3600 * 1000),
    spentMonthlyCents: 1240,
    budgetMonthlyCents: 5000,
    pendingRecommendations: 2,
  }}
  onOpen={(id) => router.push(`/workspaces/.../agents/${id}`)}
/>
```

## Guidelines

- DO compose multiple AgentCards in a vertical or grid layout for the Agents sub-page
- DO leave `onOpen` undefined for read-only contexts (e.g., aggregated home dashboard)
- DON'T put the offset shadow on by default — agent cards live inside other surfaces (workspace detail) that already provide structure; offset shadow is reserved for hero contexts
- DON'T show the pending-recommendations footer when count is 0 — keeps the visual quiet

## See Also

- [[design-system/components/index]] | [[design-system/components/recommendation-card]]
- [[design-system/components/cost-budget-meter]] (embedded)
- [[../architecture/agent-runtime]] §The Analyst Agents
