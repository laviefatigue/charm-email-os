/**
 * TaskCard — compact kanban cell for the Tasks board.
 * Renders title + priority + assignee + workspace + counts.
 * Tokens: --amber, --ink, --ink-soft, --rust, --moss, --sky, --honey
 */
"use client";

import * as React from "react";
import Link from "next/link";
import { formatDistanceToNowStrict } from "date-fns";
import {
  MessageSquare,
  FileText,
  CalendarClock,
  AlertTriangle,
  Flame,
  ChevronUp,
  Minus,
  ChevronDown,
  Bot,
} from "lucide-react";
import { cn } from "@/lib/utils";
import type { Task, TaskPriority } from "@/lib/types";

const PRIORITY_TONE: Record<TaskPriority, { color: string; Icon: React.ComponentType<{ className?: string }>; label: string }> = {
  urgent: { color: "text-rust", Icon: Flame, label: "Urgent" },
  high: { color: "text-honey", Icon: ChevronUp, label: "High" },
  medium: { color: "text-ink-soft", Icon: Minus, label: "Medium" },
  low: { color: "text-ink-soft", Icon: ChevronDown, label: "Low" },
};

const SOURCE_LABEL: Record<Task["source"], string> = {
  operator: "AE",
  agent: "Agent",
  inbound: "Inbound",
  system: "Auto",
};

export interface TaskCardProps {
  task: Task;
  href?: string;
  className?: string;
}

export function TaskCard({ task, href, className }: TaskCardProps) {
  const priority = PRIORITY_TONE[task.priority];
  const dueRel = task.dueAt
    ? formatDistanceToNowStrict(new Date(task.dueAt), { addSuffix: true })
    : null;
  const overdue =
    task.dueAt &&
    new Date(task.dueAt).getTime() < Date.now() &&
    task.status !== "done";

  const cardClass = cn(
    "flex flex-col gap-2.5 p-3 rounded-lg bg-card text-card-foreground",
    "border-[1.5px] border-border-bold transition-shadow",
    href && "cursor-pointer hover:shadow-flat-sm focus-visible:shadow-flat-sm",
    className
  );

  const content = (
    <>
      <div className="flex items-start gap-2">
        <priority.Icon
          className={cn("h-4 w-4 shrink-0 mt-0.5", priority.color)}
          aria-label={priority.label}
        />
        <p className="text-sm font-medium leading-tight flex-1 min-w-0">
          {task.title}
        </p>
      </div>

      <div className="flex flex-wrap items-center gap-1.5 text-xs text-ink-soft">
        {task.source === "inbound" && (
          <span className="inline-flex items-center gap-1 px-1.5 h-5 rounded-sm bg-sky/15 text-sky border border-sky font-medium">
            Inbound
          </span>
        )}
        {task.source === "operator" && (
          <span className="inline-flex items-center gap-1 px-1.5 h-5 rounded-sm border border-border text-ink-soft">
            {SOURCE_LABEL[task.source]}
          </span>
        )}
        {task.workspaceName && (
          <span className="truncate max-w-[120px]" title={task.workspaceName}>
            {task.workspaceName}
          </span>
        )}
      </div>

      <div className="flex items-center justify-between gap-2 pt-1.5 border-t border-border text-xs text-ink-soft">
        <span className="inline-flex items-center gap-1 min-w-0">
          <Bot className="h-3 w-3 shrink-0" aria-hidden="true" />
          <span className="truncate font-medium text-foreground">
            {task.assigneeAgentName ?? "Unassigned"}
          </span>
        </span>
        <span className="inline-flex items-center gap-2 shrink-0">
          {task.commentCount > 0 && (
            <span className="inline-flex items-center gap-0.5">
              <MessageSquare className="h-3 w-3" aria-hidden="true" />
              {task.commentCount}
            </span>
          )}
          {task.documentCount > 0 && (
            <span className="inline-flex items-center gap-0.5">
              <FileText className="h-3 w-3" aria-hidden="true" />
              {task.documentCount}
            </span>
          )}
        </span>
      </div>

      {dueRel && (
        <div
          className={cn(
            "inline-flex items-center gap-1 text-xs",
            overdue ? "text-rust font-medium" : "text-ink-soft"
          )}
        >
          {overdue ? (
            <AlertTriangle className="h-3 w-3" aria-hidden="true" />
          ) : (
            <CalendarClock className="h-3 w-3" aria-hidden="true" />
          )}
          {overdue ? `Overdue · ${dueRel}` : `Due ${dueRel}`}
        </div>
      )}
    </>
  );

  if (href) {
    return (
      <Link href={href} className={cn(cardClass, "no-underline")}>
        {content}
      </Link>
    );
  }
  return <div className={cardClass}>{content}</div>;
}
