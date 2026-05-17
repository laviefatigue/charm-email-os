/**
 * Screen: Tasks (Kanban)
 * Paperclip-pattern work queue. Operator creates tasks, assigns to agents,
 * tracks lifecycle Backlog → Todo → In Progress → In Review → Done (+ Blocked).
 *
 * Reads /api/tasks (live). Buttons mutate via /api/tasks (real).
 */
"use client";

import * as React from "react";
import Link from "next/link";
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
const BLOCKED_LANE: Lane = { status: "blocked", label: "Blocked" };

export default function TasksPage() {
  const [tasks, setTasks] = React.useState<Task[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);
  const [modalOpen, setModalOpen] = React.useState(false);

  const refetch = React.useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await taskApi.list({ includeClosed: true, pageSize: 200 });
      setTasks(res.items);
    } catch (err) {
      console.error(err);
      setError("Failed to load tasks");
    } finally {
      setLoading(false);
    }
  }, []);

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

  return (
    <div className="px-8 py-8 max-w-[1600px] w-full mx-auto">
      <PageHeader
        kicker="Work queue"
        title="Tasks"
        subtitle={`${tasks.length} task${tasks.length === 1 ? "" : "s"} across all workspaces. Assign to an agent or claim from backlog.`}
        actions={
          <button
            type="button"
            onClick={() => setModalOpen(true)}
            className="inline-flex items-center gap-1.5 h-9 px-4 rounded-md text-sm font-medium bg-amber text-ink border-[1.5px] border-border-bold hover:shadow-flat-sm focus-visible:shadow-flat-sm transition-shadow"
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
      ) : tasks.length === 0 && !loading ? (
        <EmptyBoard onCreate={() => setModalOpen(true)} />
      ) : (
        <>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-4 mb-6">
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
                  <TaskCard
                    key={task.id}
                    task={task}
                    href={`/tasks/${task.id}`}
                  />
                ))}
              </div>
            </div>
          )}
        </>
      )}

      <NewTaskModal
        open={modalOpen}
        onOpenChange={setModalOpen}
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
        <h3 className="text-sm font-medium uppercase tracking-wider text-ink-soft">
          {lane.label}
        </h3>
        <span className="text-xs font-mono text-ink-soft">{tasks.length}</span>
      </header>
      {tasks.length === 0 ? (
        <div className="text-xs text-ink-soft/60 italic px-1 py-3">No tasks</div>
      ) : (
        <div className="flex flex-col gap-2.5">
          {tasks.map((task) => (
            <TaskCard
              key={task.id}
              task={task}
              href={`/tasks/${task.id}`}
            />
          ))}
        </div>
      )}
    </section>
  );
}

function EmptyBoard({ onCreate }: { onCreate: () => void }) {
  return (
    <div className="flex flex-col items-center justify-center text-center gap-3 py-20 px-6 rounded-xl border border-dashed border-border bg-muted/30">
      <span className="inline-flex items-center justify-center h-12 w-12 rounded-md bg-amber/15 text-amber border-[1.5px] border-amber">
        <ScrollText className="h-6 w-6" aria-hidden="true" />
      </span>
      <h3 className="text-xl">No tasks yet</h3>
      <p className="text-sm text-ink-soft max-w-md">
        Create the first task. Assign it to one of the four agents (Data Analyst,
        Researcher, Day AI Reviewer, GitHub Repo Admin) — or leave unassigned for
        claim from the backlog.
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
