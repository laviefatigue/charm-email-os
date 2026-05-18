/**
 * Screen: Workspace Overview
 * Synthesized landing for a workspace. Surfaces:
 *  • Active projects (with progress)
 *  • Active tasks (assigned + pending)
 *  • Today's chronicle (recent events)
 *
 * Reads live: /api/projects (filtered), /api/tasks (filtered), getEvents (mock until daemons feed in).
 */
"use client";

import * as React from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { ChevronRight, ScrollText, FolderKanban, ListTodo } from "lucide-react";
import {
  ActivityLogRow,
  ProjectCard,
  TaskCard,
} from "@/components/charm";
import { projectApi, taskApi } from "@/lib/api";
import { getEvents } from "@/lib/data/charm";
import type { Project, Task } from "@/lib/types";

export default function WorkspaceOverviewPage() {
  const { id } = useParams<{ id: string }>();
  const [projects, setProjects] = React.useState<Project[]>([]);
  const [tasks, setTasks] = React.useState<Task[]>([]);
  const [loading, setLoading] = React.useState(true);
  const events = React.useMemo(() => getEvents(id).slice(0, 8), [id]);

  React.useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [ps, ts] = await Promise.all([
          projectApi.list({ workspaceId: id, includeClosed: false }),
          taskApi.list({ workspaceId: id, includeClosed: false, pageSize: 50 }),
        ]);
        if (cancelled) return;
        setProjects(ps.items);
        setTasks(ts.items);
      } catch (err) {
        console.error("Failed to load workspace overview", err);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [id]);

  const activeTasks = tasks
    .filter((t) => t.status === "in_progress" || t.status === "in_review")
    .slice(0, 6);
  const needsDecision = tasks.filter((t) => t.interactionPendingCount > 0);

  return (
    <div className="space-y-10">
      {/* Stats strip */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Stat label="Active projects" value={String(projects.length)} href={`/workspaces/${id}/projects`} />
        <Stat label="Active tasks" value={String(activeTasks.length)} href={`/workspaces/${id}/tasks`} />
        <Stat
          label="Needs decision"
          value={String(needsDecision.length)}
          tone={needsDecision.length > 0 ? "amber" : "ink-soft"}
          href={`/workspaces/${id}/tasks`}
        />
        <Stat label="Events (24h)" value={String(events.length)} href={`/workspaces/${id}/events`} />
      </div>

      {/* Active projects */}
      <section aria-labelledby="overview-projects">
        <div className="flex items-center justify-between mb-4">
          <h2 id="overview-projects" className="text-2xl inline-flex items-center gap-2">
            <FolderKanban className="h-5 w-5 text-copper" aria-hidden="true" />
            Active projects
          </h2>
          <Link
            href={`/workspaces/${id}/projects`}
            className="inline-flex items-center gap-1 text-sm text-copper hover:underline focus-visible:underline"
          >
            All projects
            <ChevronRight className="h-3.5 w-3.5" aria-hidden="true" />
          </Link>
        </div>
        {loading ? (
          <div className="text-sm text-ink-soft">Loading…</div>
        ) : projects.length === 0 ? (
          <EmptyState
            title="No active projects"
            description="Create the first project to plan multi-task work for this client."
            cta={{ label: "Open Projects", href: `/workspaces/${id}/projects` }}
          />
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {projects.slice(0, 4).map((p) => (
              <ProjectCard key={p.id} project={p} href={`/projects/${p.id}`} />
            ))}
          </div>
        )}
      </section>

      {/* Active tasks */}
      <section aria-labelledby="overview-tasks">
        <div className="flex items-center justify-between mb-4">
          <h2 id="overview-tasks" className="text-2xl inline-flex items-center gap-2">
            <ListTodo className="h-5 w-5 text-amber" aria-hidden="true" />
            Active tasks
          </h2>
          <Link
            href={`/workspaces/${id}/tasks`}
            className="inline-flex items-center gap-1 text-sm text-copper hover:underline focus-visible:underline"
          >
            All tasks
            <ChevronRight className="h-3.5 w-3.5" aria-hidden="true" />
          </Link>
        </div>
        {loading ? (
          <div className="text-sm text-ink-soft">Loading…</div>
        ) : activeTasks.length === 0 ? (
          <EmptyState
            title="No active tasks"
            description="Nothing in progress right now. Open the Tasks board to create one or pick from backlog."
            cta={{ label: "Open Tasks", href: `/workspaces/${id}/tasks` }}
          />
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
            {activeTasks.map((t) => (
              <TaskCard key={t.id} task={t} href={`/tasks/${t.id}`} />
            ))}
          </div>
        )}
      </section>

      {/* Chronicle */}
      <section aria-labelledby="overview-chronicle">
        <div className="flex items-center justify-between mb-4">
          <h2 id="overview-chronicle" className="text-2xl inline-flex items-center gap-2">
            <ScrollText className="h-5 w-5 text-sky" aria-hidden="true" />
            Today&apos;s chronicle
          </h2>
          <Link
            href={`/workspaces/${id}/events`}
            className="inline-flex items-center gap-1 text-sm text-copper hover:underline focus-visible:underline"
          >
            Full activity log
            <ChevronRight className="h-3.5 w-3.5" aria-hidden="true" />
          </Link>
        </div>
        {events.length === 0 ? (
          <EmptyState
            title="No events yet"
            description="Daemon events, agent runs, and context syncs will appear here as the workspace activates."
          />
        ) : (
          <ul className="rounded-lg border-[1.5px] border-border-bold bg-card overflow-hidden">
            {events.map((event) => (
              <ActivityLogRow key={event.id} event={event} />
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

function Stat({
  label,
  value,
  tone = "ink",
  href,
}: {
  label: string;
  value: string;
  tone?: "ink" | "ink-soft" | "amber" | "moss" | "rust";
  href?: string;
}) {
  const toneClass = {
    ink: "text-foreground",
    "ink-soft": "text-ink-soft",
    amber: "text-amber",
    moss: "text-moss",
    rust: "text-rust",
  }[tone];
  const body = (
    <div className="rounded-lg border-[1.5px] border-border-bold bg-card p-3 transition-shadow hover:shadow-flat-sm">
      <p className="text-xs uppercase tracking-wider text-ink-soft">{label}</p>
      <p className={`text-2xl font-mono mt-0.5 ${toneClass}`}>{value}</p>
    </div>
  );
  return href ? (
    <Link href={href} className="no-underline">{body}</Link>
  ) : (
    body
  );
}

function EmptyState({
  title,
  description,
  cta,
}: {
  title: string;
  description: string;
  cta?: { label: string; href: string };
}) {
  return (
    <div className="flex flex-col items-center justify-center text-center gap-2 py-10 px-6 rounded-lg border border-dashed border-border bg-muted/30">
      <p className="text-base font-medium">{title}</p>
      <p className="text-sm text-ink-soft max-w-md">{description}</p>
      {cta && (
        <Link
          href={cta.href}
          className="mt-1 text-sm text-copper hover:underline focus-visible:underline"
        >
          {cta.label} →
        </Link>
      )}
    </div>
  );
}
