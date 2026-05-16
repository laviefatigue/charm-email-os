---
name: ActivityLogRow
category: charm
status: generated
batch: 5
created: 2026-05-15
---

# ActivityLogRow

Single row in the Activity Log. The Chronicle surface, interleaving three event sources into one chronological stream:

- **Daemon events** (existing `event_log`) — Plan F warmup-disable fires, EOD reapply runs, tag op completes
- **Agent runs** (new `agent_run_log` from [[../architecture/agent-runtime]]) — Performance Analyst woke, completed analysis, posted recommendation
- **Context syncs** (new `workspace_context_syncs` from [[../architecture/client-context-sync]]) — repo pulled, N docs updated, commit SHA delta

## Layout

Compact horizontal row, dense by design (this is the table-inside-a-card surface, where the Village density model gets dense-inside-outlined-frame):

```
[mono timestamp] [type icon] [actor: action — detail]                    [status]
2026-05-15 09:14 ⌘ Daemon    Plan F: warmup_disable fired                ✓ OK
                              47 inboxes affected
```

- Type icon: Workflow (daemon, copper), Bot (agent, amber), GitBranch (context, sky)
- Status icon: CheckCircle (moss), XCircle (rust), Clock (amber, in-progress)
- Hover: `bg-muted/50` if interactive
- Hairline border-bottom between rows (the `--border` 1px hairline, not the bold outline)

## Tokens Used

- Color: [[design-system/tokens/colors]] — `--copper`/`--amber`/`--sky` for event types; `--moss`/`--rust` for status; `--ink-soft` for timestamps
- Typography: [[design-system/tokens/typography]] — mono for timestamps + details, Manrope for actor + action
- Spacing: [[design-system/tokens/spacing]] — `--space-3` vertical (dense table-inside-card), `--space-3` row gap
- Effects: [[design-system/tokens/effects]] — `--border` (1px hairline), no shadow

## Usage

```tsx
import { ActivityLogRow } from "@/components/charm";

<ul className="rounded-lg border-[1.5px] border-border-bold bg-card overflow-hidden">
  {events.map((event) => (
    <ActivityLogRow
      key={event.id}
      event={event}
      onOpen={(id) => openEventDetail(id)}
    />
  ))}
</ul>
```

## Guidelines

- DO wrap rows in a bold-outlined card so the list reads as one unit (between cards = air, inside card = dense)
- DO display relative time by default (`47m ago`); use `absoluteTime` for export/audit views
- DO color-code by event type so daemon/agent/context streams are scannable
- DON'T paginate at < 50 rows — use virtualization for very long lists
- DON'T animate row-by-row (per Ghibli motion: never twitchy)

## See Also

- [[design-system/components/index]] | [[design-system/tokens/typography]]
- [[../architecture/agent-runtime]] §Activity Log
- [[../architecture/client-context-sync]] §Sync Worker
