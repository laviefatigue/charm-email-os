/**
 * Screen: Workspace Events (Chronicle)
 * Chronological stream interleaving daemon events + agent runs + context syncs.
 *
 * Design System: [[design-system/index]]
 * Components: [[design-system/components/activity-log-row]]
 */
"use client";

import * as React from "react";
import { notFound, useParams } from "next/navigation";
import { ScrollText } from "lucide-react";
import { ActivityLogRow, PageHeader } from "@/components/charm";
import { getWorkspace, getEvents } from "@/lib/mock/charm";
import { cn } from "@/lib/utils";
import type { ActivityEvent, ActivityEventType } from "@/components/charm";

type Filter = "all" | ActivityEventType;

const FILTERS: { id: Filter; label: string }[] = [
  { id: "all", label: "All" },
  { id: "daemon-event", label: "Daemons" },
  { id: "agent-run", label: "Agents" },
  { id: "context-sync", label: "Context syncs" },
];

export default function WorkspaceEventsPage() {
  const { id } = useParams<{ id: string }>();
  const workspace = getWorkspace(id);
  if (!workspace) notFound();

  const [filter, setFilter] = React.useState<Filter>("all");
  const allEvents = React.useMemo(() => getEvents(id), [id]);

  const filteredEvents: ActivityEvent[] = React.useMemo(
    () =>
      filter === "all"
        ? allEvents
        : allEvents.filter((e) => e.type === filter),
    [allEvents, filter]
  );

  const countsByType = React.useMemo(() => {
    const c: Record<string, number> = { all: allEvents.length };
    for (const e of allEvents) {
      c[e.type] = (c[e.type] ?? 0) + 1;
    }
    return c;
  }, [allEvents]);

  return (
    <div>
      <PageHeader
        kicker="Chronicle"
        title="Events"
        subtitle={`${allEvents.length} event${allEvents.length === 1 ? "" : "s"} in the last 24h, interleaved across daemons, agents, and context syncs.`}
      />

      {/* Filter chips */}
      <div className="flex flex-wrap items-center gap-2 mb-5">
        {FILTERS.map((f) => {
          const count = countsByType[f.id] ?? 0;
          const active = filter === f.id;
          return (
            <button
              key={f.id}
              type="button"
              onClick={() => setFilter(f.id)}
              className={cn(
                "inline-flex items-center gap-2 h-7 px-3 rounded-sm text-xs font-medium border-[1.5px] transition-colors",
                active
                  ? "bg-amber text-ink border-ink"
                  : "bg-transparent text-ink-soft border-border hover:border-border-bold hover:text-foreground"
              )}
            >
              {f.label}
              <span className="font-mono">{count}</span>
            </button>
          );
        })}
      </div>

      {/* Event list */}
      {filteredEvents.length === 0 ? (
        <div className="flex flex-col items-center justify-center text-center gap-3 py-16 px-6 rounded-xl border border-dashed border-border bg-muted/30">
          <span className="inline-flex items-center justify-center h-12 w-12 rounded-md bg-sky/15 text-sky border-[1.5px] border-sky">
            <ScrollText className="h-6 w-6" aria-hidden="true" />
          </span>
          <h3 className="text-xl">No events match this filter</h3>
          <p className="text-sm text-ink-soft max-w-md">
            Try a different filter or check back later.
          </p>
        </div>
      ) : (
        <ul className="rounded-lg border-[1.5px] border-border-bold bg-card overflow-hidden">
          {filteredEvents.map((event) => (
            <ActivityLogRow
              key={event.id}
              event={event}
              onOpen={(id) => console.warn("open event detail", id)}
            />
          ))}
        </ul>
      )}
    </div>
  );
}
