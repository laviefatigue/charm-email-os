/**
 * ProjectCard — compact card for project lists.
 * Shows progress bar, status, priority, dates, task counts, attention.
 */
"use client";

import * as React from "react";
import Link from "next/link";
import { format, formatDistanceToNowStrict } from "date-fns";
import {
  CalendarClock,
  AlertTriangle,
  CheckCircle2,
  Pause,
  XCircle,
  PlayCircle,
  ClipboardList,
} from "lucide-react";
import { cn } from "@/lib/utils";
import type { Project, ProjectStatus } from "@/lib/types";

const STATUS_META: Record<
  ProjectStatus,
  { label: string; tone: string; Icon: React.ComponentType<{ className?: string }> }
> = {
  planning: { label: "Planning", tone: "text-sky", Icon: ClipboardList },
  active: { label: "Active", tone: "text-moss", Icon: PlayCircle },
  paused: { label: "Paused", tone: "text-honey", Icon: Pause },
  done: { label: "Done", tone: "text-ink-soft", Icon: CheckCircle2 },
  cancelled: { label: "Cancelled", tone: "text-ink-soft", Icon: XCircle },
};

export interface ProjectCardProps {
  project: Project;
  href?: string;
  className?: string;
}

export function ProjectCard({ project, href, className }: ProjectCardProps) {
  const meta = STATUS_META[project.status];
  const { progress } = project;
  const overdue = progress.overdueTasks > 0;
  const blocked = progress.blockedTasks > 0;

  const dateLabel = (() => {
    if (project.actualEndAt) return `Ended ${format(new Date(project.actualEndAt), "MMM d")}`;
    if (project.targetEndAt)
      return `Due ${formatDistanceToNowStrict(new Date(project.targetEndAt), { addSuffix: true })}`;
    if (project.startAt) return `Starts ${formatDistanceToNowStrict(new Date(project.startAt), { addSuffix: true })}`;
    return "No dates set";
  })();

  const cardClass = cn(
    "flex flex-col gap-3 p-4 rounded-lg bg-card text-card-foreground",
    "border-[1.5px] border-border-bold transition-shadow",
    (overdue || blocked) && project.status === "active" && "shadow-flat",
    href && "cursor-pointer hover:shadow-flat focus-visible:shadow-flat",
    className
  );

  const body = (
    <>
      <header className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <h3 className="text-base font-medium truncate">{project.name}</h3>
          {project.workspaceName && (
            <p className="text-xs text-ink-soft truncate">{project.workspaceName}</p>
          )}
        </div>
        <span className={cn("inline-flex items-center gap-1 text-xs font-medium shrink-0", meta.tone)}>
          <meta.Icon className="h-3.5 w-3.5" aria-hidden="true" />
          {meta.label}
        </span>
      </header>

      {project.description && (
        <p className="text-xs text-ink-soft line-clamp-2">{project.description}</p>
      )}

      {/* Progress bar */}
      <div className="space-y-1">
        <div className="flex items-center justify-between text-xs">
          <span className="text-ink-soft">
            {progress.doneTasks} / {progress.totalTasks} tasks
          </span>
          <span className="font-mono font-medium">{progress.percentDone}%</span>
        </div>
        <div className="h-2 rounded-full bg-cream border border-ink overflow-hidden">
          <div
            className="h-full bg-moss transition-all duration-300"
            style={{ width: `${Math.min(100, progress.percentDone)}%` }}
          />
        </div>
      </div>

      <div className="flex items-center justify-between gap-2 text-xs text-ink-soft pt-2 border-t border-border">
        <span className="inline-flex items-center gap-1">
          <CalendarClock className="h-3 w-3" aria-hidden="true" />
          {dateLabel}
        </span>
        <span className="inline-flex items-center gap-2">
          {blocked && (
            <span className="inline-flex items-center gap-0.5 text-rust">
              <AlertTriangle className="h-3 w-3" aria-hidden="true" />
              {progress.blockedTasks}
            </span>
          )}
          {overdue && (
            <span className="inline-flex items-center gap-0.5 text-rust font-medium">
              <AlertTriangle className="h-3 w-3" aria-hidden="true" />
              {progress.overdueTasks} overdue
            </span>
          )}
        </span>
      </div>
    </>
  );

  return href ? (
    <Link href={href} className={cn(cardClass, "no-underline")}>{body}</Link>
  ) : (
    <div className={cardClass}>{body}</div>
  );
}
