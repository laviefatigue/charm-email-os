/**
 * Screen: Timeline — cross-workspace Gantt of all in-flight tasks.
 * The "long-term roadmap" view.
 */
"use client";

import * as React from "react";
import { addDays, startOfDay } from "date-fns";
import { taskApi, projectApi } from "@/lib/api";
import { PageHeader, GanttStrip, type GanttItem } from "@/components/charm";
import type { Project, Task } from "@/lib/types";
import { cn } from "@/lib/utils";

const STATUS_COLOR: Record<Task["status"], GanttItem["tone"]> = {
  backlog: "sage",
  todo: "sky",
  in_progress: "amber",
  in_review: "honey",
  done: "moss",
  blocked: "rust",
};

type GroupBy = "project" | "assignee" | "workspace";

export default function TimelinePage() {
  const [tasks, setTasks] = React.useState<Task[]>([]);
  const [projects, setProjects] = React.useState<Project[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);
  const [groupBy, setGroupBy] = React.useState<GroupBy>("project");
  const [daysVisible, setDaysVisible] = React.useState(21);

  React.useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      try {
        const [ts, ps] = await Promise.all([
          taskApi.list({ includeClosed: false, pageSize: 200 }),
          projectApi.list({ includeClosed: false }),
        ]);
        if (cancelled) return;
        setTasks(ts.items);
        setProjects(ps.items);
      } catch (err) {
        console.error(err);
        if (!cancelled) setError("Failed to load timeline");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const projectName = React.useMemo(() => {
    const map = new Map(projects.map((p) => [p.id, p.name]));
    return (id?: string | null) => (id ? map.get(id) ?? "Unknown project" : "Orphan tasks");
  }, [projects]);

  const ganttItems: GanttItem[] = React.useMemo(() => {
    return tasks
      .filter((t) => t.startAt || t.dueAt)
      .map((t) => {
        const start = t.startAt
          ? new Date(t.startAt)
          : t.dueAt
            ? new Date(t.dueAt)
            : new Date();
        let end: Date;
        if (t.dueAt) end = new Date(t.dueAt);
        else if (t.estimatedHours) end = addDays(start, Math.ceil(t.estimatedHours / 8));
        else end = addDays(start, 1);
        let lane = "—";
        if (groupBy === "project") lane = projectName(t.projectId);
        else if (groupBy === "assignee") lane = t.assigneeAgentName ?? "Unassigned";
        else if (groupBy === "workspace") lane = t.workspaceName ?? "Cross-workspace";
        return {
          id: t.id,
          label: t.title,
          start,
          end,
          href: `/tasks/${t.id}`,
          lane,
          tone: STATUS_COLOR[t.status],
          subtitle:
            groupBy === "project"
              ? t.assigneeAgentName ?? undefined
              : t.projectName ?? undefined,
          percentDone: t.status === "done" ? 100 : t.status === "in_review" ? 80 : t.status === "in_progress" ? 40 : 0,
        };
      });
  }, [tasks, groupBy, projectName]);

  const ganttStart = startOfDay(addDays(new Date(), -2));

  const groupOptions: { id: GroupBy; label: string }[] = [
    { id: "project", label: "By project" },
    { id: "assignee", label: "By assignee" },
    { id: "workspace", label: "By workspace" },
  ];

  return (
    <div className="px-8 py-8 max-w-[1600px] w-full mx-auto">
      <PageHeader
        kicker="Long-term roadmap"
        title="Timeline"
        subtitle={
          loading
            ? "Loading…"
            : `${ganttItems.length} scheduled task${ganttItems.length === 1 ? "" : "s"} across all in-flight projects.`
        }
      />

      {error && (
        <div className="mb-4 p-3 rounded-md border-[1.5px] border-rust bg-rust/10 text-rust text-sm">
          {error}
        </div>
      )}

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-2 mb-5">
        <span className="text-xs uppercase tracking-wider text-ink-soft mr-2">Group</span>
        {groupOptions.map((g) => (
          <button
            key={g.id}
            type="button"
            onClick={() => setGroupBy(g.id)}
            className={cn(
              "inline-flex items-center h-7 px-3 rounded-sm text-xs font-medium border-[1.5px] transition-colors",
              groupBy === g.id
                ? "bg-amber text-ink border-ink"
                : "bg-transparent text-ink-soft border-border hover:border-border-bold hover:text-foreground"
            )}
          >
            {g.label}
          </button>
        ))}

        <span className="text-xs uppercase tracking-wider text-ink-soft mx-2">Window</span>
        {[14, 21, 30, 60].map((n) => (
          <button
            key={n}
            type="button"
            onClick={() => setDaysVisible(n)}
            className={cn(
              "inline-flex items-center h-7 px-3 rounded-sm text-xs font-mono font-medium border-[1.5px] transition-colors",
              daysVisible === n
                ? "bg-amber text-ink border-ink"
                : "bg-transparent text-ink-soft border-border hover:border-border-bold hover:text-foreground"
            )}
          >
            {n}d
          </button>
        ))}
      </div>

      <GanttStrip
        items={ganttItems}
        startDate={ganttStart}
        daysVisible={daysVisible}
        emptyMessage="No scheduled tasks. Add start_at + due_at (or estimated_hours) to tasks to see them here."
      />
    </div>
  );
}
