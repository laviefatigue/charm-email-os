---
name: Component Library
type: component-index
status: defined
created: 2026-05-15
---

# Component Library

Charm Email OS components — built on shadcn/ui primitives + the Village token system. All components live in `charm-email-os/components/`.

## UI Primitives (`components/ui/`)

Standard shadcn/ui (new-york variant), already installed pre-redesign. **No rewrites needed** — they consume the CSS variables defined in [[../tokens/colors]] so the Village palette inherits automatically. Verified zero raw color leaks on 2026-05-15.

| Component | Doc / Notes |
|-----------|-------------|
| accordion | shadcn default |
| alert / alert-dialog | shadcn default |
| avatar | shadcn default |
| badge | shadcn default |
| button | shadcn default |
| card | shadcn default — supplemented by [[workspace-card]] / [[agent-card]] / [[recommendation-card]] for Charm composites |
| checkbox | shadcn default |
| collapsible | shadcn default |
| dialog | shadcn default |
| dropdown-menu | shadcn default |
| input / textarea / label | shadcn default |
| popover | shadcn default |
| progress | shadcn default — supplemented by [[cost-budget-meter]] for budget-specific use |
| radio-group | shadcn default |
| scroll-area | shadcn default |
| select | shadcn default |
| separator | shadcn default |
| sheet | shadcn default |
| skeleton | shadcn default |
| slider | shadcn default |
| switch | shadcn default |
| table | shadcn default |
| tabs | shadcn default |
| tooltip | shadcn default |

## Charm Composites (`components/charm/`)

The new design-system layer. These are the surfaces unique to Charm's workspace-first control plane.

| Component | Purpose | Doc |
|-----------|---------|-----|
| `StatusPill` | Domain/inbox lifecycle vocab (live, incubating, reserve, dead, burned, kill-pending, eod-scheduled, disconnected, drift, quarantined) | [[status-pill]] |
| `ContextFreshnessPill` | Per-workspace GitHub-context-repo sync freshness indicator | [[context-freshness-pill]] |
| `CostBudgetMeter` | Per-agent monthly LLM cost bar with 80%/100% thresholds | [[cost-budget-meter]] |
| `AgentCard` | Analyst-agent list cell — status, last run, cost, pending recommendations | [[agent-card]] |
| `RecommendationCard` | The hero surface — `request_confirmation` from agent with cited context + approve/reject | [[recommendation-card]] |
| `WorkspaceCard` | Home grid card — internal metrics + integrations + agents + recommendations + freshness | [[workspace-card]] |
| `ActivityLogRow` | One row in the Chronicle — daemon events + agent runs + context syncs interleaved | [[activity-log-row]] |

Import via the barrel:

```tsx
import {
  StatusPill,
  ContextFreshnessPill,
  CostBudgetMeter,
  AgentCard,
  RecommendationCard,
  WorkspaceCard,
  ActivityLogRow,
} from "@/components/charm";
```

## Legacy / Feature Composites (`components/{feature}/`)

Pre-redesign feature folders. These continue to work (they consume the same CSS variables) but will be visually transformed by the Village token swap and progressively replaced as `/design-app` builds new pages:

- `clients/`, `health/`, `inboxes/`, `infrastructure/`, `leads/`, `providers/`, `purchasing/`, `reports/`, `shared/`, `strategy/`, `suppression/`
- `layout/` — sidebar + nav primitives (will be rebuilt to workspace-first nav)
- `providers/StoreProvider` — Zustand store wrapper (kept)

## Foundation Files

| File | Purpose |
|------|---------|
| [`app/globals.css`](../../../charm-email-os/app/globals.css) | Tailwind v4 `@theme` registration + Howl primitives + Charm semantic roles + light/dark mode + Village utilities |
| [`app/layout.tsx`](../../../charm-email-os/app/layout.tsx) | Fraunces + Manrope + Geist Mono loaded via `next/font/google` |

## Validation Status

All 7 Charm composites passed the validation gate on 2026-05-15:

- ✅ Zero raw Tailwind palette colors (`bg-blue-500` etc.)
- ✅ Zero raw hex/rgb values
- ✅ All use `React.forwardRef` + `displayName`
- ✅ All consume design-token CSS variables exclusively
- ✅ All keyboard-accessible (interactive variants have `tabIndex` + `onKeyDown`)
- ✅ All work in light + dark mode (no hardcoded mode-specific values)

## See Also

- [[../tokens/index]] — token system source of truth
- [[../brand-brief]] — workspace-first IA + agent surfaces
- [[../references/ref-paperclip]] — the Village aesthetic source
- [[../../architecture/agent-runtime]] — agent runtime spec these components serve
- [[../../architecture/client-context-sync]] — context sync spec
