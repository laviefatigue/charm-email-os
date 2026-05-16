---
ref: paperclip
type: full-aesthetic-lift
source: D:\Work\paperclip\docs
captured: 2026-05-15
revised: 2026-05-15
status: primary-reference
---

# Reference: Paperclip — Village Aesthetic (Primary Lift)

**Inheritance level: full lift.** We adopt paperclip's complete Village design system (palette, typography, effects, spacing) and swap only the *vocabulary* for Charm's operational domain. The aesthetic is paperclip-Village; the language is Charm-operator.

**Why full lift, not selective:** Initial read framed the Village as "too whimsical for a control plane." That read was wrong — the Village's density model is *generous between pieces, dense inside pieces*, which is exactly what operator UIs need. Tables and event streams can live dense *inside* outlined cards; between cards, air. The "place not tool" framing creates trust, not friction — operators monitoring 5 workspaces benefit from a UI that feels coherent and intentional, not a generic-AI shadcn dashboard.

## The Three Non-Negotiables (the through-line)

These are the moves that prevent the UI from reading as "generic AI design":

1. **Warm ink everywhere, never cold.** `--ink: hsl(28 18% 22%)` (warm-brown) and `--cream-light: hsl(40 40% 94%)` (cream) replace `#000` and `#fff`. There are no pure extremes. The interface always feels like a place with a hearth.

2. **The offset shadow is the signature.** `--shadow-flat: 4px 4px 0 var(--ink)` is the *only* meaningful shadow, reserved for hero surfaces (mailbox/dashboard cards, modals, CTAs). Generic AI design softens everything equally; this picks ~3 things per surface and punches them.

3. **The outline carries hierarchy, not the fill.** Default cards get `--border-bold` (1.5px ink). Primary buttons get the same outline. Inputs get `--border` (1px ink-soft). Filled backgrounds (cream/amber/sage/copper) are secondary to outline vocabulary. This inverts "fill = hierarchy" and is what makes the UI unmistakably non-shadcn-default.

## Color Tokens (verbatim lift) `[scraped]`

All HSL. Source: [D:/Work/paperclip/docs/design-system/tokens/colors.md](D:\Work\paperclip\docs\design-system\tokens\colors.md).

### Primitives (Howl's Moving Castle palette)

| Token | HSL | Source Frame |
|-------|-----|--------------|
| `--amber` | `hsl(34 78% 56%)` | Calcifer's flame, lantern glow |
| `--honey` | `hsl(38 65% 68%)` | Late-afternoon sunlight |
| `--copper` | `hsl(22 55% 48%)` | Brass mechanical parts |
| `--rust` | `hsl(14 55% 42%)` | Oxidised iron |
| `--cream` | `hsl(38 35% 88%)` | Walls, papers |
| `--cream-light` | `hsl(40 40% 94%)` | Backlit highlights — page bg |
| `--sage` | `hsl(85 22% 58%)` | Hillsides, Howl's coat |
| `--moss` | `hsl(95 25% 38%)` | Forest shadow |
| `--sky` | `hsl(205 45% 72%)` | Daytime sky, Markl's eyes |
| `--blue-howl` | `hsl(210 40% 38%)` | Howl's coat-blue |
| `--storm` | `hsl(220 18% 30%)` | Wartime overcast |
| `--rose` | `hsl(345 35% 78%)` | Sophie's ribbon |
| `--rose-deep` | `hsl(355 38% 58%)` | Sunset accent |
| `--ink` | `hsl(28 18% 22%)` | Outlines, body text |
| `--ink-soft` | `hsl(28 14% 36%)` | Secondary text, muted strokes |

### Semantic Roles (Charm-mapped)

| Role | Token | Charm Use |
|------|-------|-----------|
| `--background` | cream-light | Page ground |
| `--foreground` | ink | Body text |
| `--primary` | amber | Primary CTAs (Approve kill, Enable EOD reapply, Add domain) |
| `--secondary` | sage | Supporting earth-anchored accents |
| `--accent` | copper | "Look here" highlights, mechanical motifs (icon backgrounds, hover states) |
| `--border-bold` | ink (1.5px) | Cards, modals, primary buttons — cartoon-idiom outline |
| `--border` | ink-soft (1px) | Inputs, dividers, table grid |
| `--destructive` | rust | Kill confirmed, Burn confirmed, Errors |
| `--success` | moss | "Live" status, "Healthy" |
| `--warning` | honey | "Reserve" status, "Drift detected" cautions |
| `--info` | sky | "Incubating" status, scheduled events, queued |
| `--muted` | cream | Disabled / subtle surfaces |

**Critical:** No `#fff`, no `#000`. Light bg = cream-light. Body text = warm ink.

### Status Vocabulary (Charm-specific extension)

Charm's domain lifecycle maps to paperclip's palette without inventing new tokens:

| Charm Lifecycle State | Token | Visual |
|-----------------------|-------|--------|
| Incubating | `--sky` | Outlined sky pill, ink text |
| Reserve | `--sage` | Outlined sage pill, ink text |
| Live | `--moss` | Filled moss + cream-light text |
| Dead (rest cycle) | `--ink-soft` | Outlined ink-soft pill |
| Burned | `--rust` | Outlined rust pill |
| Kill-pending (operator action required) | `--amber` filled | Hearth-light: needs your nod |
| EOD reapply scheduled | `--amber` outlined | Hearth-light: scheduled |
| Disconnected | `--storm` | Outlined storm pill |

## Typography Tokens (verbatim lift) `[scraped]`

Source: [D:/Work/paperclip/docs/design-system/tokens/typography.md](D:\Work\paperclip\docs\design-system\tokens\typography.md).

| Role | Font | Source |
|------|------|--------|
| Headings (h1–h4, display) | **Fraunces** (variable serif, OFL, Google Fonts) | Chunky, warm, slightly hand-drawn at heavy weights |
| Body, UI labels, table rows | **Manrope** (geometric humanist sans, OFL, Google Fonts) | Friendlier than Inter, dense at body sizes |
| Mono (IDs, timestamps, domain names, EB campaign IDs, event payloads) | **Geist Mono** (OFL, Vercel) | One value lifted from Vercel — code-tone token |

**Fraunces variable axes:** `wght` 600–900, `opsz` 14–144, `SOFT` 50–100, `WONK` 0 on running headings, `WONK` 1 on display only.

**Discipline:** Fraunces for headings *only*. Body emphasis is bold-Manrope, never inline Fraunces. Never more than 2 families.

## Effects Tokens (verbatim lift) `[scraped]`

Source: [D:/Work/paperclip/docs/design-system/tokens/effects.md](D:\Work\paperclip\docs\design-system\tokens\effects.md).

| Token | Value | Charm Use |
|-------|-------|-----------|
| `--radius-sm` | 6px | Status pills, badges, tags |
| `--radius-md` | 10px | Buttons, inputs, dropdowns |
| `--radius-lg` | 14px | Workspace cards, panels, popovers |
| `--radius-xl` | 20px | Modals (kill confirm, firewall override), dialogs |
| `--border-bold` | 1.5px ink | Workspace cards, primary CTAs, modal frames |
| `--border` | 1px ink-soft | Table grid, inputs, dividers |
| `--shadow-flat` | `4px 4px 0 var(--ink)` | Hero surfaces only — workspace cards on home, kill-confirm modals, "pending approvals" panel |
| `--shadow-flat-sm` | `2px 2px 0 var(--ink)` | Hover state on cards, popovers |
| `--shadow-none` | `none` | Everything else (table rows, inputs, secondary surfaces) |

**Critical:** Never `border-radius: 0` on interactive elements. Never gradients. Never pure black or soft drop-shadow. Outline + flat fill carries elevation; offset shadow signals "this matters."

### Motion `[scraped]`

| Token | Duration | Easing | Charm Use |
|-------|----------|--------|-----------|
| `--duration-instant` | 0ms | — | Checkbox / radio state |
| `--duration-fast` | 150ms | ease-out | Button presses, hover |
| `--duration-normal` | 250ms | `cubic-bezier(0.25, 0.46, 0.45, 0.94)` | Modal open, drawer slides |
| `--duration-slow` | 400ms | `cubic-bezier(0.4, 0, 0.2, 1)` | Page transitions, activity-log scrub |

Philosophy: "Studio Ghibli's atmospheric pacing — calm, deliberate, never twitchy." No bouncy springs, no cascading list animations.

### Focus

`var(--ring)` = amber. 2px solid, 2px offset. The amber ring on cream-light reads as Calcifer's hearth-light highlighting your hand — on-narrative for an operator picking a workspace.

## Spacing Tokens (verbatim lift) `[scraped]`

Source: [D:/Work/paperclip/docs/design-system/tokens/spacing.md](D:\Work\paperclip\docs\design-system\tokens\spacing.md).

4px base unit. Tailwind-compatible scale: 1/2/3/4/5/6/8/10/12/16/20/24/32 → 4px/8px/12px/16px/20px/24px/32px/40px/48px/64px/80px/96px/128px.

**Density model — critical for Charm:**
- *Between* surfaces: generous (`--space-12` minimum between sections, `--space-6` card gap)
- *Inside* surfaces: dense (tables can pack inboxes, events, drift rows freely — they live inside outlined cards that provide air)

This is what defeats the "Village is too loose for operators" objection. The Village is generous between pieces, dense within them. That maps perfectly to operator UIs: every workspace card is an island; inside, full-fat data.

### Layout

- Max content width: 1280px
- Sidebar collapsed: 64px
- Sidebar expanded: 240px
- Mobile side padding: 16px
- Tablet: 24px
- Desktop: 32px
- Gutter between columns: 24px

## IA Lift (unchanged from prior capture)

Workspace-first nav, mirroring paperclip's Company-first nav. See prior IA-mapping table — still applies. Sources: [dashboard.md](D:\Work\paperclip\docs\guides\board-operator\dashboard.md), [activity-log.md](D:\Work\paperclip\docs\guides\board-operator\activity-log.md), [approvals.md](D:\Work\paperclip\docs\guides\board-operator\approvals.md), [costs-and-budgets.md](D:\Work\paperclip\docs\guides\board-operator\costs-and-budgets.md), [managing-tasks.md](D:\Work\paperclip\docs\guides\board-operator\managing-tasks.md), [org-structure.md](D:\Work\paperclip\docs\guides\board-operator\org-structure.md).

| Paperclip Surface | Charm Equivalent |
|-------------------|------------------|
| The square (Dashboard) | Home — workspace card grid with internal + external + agent state |
| Mailbox (asks awaiting nod) | **Recommendations** — `request_confirmation` cards from analyst agents (per-workspace + cross-workspace views) |
| Asks (list + detail) | **Agents** — analyst agent list + detail (status, last run, cost, config, skills, run history) |
| Villagers (relationships + village map) | Domains + Inboxes (per-workspace pipeline view) |
| Chronicle (activity log) | Activity Log — daemon `event_log` + `agent_run_log` interleaved |
| Rituals (routines) | Routines — scheduled analyst runs + daemon schedules (EOD reapply, hypertide audit, Plan F) |
| Aims (goals) | Workspace targets (capacity, deliverability, burn-rate ceiling) |
| Workshops / Endeavors | Workspaces (the unit itself) |
| Approvals (formal governance) | **Pending Gates** — daemon-related operator actions (kill confirm, firewall override) — distinct from analyst Recommendations |
| Costs + Budgets | **Two tiers:** Agent LLM cost (per-agent monthly cap) + Infrastructure cost (EB seats + HT calls + registrar) |

### Workspace Detail Sub-Nav (final)

```
Workspace: {client name}
  ├── Overview          (synthesized status, today's chronicle)
  ├── Recommendations   (pending agent confirmations — the active surface)
  ├── Agents            (analyst agents for this workspace)
  ├── Domains           (lifecycle pipeline)
  ├── Inboxes           (per-inbox state, kill triggers)
  ├── Campaigns         (sender attachment, EOD status)
  ├── Events            (activity log — daemons + agent runs)
  ├── Pending Gates     (daemon-related operator actions)
  ├── Routines          (scheduled runs + on-event triggers)
  ├── Integrations      (day.ai, external connections)
  ├── Costs             (agent LLM spend + infra spend)
  └── Settings          (per-workspace flags, agent budgets, daemon toggles)
```

## Concept Mapping (Company → Workspace) — revised 2026-05-15

Earlier framing claimed Charm has "no reasoning agents, only state-machine daemons." **That was wrong.** Charm adopts paperclip's full agent runtime for **analyst agents** (performance, infrastructure health, domain insights, account management) — distinct from but coexisting with our state-machine daemons.

| Paperclip | Charm |
|-----------|-------|
| Company | Workspace (client) |
| Agents | **Two tiers:** (1) **Analyst agents** — LLM-backed via paperclip runtime — Performance, Health Monitor, Domain Insights, Account Manager; (2) **Daemons** (state machines) — Plan F warmup-disable, EOD reapply, hypertide audit, tag op worker |
| Skills (markdown SKILL.md) | Charm analyst skills (`skills/burn-velocity-analysis/SKILL.md`, `skills/drift-detection/SKILL.md`, etc.) — same markdown pattern, injected via adapter at heartbeat time |
| Adapters | Same — `claude_local` primarily, possibly `process` for Python analysts. Authenticate via encrypted Anthropic key in local master-key store |
| Issues / tasks | **Two tiers:** (1) Analyst-agent tasks (analysis runs, generated recommendations); (2) Daemon-fired inbox-lifecycle events + operator-action records |
| Heartbeats | Analyst-agent heartbeats (timer/on-demand/on-event) + daemon event-log entries (deterministic, no LLM) |
| `request_confirmation` interactions | **The recommendation mailbox.** Analyst agent surfaces "Approve this rotation slate?" → operator one-click approve → agent wakes with `CHARM_APPROVAL_STATUS=approved` → executes implementation |
| Approvals (formal governance) | Pending gates for daemons — kill confirm, cross-workspace firewall override, domain add (where operator nod is required by policy) |
| Routines | Scheduled analyst runs (daily performance review, weekly burn-forecast) + on-event triggers (kill cascade fires → health monitor wakes) |
| Per-company budget | **Two tiers:** (1) Per-agent monthly LLM cost budget (Claude token spend, 80% warn / 100% hard-stop); (2) Per-workspace infrastructure budget (EB seats + HT calls + registrar spend) |
| Activity log (immutable, all mutations) | Charm `event_log` (existing) + new `agent_run_log` (paperclip pattern) |
| Better Auth (operator) + JWT (agent) | Same — Better Auth for operator dashboard, short-lived JWT injected as `CHARM_API_KEY` per agent heartbeat |
| Encrypted local secrets (`~/.paperclip/.../master.key`) | Same pattern — `~/.charm/instances/default/secrets/master.key` for Anthropic/OpenAI keys |

### What Actually Doesn't Transfer

- **Org-chart hierarchy** — Charm workspaces are peers with cross-firewall edges, not a CEO → CTO → engineers tree.
- **Hiring flow** — We *provision* analyst agents (operator chooses to enable Performance Analyst for Workspace X); we don't "hire" them through an approval gate.
- **Multi-tenant company model** — Paperclip lets one operator run many companies; Charm has one operator (us) running many workspaces (clients) — but the workspace-as-control-plane model is identical to company-as-control-plane.

### What Charm Adds on Top

- **Daemon tier** — paperclip has no equivalent. Our state-machine workers (EOD reapply, Plan F, hypertide audit, tag op worker) execute deterministic policy. Agents reason; daemons execute. The UI surfaces both — agents in a Recommendations mailbox, daemons in an Activity log + Pending Gates panel.
- **External integration tier** — workspaces wire into client-specific external tools (day.ai, etc.). Agents can read these as additional data sources.
- **ESP-aware data interpretation** — Google vs MSFT data semantics differ structurally; analyst-agent skills must encode the ESP-split logic (see [docs/concepts/esp-aware-data-interpretation.md](../../concepts/esp-aware-data-interpretation.md)).

## What This Means for Charm UI

A *Village reskin for an email-infrastructure control plane*. Same outlined-flat-chunky vocabulary, same Howl's palette, same chunky-serif headings, same offset-shadow signature. The operational language (workspace / domain / inbox / kill / EOD reapply) replaces paperclip's narrative names (company / agent / issue / approval). But the *visual identity* — every token, every constraint — is paperclip's.

## See Also

- [[design-system/brand-brief]]
- [[design-system/references/ref-vercel]] — demoted: now only contributes Geist Mono as the mono font token
- [[design-system/references/index]]
- Paperclip source: [D:/Work/paperclip/docs/](D:\Work\paperclip\docs\)
- Howl's Moving Castle reference (in paperclip): [ref-howls-moving-castle.md](D:\Work\paperclip\docs\design-system\references\ref-howls-moving-castle.md)
