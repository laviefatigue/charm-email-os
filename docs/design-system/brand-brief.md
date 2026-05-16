---
project: charm-email-os
type: app
framework: next
created: 2026-05-15
---

# Brand Brief

## Project

**Charm Email OS** — operator-facing tool for managing email infrastructure across multiple client workspaces. Backend handles inbox lifecycle (provisioning, warmup, kill triggers, domain rotation), campaign-sender attachment via the EOD reapply daemon, Hypertide subscription auditing, and event-driven tag synchronization. The frontend is the operator's window into all of this — currently a fragmented set of report pages that doesn't yet reflect the operational/daemon tier the system has grown into.

## Type

**app** — operator dashboard / ops console. Not marketing, not consumer-facing, not e-commerce. Heavy on tables, charts, status surfaces, and per-workspace flag controls.

## Framework

**Next.js 16** (App Router) — already in place at `charm-email-os/`. React 19, Tailwind, shadcn/ui with 20+ Radix-backed components installed. `cva` + `clsx` + `tailwind-merge` + `lucide-react` available.

## Paths

Note: the repo has a nested layout — the Next.js app lives in a `charm-email-os/` subdirectory of the repo root (`d:/Work/Charm/charm-email-os/charm-email-os/`). Repo-root paths below.

- **Components**: `charm-email-os/components/ui/` (shadcn primitives), `charm-email-os/components/` (composed/feature)
- **Styles**: `charm-email-os/app/globals.css`
- **Pages (App Router)**: `charm-email-os/app/`
- **Lib (hooks, stores, API client)**: `charm-email-os/lib/`
- **Public assets**: `charm-email-os/public/`
- **shadcn config**: `charm-email-os/components.json`

## Audience

**Primary:** Charm operators — people running domains/inboxes/campaigns across 10+ active client workspaces. Technical comfort is high but time is short. They need to see "what needs attention now" and act on it fast.

**Secondary (future):** Per-client read-only surfaces (capacity dashboards, deliverability reports). Not in current scope but the design should not block this direction.

## Workspace = Client Control Plane with Analyst Agents (2026-05-15, revised)

Each workspace represents a client and is the **operator's control plane for that client's complete operational footprint**, combining:

1. **Internal infrastructure** — domains, inboxes, campaigns, kills, EOD reapply, hypertide subscriptions (existing Charm surface)
2. **External integrations** — day.ai (CRM/calendar AI), and other per-client tools wired in as the workspace matures
3. **Per-workspace analyst agents with skills** *(new, 2026-05-15)* — LLM-backed agents that read Charm DB + integrations, analyze performance/health/domain metrics, and surface **recommendations** to the operator
4. **Per-client data + resources** — surfaced inside the workspace card and detail page

### The Agent Tier (paperclip pattern, full lift)

Charm adopts paperclip's agent runtime + skills + adapters + auth pattern verbatim, applied to **email-infrastructure analysts** instead of code-gen agents. See [[../architecture/agent-runtime]] for the spec.

**Analyst agents Charm needs** (each is a configured paperclip-pattern agent):

| Agent | Skills | Reads | Recommends |
|-------|--------|-------|------------|
| **Performance Analyst** | burn-velocity-analysis, kill-cascade-forensics, deliverability-trends | `event_log`, `inbox_metrics`, `domain_kill_history` | "Workspace X is approaching kill threshold; rotate domains A, B, C" |
| **Infrastructure Health Monitor** | drift-detection, warmup-audit, hypertide-reconcile | `inbox_state`, `warmup_status`, `hypertide_subscriptions` | "12 inboxes have drift between EB warmup status and our DB; reconcile?" |
| **Domain Insights Advisor** | burn-forecast, rotation-strategy, registrar-optimization | `domain_lifecycle`, `burn_rate_history`, `registrar_spend` | "Workspace Y burn rate trending up 18% MoM; recommend pre-emptive rotation slate" |
| **Account Manager** *(future)* | per-client-synthesis, capacity-planning, integration-orchestration | All of the above + day.ai data | "Client Z is over-capacity on Live domains; pause incubation queue?" |

These coexist with — and are distinct from — Charm's **state-machine daemons** (EOD reapply, Plan F warmup-disable, hypertide audit, tag op worker). Daemons execute policy deterministically; agents reason and propose policy.

### Auth & Runtime (paperclip pattern)

- **Operator auth:** Better Auth (cookie-session) — same as paperclip
- **Agent auth:** short-lived JWT injected as `CHARM_API_KEY` env var per heartbeat
- **LLM provider auth:** encrypted secrets in local master key, decrypted at runtime, injected as `ANTHROPIC_API_KEY`
- **Heartbeat:** scheduled (cron via routines) + on-demand (operator triggers analysis) + on-event (kill chain fires → health monitor wakes)
- **Recommendation surface:** `request_confirmation` interaction (per-issue inline approval card, not a separate approvals queue)

### Implication for the UI

Workspace cards on home now surface:
- Internal metrics (domains live, EOD status, monthly spend)
- External integration status (day.ai connected / drift / disconnected)
- **Active analyst agents** (count + last run + budget utilization)
- **Pending recommendations** (count of `request_confirmation` cards waiting on operator nod)
- **Context freshness** — minutes since last sync from the client's GitHub context repo (see [[../architecture/client-context-sync]])

Workspace detail page sub-nav adds three new sections alongside Domains / Inboxes / Events:
- **Agents** — list of configured analyst agents for this workspace, with per-agent status / last run / cost / config
- **Recommendations** — mailbox of pending `request_confirmation` cards from agents; one-click Approve/Reject with the full analysis + cited context docs inline
- **Context** — view of the client's Foam-markdown repo (notes, feedback, decisions, client card); read-only render with backlink graph; surfaces sync status + freshness

This is the *combining dashboard with real tools* model: don't just show a burn-velocity chart — surface an agent that analyzed the chart (citing recent AE feedback from the client's context repo) and is asking "approve this rotation slate?" with the proposed action inline.

## Mental Model — workspace-first (anchored on paperclip reference)

The operator thinks across multiple unit-of-work axes:

1. **Workspaces** — the org partition + control plane (now includes analyst agents). Every backend operation is workspace-scoped (per ADR-006). **Chosen as primary IA.** See [[references/ref-paperclip]] for the Company→Workspace mapping rationale.
2. **Recommendations** *(new tier)* — pending operator decisions from analyst agents (mailbox-style queue, per-workspace and cross-workspace views).
3. **Operations / daemon events** — the deterministic system: EOD daemon firing, kill triggers cascading, tag ops draining, hypertide audit running. Surfaced *within* a workspace (activity log) and globally.
4. **Pipeline / lifecycle** — incubating → reserve → live → dead/burned. Surfaced *within* workspace detail (Domains panel).
5. **Campaigns** — the customer-facing artifact. Surfaced *within* workspace detail.

**Decision:** Workspace-first nav. Home = card grid of 5 active workspaces (each showing internal + external + agent state); click in to a workspace dashboard with sub-nav for **Recommendations / Agents** / Domains / Inboxes / Events / Integrations / Settings. Cross-workspace top-level surfaces: Home (dashboard), Recommendations (cross-workspace mailbox), Daemons (cross-workspace operations view).

## Tonal Direction — Village reskin for an email-infrastructure control plane

**Full lift** of paperclip's Village aesthetic. See [[references/ref-paperclip]] for the verbatim token system + the three non-negotiables (warm ink everywhere, offset shadow as signature, outline-carries-hierarchy).

**Pivot note (2026-05-15):** Initial framing was "warm-modern, drop the Fraunces serif and offset shadows" because I read the Village as "too whimsical for a control plane." That read was wrong. The Village's density model is *generous between surfaces, dense inside surfaces* — which is exactly what operator UIs need. Tables of inboxes / domains / events can live full-fat inside outlined cards; between cards, air. The "place not tool" framing creates trust, not friction.

### Take (full lift)

- **Palette:** Howl's Moving Castle primitives — amber (Calcifer/hearth), honey, copper, rust, cream, sage, moss, sky, blue-howl, storm, rose, rose-deep, ink (warm-brown), ink-soft. No `#fff`, no `#000`.
- **Typography:** Fraunces (variable serif, chunky, OFL) for headings + Manrope (geometric humanist sans, OFL) for body + Geist Mono (OFL) for code-tone (IDs, timestamps, domain names).
- **Effects:** 1.5px bold ink outline on cards/modals/CTAs (the cartoon-idiom signature). `4px 4px 0 var(--ink)` offset shadow reserved for hero surfaces (workspace cards on home, kill-confirm modals). Generous radii: 6/10/14/20.
- **Spacing:** 4px base. Generous between sections (`--space-12` min), dense inside (tables pack freely).
- **Motion:** Ghibli-pacing — calm, deliberate, never twitchy. No bouncy springs.
- **Focus:** Amber ring, 2px solid, 2px offset (Calcifer's hearth-light highlighting your hand).

### Charm-specific extensions

- **Status vocabulary mapping:** Live=moss / Incubating=sky / Reserve=sage / Dead=ink-soft / Burned=rust / Kill-pending=amber-filled / EOD-scheduled=amber-outlined / Disconnected=storm. Maps cleanly to the Howl palette — no invented tokens.
- **Operational vocabulary:** We use Charm-operator language (Workspaces, Domains, Inboxes, Events, Kills, EOD reapply) — *not* paperclip's narrative names (the square, mailbox, villagers, chronicle). The *aesthetic* is paperclip; the *labels* are operational.

### Anti-references

- Linear (too cool, too sharp, too corporate-grey)
- Vercel dashboard / default shadcn (safe, generic, no personality)
- Notion (too airy, too consumer)
- Stripe dashboard (Swiss-clean but cold)

Position: A Charm-operator Village. Calm warmth, opinionated outline + shadow vocabulary, chunky-serif headings, dense data inside breathing cards. Unmistakably ours.

## Brand Tokens

Not yet defined. Run `/design-brand-consult` with 3-5 reference URLs to extract design language.

## Existing UI to Reference

Before the redesign, the existing app contains:

- **7-page operator queue** (`/reports/cancel-candidates`, `/reports/capacity`, `/reports/disconnects`, `/reports/incubation-stuck`, `/reports/kills`, `/reports/quarantined`, `/reports/rotation`) — shipped, in active use, contracts stable
- **3 newer JSON-only report endpoints** (no UI yet) — `/api/reports/burn-velocity`, `/api/reports/burned-domain-attachments`, `/api/reports/hypertide-drift`
- **In-flight Domain Engine v2 + suppression UI** in untracked files (`components/infrastructure/DomainEngineV2.tsx`, `OperationsTable.tsx`, `PipelineTable.tsx`, `components/suppression/`) — parallel track; decision pending on fold-in vs separate
- **Health views** (`components/health/KillBreakdownChart.tsx`)
- **Infrastructure views** (`components/infrastructure/*`)
- **Layout primitives** (`components/layout/TabNavigation.tsx`, app shell)

The redesign target: **a complete operator UI overhaul reflecting the operational/daemon tier** (EOD reapply, Plan F warmup-disable, hypertide audit, ESP-aware semantics) that the backend grew into during the 2026-05 sprint.

## See Also

- [[design-system/index]]
- [[design-system/tokens/index]]
- [[design-system/references/index]]
- [docs/plans/INBOX-INTEGRITY-PROGRAM.md](../plans/INBOX-INTEGRITY-PROGRAM.md) — master backend tracker; informs what surfaces the UI needs
- [docs/concepts/esp-aware-data-interpretation.md](../concepts/esp-aware-data-interpretation.md) — Google vs MSFT data semantics that affect every rate/ratio display
