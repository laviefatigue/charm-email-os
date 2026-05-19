/**
 * Screen: Project detail
 * Header + progress + mini Gantt + project tasks list.
 */
"use client";

import * as React from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { ChevronLeft, Plus, CalendarClock, AlertTriangle } from "lucide-react";
import { addDays, format, startOfDay } from "date-fns";
import { projectApi, taskApi } from "@/lib/api";
import {
  PageHeader,
  GanttStrip,
  type GanttItem,
  TaskCard,
  NewTaskModal,
} from "@/components/charm";
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

export default function ProjectDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [project, setProject] = React.useState<Project | null>(null);
  const [tasks, setTasks] = React.useState<Task[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);
  const [newTaskOpen, setNewTaskOpen] = React.useState(false);

  const refetch = React.useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [p, ts] = await Promise.all([
        projectApi.get(id),
        taskApi.list({ projectId: id, includeClosed: true, pageSize: 100 }),
      ]);
      setProject(p);
      setTasks(ts.items);
    } catch (err) {
      console.error(err);
      setError("Failed to load project");
    } finally {
      setLoading(false);
    }
  }, [id]);

  React.useEffect(() => {
    refetch();
  }, [refetch]);

  // Gantt items from tasks with scheduled dates
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
        return {
          id: t.id,
          label: t.title,
          start,
          end,
          href: `/tasks/${t.id}`,
          lane: t.assigneeAgentName ?? "Unassigned",
          tone: STATUS_COLOR[t.status],
          subtitle: t.assigneeAgentName ?? undefined,
          percentDone: t.status === "done" ? 100 : t.status === "in_review" ? 80 : t.status === "in_progress" ? 40 : 0,
        };
      });
  }, [tasks]);

  // Gantt window: start from project start_at (or earliest task) and span to end
  const ganttStart = React.useMemo(() => {
    if (project?.startAt) return startOfDay(new Date(project.startAt));
    if (project?.progress.earliestTaskStart)
      return startOfDay(new Date(project.progress.earliestTaskStart));
    return startOfDay(new Date());
  }, [project]);

  if (loading && !project) {
    return (
      <div className="px-8 py-8 max-w-6xl mx-auto text-sm text-ink-soft">Loading project…</div>
    );
  }
  if (error || !project) {
    return (
      <div className="px-8 py-8 max-w-6xl mx-auto">
        <p className="text-rust">{error ?? "Project not found"}</p>
        <Link href="/" className="text-copper hover:underline text-sm mt-2 inline-block">
          ← Back to home
        </Link>
      </div>
    );
  }

  const tasksByStatus = (() => {
    const groups: Record<string, Task[]> = {};
    for (const t of tasks) {
      const k = t.status;
      if (!groups[k]) groups[k] = [];
      groups[k].push(t);
    }
    return groups;
  })();

  const backHref = project.workspaceId ? `/workspaces/${project.workspaceId}/projects` : "/";
  const backLabel = project.workspaceId ? "Workspace projects" : "Home";

  return (
    <div className="px-8 py-8 max-w-7xl w-full mx-auto">
      <Link
        href={backHref}
        className="inline-flex items-center gap-1 text-xs text-ink-soft hover:text-foreground mb-3 transition-colors"
      >
        <ChevronLeft className="h-3 w-3" aria-hidden="true" />
        {backLabel}
      </Link>

      <PageHeader
        kicker={project.workspaceName ? `Workspace · ${project.workspaceName}` : "Cross-workspace project"}
        title={project.name}
        subtitle={project.description ?? undefined}
        actions={
          <div className="flex items-center gap-2">
            <span className="inline-flex items-center gap-1.5 text-sm">
              <span className="inline-flex items-center gap-1 px-2 h-6 rounded-sm border-[1.5px] border-border bg-muted text-foreground text-xs font-medium capitalize">
                {project.status}
              </span>
            </span>
            <button
              type="button"
              onClick={() => setNewTaskOpen(true)}
              className="inline-flex items-center gap-1.5 h-9 px-4 rounded-md text-sm font-medium bg-amber text-ink border-[1.5px] border-border-bold hover:shadow-flat-sm transition-shadow"
            >
              <Plus className="h-4 w-4" aria-hidden="true" />
              Add task
            </button>
          </div>
        }
      />

      {/* Stat strip */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mb-8">
        <Stat label="Tasks" value={`${project.progress.doneTasks} / ${project.progress.totalTasks}`} />
        <Stat
          label="Progress"
          value={`${project.progress.percentDone}%`}
          tone={project.progress.percentDone >= 75 ? "moss" : project.progress.percentDone >= 25 ? "honey" : "ink-soft"}
        />
        <Stat
          label="In progress"
          value={String(project.progress.inProgressTasks)}
          tone="amber"
        />
        <Stat
          label="Blocked"
          value={String(project.progress.blockedTasks)}
          tone={project.progress.blockedTasks > 0 ? "rust" : "ink-soft"}
        />
        <Stat
          label="Overdue"
          value={String(project.progress.overdueTasks)}
          tone={project.progress.overdueTasks > 0 ? "rust" : "ink-soft"}
        />
      </div>

      {/* Date range */}
      {(project.startAt || project.targetEndAt) && (
        <div className="flex items-center gap-3 text-sm text-ink-soft mb-6">
          <CalendarClock className="h-4 w-4" aria-hidden="true" />
          <span>
            {project.startAt && format(new Date(project.startAt), "MMM d, yyyy")}
            {project.startAt && project.targetEndAt && " → "}
            {project.targetEndAt && format(new Date(project.targetEndAt), "MMM d, yyyy")}
          </span>
        </div>
      )}

      {/* Mini Gantt */}
      <section className="mb-10" aria-labelledby="project-gantt">
        <h2 id="project-gantt" className="text-base font-medium uppercase tracking-wider text-ink-soft mb-3">
          Timeline
        </h2>
        <GanttStrip
          items={ganttItems}
          startDate={ganttStart}
          daysVisible={21}
          compact={false}
          emptyMessage="No tasks have scheduled dates yet. Edit a task to set start_at or due_at."
        />
      </section>

      {/* Task lanes */}
      <section aria-labelledby="project-tasks">
        <h2 id="project-tasks" className="text-base font-medium uppercase tracking-wider text-ink-soft mb-3">
          Tasks · {tasks.length}
        </h2>
        {tasks.length === 0 ? (
          <div className="flex flex-col items-center justify-center text-center gap-3 py-12 px-6 rounded-xl border border-dashed border-border bg-muted/30">
            <p className="text-sm text-ink-soft">No tasks in this project yet</p>
            <button
              type="button"
              onClick={() => setNewTaskOpen(true)}
              className="inline-flex items-center gap-1.5 h-9 px-4 rounded-md text-sm font-medium bg-amber text-ink border-[1.5px] border-border-bold hover:shadow-flat-sm transition-shadow"
            >
              <Plus className="h-4 w-4" aria-hidden="true" />
              Add the first task
            </button>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {(["in_progress", "in_review", "todo", "blocked", "backlog", "done"] as Task["status"][]).flatMap(
              (st) => tasksByStatus[st] ?? []
            ).map((task) => (
              <TaskCard key={task.id} task={task} href={`/tasks/${task.id}`} />
            ))}
          </div>
        )}
      </section>

      <NewTaskModal
        open={newTaskOpen}
        onOpenChange={setNewTaskOpen}
        defaultWorkspaceId={project.workspaceId ?? undefined}
        onCreated={() => refetch()}
      />
    </div>
  );
}

function Stat({
  label,
  value,
  tone = "ink",
}: {
  label: string;
  value: string;
  tone?: "ink" | "ink-soft" | "moss" | "amber" | "rust" | "honey";
}) {
  const toneClass = {
    ink: "text-foreground",
    "ink-soft": "text-ink-soft",
    moss: "text-moss",
    amber: "text-amber",
    rust: "text-rust",
    honey: "text-honey",
  }[tone];
  return (
    <div className="rounded-lg border-[1.5px] border-border-bold bg-card p-3">
      <p className="text-xs uppercase tracking-wider text-ink-soft">{label}</p>
      <p className={cn("text-2xl font-mono mt-0.5", toneClass)}>{value}</p>
    </div>
  );
}
