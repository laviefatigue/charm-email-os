/**
 * Screen: Workspace Tasks
 * Tasks scoped to THIS workspace. Kanban view. NewTaskModal pre-filled with workspaceId.
 * Top-level /tasks remains the cross-workspace roll-up.
 */
"use client";

import * as React from "react";
import { useParams } from "next/navigation";
import { Plus, ScrollText } from "lucide-react";
import { taskApi } from "@/lib/api";
import { PageHeader, TaskCard, NewTaskModal } from "@/components/charm";
import type { Task, TaskStatus } from "@/lib/types";
import { cn } from "@/lib/utils";

type Lane = { status: TaskStatus; label: string };
const LANES: Lane[] = [
  { status: "backlog", label: "Backlog" },
  { status: "todo", label: "Todo" },
  { status: "in_progress", label: "In progress" },
  { status: "in_review", label: "In review" },
  { status: "done", label: "Done" },
];

export default function WorkspaceTasksPage() {
  const { id } = useParams<{ id: string }>();
  const [tasks, setTasks] = React.useState<Task[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);
  const [modalOpen, setModalOpen] = React.useState(false);

  const refetch = React.useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await taskApi.list({
        workspaceId: id,
        includeClosed: true,
        pageSize: 200,
      });
      setTasks(res.items);
    } catch (err) {
      console.error(err);
      setError("Failed to load tasks");
    } finally {
      setLoading(false);
    }
  }, [id]);

  React.useEffect(() => {
    refetch();
  }, [refetch]);

  const byStatus = React.useMemo(() => {
    const groups: Record<TaskStatus, Task[]> = {
      backlog: [],
      todo: [],
      in_progress: [],
      in_review: [],
      done: [],
      blocked: [],
    };
    for (const t of tasks) groups[t.status].push(t);
    return groups;
  }, [tasks]);

  const activeCount = tasks.filter(
    (t) => t.status !== "done" && t.status !== "blocked"
  ).length;

  return (
    <div>
      <PageHeader
        kicker="Workspace tasks"
        title="Tasks"
        subtitle={
          tasks.length === 0
            ? "No tasks in this workspace yet."
            : `${tasks.length} task${tasks.length === 1 ? "" : "s"} · ${activeCount} active`
        }
        actions={
          <button
            type="button"
            onClick={() => setModalOpen(true)}
            className="inline-flex items-center gap-1.5 h-9 px-4 rounded-md text-sm font-medium bg-amber text-ink border-[1.5px] border-border-bold hover:shadow-flat-sm transition-shadow"
          >
            <Plus className="h-4 w-4" aria-hidden="true" />
            New task
          </button>
        }
      />

      {error && (
        <div className="mb-4 p-3 rounded-md border-[1.5px] border-rust bg-rust/10 text-rust text-sm">
          {error}
        </div>
      )}

      {loading && tasks.length === 0 ? (
        <div className="text-sm text-ink-soft py-12 text-center">Loading tasks…</div>
      ) : tasks.length === 0 ? (
        <EmptyState onCreate={() => setModalOpen(true)} />
      ) : (
        <>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-3 mb-6">
            {LANES.map((lane) => (
              <Lane
                key={lane.status}
                lane={lane}
                tasks={byStatus[lane.status]}
              />
            ))}
          </div>

          {byStatus.blocked.length > 0 && (
            <div className="rounded-lg border-[1.5px] border-rust bg-rust/5 p-4">
              <h3 className="text-base font-medium text-rust mb-3 inline-flex items-center gap-2">
                <span className="h-2 w-2 rounded-full bg-rust" aria-hidden="true" />
                Blocked · {byStatus.blocked.length}
              </h3>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                {byStatus.blocked.map((task) => (
                  <TaskCard key={task.id} task={task} href={`/tasks/${task.id}`} />
                ))}
              </div>
            </div>
          )}
        </>
      )}

      <NewTaskModal
        open={modalOpen}
        onOpenChange={setModalOpen}
        defaultWorkspaceId={id}
        onCreated={() => refetch()}
      />
    </div>
  );
}

function Lane({ lane, tasks }: { lane: Lane; tasks: Task[] }) {
  return (
    <section
      aria-label={`${lane.label} (${tasks.length})`}
      className={cn(
        "flex flex-col gap-2.5 rounded-lg border-[1.5px] border-border bg-muted/30 p-3 min-h-[200px]"
      )}
    >
      <header className="flex items-center justify-between px-1 mb-1">
        <h3 className="text-xs font-medium uppercase tracking-wider text-ink-soft">
          {lane.label}
        </h3>
        <span className="text-xs font-mono text-ink-soft">{tasks.length}</span>
      </header>
      {tasks.length === 0 ? (
        <div className="text-xs text-ink-soft/60 italic px-1 py-3">No tasks</div>
      ) : (
        <div className="flex flex-col gap-2.5">
          {tasks.map((task) => (
            <TaskCard key={task.id} task={task} href={`/tasks/${task.id}`} />
          ))}
        </div>
      )}
    </section>
  );
}

function EmptyState({ onCreate }: { onCreate: () => void }) {
  return (
    <div className="flex flex-col items-center justify-center text-center gap-3 py-16 px-6 rounded-xl border border-dashed border-border bg-muted/30">
      <span className="inline-flex items-center justify-center h-12 w-12 rounded-md bg-amber/15 text-amber border-[1.5px] border-amber">
        <ScrollText className="h-6 w-6" aria-hidden="true" />
      </span>
      <h3 className="text-xl">No tasks yet</h3>
      <p className="text-sm text-ink-soft max-w-md">
        Create the first task. Assign to an agent (Data Analyst, Researcher, Day
        AI Reviewer, GitHub Repo Admin) — or leave unassigned for backlog claim.
      </p>
      <button
        type="button"
        onClick={onCreate}
        className="mt-2 inline-flex items-center gap-1.5 h-9 px-4 rounded-md text-sm font-medium bg-amber text-ink border-[1.5px] border-border-bold hover:shadow-flat-sm transition-shadow"
      >
        <Plus className="h-4 w-4" aria-hidden="true" />
        New task
      </button>
    </div>
  );
}
