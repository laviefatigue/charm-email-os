---
name: StatusPill
category: charm
status: generated
batch: 5
created: 2026-05-15
---

# StatusPill

Charm lifecycle status pill. The vocabulary surface for domain / inbox / workspace states.

## Purpose

Renders a single state pill with the Howl palette mapping defined in [[design-system/tokens/colors]] §Charm Status Vocabulary. Outlined by default; filled for "action required" states (kill-pending, quarantined) and the steady-state "Live" winner.

## Variants

| Kind | Color | Style | Meaning |
|------|-------|-------|---------|
| `live` | moss | Filled | Domain/inbox is in the active rotation |
| `incubating` | sky | Outlined | New, warming up, not yet in rotation |
| `reserve` | sage | Outlined | Warmed, parked, ready to promote |
| `dead` | ink-soft | Outlined | Retired naturally (rest cycle) |
| `burned` | rust | Outlined | Reputation gone, will not return |
| `kill-pending` | amber | **Filled** | Operator action required (kill confirm) |
| `eod-scheduled` | amber | Outlined | EOD reapply queued |
| `disconnected` | storm | Outlined | Connection lost (operator reconnect) |
| `drift` | honey | Outlined | EB ↔ DB / HT ↔ DB drift detected |
| `quarantined` | rust | **Filled** | Compliance/admin hold |

Sizes: `sm` (h-5), `md` (h-6, default), `lg` (h-7).

## Tokens Used

- Color: [[design-system/tokens/colors]] — `--moss`, `--sky`, `--sage`, `--ink-soft`, `--rust`, `--amber`, `--storm`, `--honey`, `--cream-light`, `--ink`
- Effects: [[design-system/tokens/effects]] — `--radius-sm` (6px), 1.5px outline

## Usage

```tsx
import { StatusPill } from "@/components/charm";

<StatusPill kind="live" />
<StatusPill kind="kill-pending" size="lg" />
<StatusPill kind="eod-scheduled" showDot={false} label="EOD · 02:00 UTC" />
```

## Guidelines

- DO use this for every lifecycle-state surface so the vocabulary stays consistent
- DO override `label` when you need to embed a sub-detail ("EOD · 02:00")
- DON'T invent new status colors — extend the union if a new state appears, then map it here
- DON'T use filled style for non-action-required states (dilutes the kill-pending signal)

## See Also

- [[design-system/components/index]] | [[design-system/tokens/colors]]
- [[design-system/components/workspace-card]] (consumes this)
- [[design-system/components/activity-log-row]] (consumes this)
