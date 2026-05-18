/**
 * HomePanels — client-side fetch of cross-workspace pending decisions +
 * recent activity. Two supplementary panels for the Home daily landing.
 */
"use client";

import * as React from "react";
import Link from "next/link";
import { formatDistanceToNowStrict } from "date-fns";
import { Sparkles, Activity, ChevronRight } from "lucide-react";
import { taskApi } from "@/lib/api";
import type { Task } from "@/lib/types";
import { cn } from "@/lib/utils";

export function HomePanels() {
  const [tasks, setTasks] = React.useState<Task[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await taskApi.list({ includeClosed: false, pageSize: 100 });
        if (cancelled) return;
        setTasks(res.items);
      } catch (err) {
        console.error(err);
        if (!cancelled) setError("Couldn't load activity (backend may be offline)");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const pending = React.useMemo(
    () => tasks.filter((t) => t.interactionPendingCount > 0).slice(0, 5),
    [tasks]
  );
  const recent = React.useMemo(
    () =>
      [...tasks]
        .sort((a, b) => new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime())
        .slice(0, 6),
    [tasks]
  );

  if (loading && tasks.length === 0) {
    return (
      <div className="text-xs text-ink-soft text-center py-4">Loading activity…</div>
    );
  }

  if (error) {
    return (
      <div className="text-xs text-ink-soft text-center py-4 border border-dashed border-border rounded-md">
        {error}
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
      <Panel
        title="Pending decisions"
        icon={Sparkles}
        accent="amber"
        emptyTitle="Nothing waiting on you"
        emptyBody="Agents will surface pending decisions here when they need your nod."
        rows={pending}
        renderRow={(t) => (
          <Link
            key={t.id}
            href={`/tasks/${t.id}`}
            className="flex items-center justify-between gap-3 px-3 py-2 rounded-md hover:bg-muted transition-colors border-[1.5px] border-transparent hover:border-border"
          >
            <div className="min-w-0">
              <p className="text-sm font-medium truncate">{t.title}</p>
              <p className="text-xs text-ink-soft truncate">
                {t.workspaceName ?? "Cross-workspace"}
                {t.assigneeAgentName && <> · {t.assigneeAgentName}</>}
              </p>
            </div>
            <span className="inline-flex items-center justify-center h-5 min-w-5 px-1 rounded-sm bg-amber text-ink text-xs font-semibold border-[1.5px] border-ink shrink-0">
              {t.interactionPendingCount}
            </span>
          </Link>
        )}
      />

      <Panel
        title="Recent activity"
        icon={Activity}
        accent="sky"
        emptyTitle="No recent activity"
        emptyBody="Tasks and projects you're working on will appear here as they update."
        rows={recent}
        renderRow={(t) => (
          <Link
            key={t.id}
            href={`/tasks/${t.id}`}
            className="flex items-center justify-between gap-3 px-3 py-2 rounded-md hover:bg-muted transition-colors border-[1.5px] border-transparent hover:border-border"
          >
            <div className="min-w-0">
              <p className="text-sm truncate">{t.title}</p>
              <p className="text-xs text-ink-soft truncate">
                {t.workspaceName ?? "Cross-workspace"}
                {" · "}
                <span className="capitalize">{t.status.replace("_", " ")}</span>
              </p>
            </div>
            <span
              className="text-xs text-ink-soft font-mono shrink-0"
              title={t.updatedAt}
            >
              {formatDistanceToNowStrict(new Date(t.updatedAt), { addSuffix: true })}
            </span>
          </Link>
        )}
      />
    </div>
  );
}

function Panel<T>({
  title,
  icon: Icon,
  accent,
  emptyTitle,
  emptyBody,
  rows,
  renderRow,
}: {
  title: string;
  icon: React.ComponentType<{ className?: string }>;
  accent: "amber" | "sky";
  emptyTitle: string;
  emptyBody: string;
  rows: T[];
  renderRow: (row: T) => React.ReactNode;
}) {
  const accentClass = accent === "amber" ? "text-amber" : "text-sky";

  return (
    <section className="rounded-lg border-[1.5px] border-border-bold bg-card">
      <header className="px-4 py-3 border-b border-border flex items-center justify-between">
        <h2 className="text-sm font-medium inline-flex items-center gap-2">
          <Icon className={cn("h-4 w-4", accentClass)} aria-hidden="true" />
          {title}
        </h2>
        {rows.length > 0 && (
          <span className="text-xs font-mono text-ink-soft">{rows.length}</span>
        )}
      </header>
      <div className="p-2">
        {rows.length === 0 ? (
          <div className="px-3 py-6 text-center">
            <p className="text-sm font-medium">{emptyTitle}</p>
            <p className="text-xs text-ink-soft mt-1 max-w-xs mx-auto">{emptyBody}</p>
          </div>
        ) : (
          <div className="space-y-0.5">{rows.map(renderRow)}</div>
        )}
      </div>
    </section>
  );
}
