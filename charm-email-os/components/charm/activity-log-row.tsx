/**
 * Activity log row — daemon events, agent runs, and context-sync events interleaved.
 * Reflects event_log + agent_run_log + workspace_context_syncs surfaces per
 * [[../architecture/agent-runtime]] §Activity Log and [[../architecture/client-context-sync]] §Sync Worker.
 * Tokens: --moss, --rust, --amber, --copper, --sky, --ink, --ink-soft
 * See [[design-system/components/activity-log-row]]
 */
"use client";

import * as React from "react";
import { format, formatDistanceToNowStrict } from "date-fns";
import { Workflow, Bot, GitBranch, CheckCircle2, XCircle, Clock } from "lucide-react";
import { cn } from "@/lib/utils";

export type ActivityEventType = "daemon-event" | "agent-run" | "context-sync";
export type ActivityEventStatus = "ok" | "failed" | "in_progress" | "no_changes";

export interface ActivityEvent {
  id: string;
  timestamp: Date | string;
  type: ActivityEventType;
  /** Daemon name, agent name, or "context-sync" */
  actor: string;
  /** Human-readable action summary, e.g. "warmup_disable fired", "Performance Analyst completed run" */
  action: string;
  /** Optional one-line meta string (e.g. "47 inboxes affected", "commit a3b7c9d ← f12e8a4") */
  detail?: string;
  status?: ActivityEventStatus;
}

const TYPE_META: Record<
  ActivityEventType,
  { Icon: React.ComponentType<{ className?: string }>; tone: string; label: string }
> = {
  "daemon-event": { Icon: Workflow, tone: "text-copper", label: "Daemon" },
  "agent-run": { Icon: Bot, tone: "text-amber", label: "Agent" },
  "context-sync": { Icon: GitBranch, tone: "text-sky", label: "Context" },
};

const STATUS_META: Record<
  ActivityEventStatus,
  { Icon: React.ComponentType<{ className?: string }>; tone: string; label: string }
> = {
  ok: { Icon: CheckCircle2, tone: "text-moss", label: "OK" },
  failed: { Icon: XCircle, tone: "text-rust", label: "Failed" },
  in_progress: { Icon: Clock, tone: "text-amber", label: "In progress" },
  no_changes: { Icon: CheckCircle2, tone: "text-ink-soft", label: "No changes" },
};

export interface ActivityLogRowProps extends React.HTMLAttributes<HTMLLIElement> {
  event: ActivityEvent;
  /** Show absolute timestamp instead of relative (default: relative). */
  absoluteTime?: boolean;
  onOpen?: (eventId: string) => void;
}

const ActivityLogRow = React.forwardRef<HTMLLIElement, ActivityLogRowProps>(
  ({ className, event, absoluteTime = false, onOpen, ...props }, ref) => {
    const typeMeta = TYPE_META[event.type];
    const statusMeta = event.status ? STATUS_META[event.status] : null;
    const ts =
      typeof event.timestamp === "string"
        ? new Date(event.timestamp)
        : event.timestamp;
    const timeLabel = absoluteTime
      ? format(ts, "yyyy-MM-dd HH:mm")
      : formatDistanceToNowStrict(ts, { addSuffix: true });
    const tooltipTime = format(ts, "yyyy-MM-dd HH:mm:ss");

    const interactive = !!onOpen;

    return (
      <li
        ref={ref}
        role={interactive ? "button" : undefined}
        tabIndex={interactive ? 0 : undefined}
        onClick={interactive ? () => onOpen?.(event.id) : undefined}
        onKeyDown={
          interactive
            ? (e: React.KeyboardEvent) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  onOpen?.(event.id);
                }
              }
            : undefined
        }
        className={cn(
          "grid grid-cols-[auto_auto_1fr_auto] items-center gap-3 px-3 py-2.5",
          "border-b border-border last:border-b-0",
          interactive && "cursor-pointer hover:bg-muted/50 focus-visible:bg-muted/50 transition-colors",
          className
        )}
        {...props}
      >
        {/* Timestamp */}
        <time
          dateTime={ts.toISOString()}
          title={tooltipTime}
          className="font-mono text-xs text-ink-soft whitespace-nowrap"
        >
          {timeLabel}
        </time>

        {/* Type icon */}
        <span
          className={cn("inline-flex items-center", typeMeta.tone)}
          aria-label={typeMeta.label}
        >
          <typeMeta.Icon className="h-4 w-4" aria-hidden="true" />
        </span>

        {/* Actor + action + detail */}
        <div className="min-w-0 flex flex-col">
          <div className="flex items-baseline gap-2 min-w-0">
            <span className="text-sm font-medium text-foreground truncate">
              {event.actor}
            </span>
            <span className="text-sm text-ink-soft truncate">{event.action}</span>
          </div>
          {event.detail && (
            <span className="text-xs text-ink-soft font-mono truncate">
              {event.detail}
            </span>
          )}
        </div>

        {/* Status */}
        {statusMeta && (
          <span
            className={cn(
              "inline-flex items-center gap-1 text-xs font-medium shrink-0",
              statusMeta.tone
            )}
            aria-label={statusMeta.label}
          >
            <statusMeta.Icon className="h-3.5 w-3.5" aria-hidden="true" />
            <span className="hidden sm:inline">{statusMeta.label}</span>
          </span>
        )}
      </li>
    );
  }
);
ActivityLogRow.displayName = "ActivityLogRow";

export { ActivityLogRow };
