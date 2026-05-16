/**
 * Per-workspace analyst-agent card. Surfaces status, last run, cost, pending recommendations.
 * Reflects rows in agents table per [[../architecture/agent-runtime]] §Data Model Additions.
 * Tokens: --moss, --amber, --rust, --ink, --ink-soft, --cream-light
 * See [[design-system/components/agent-card]]
 */
"use client";

import * as React from "react";
import { formatDistanceToNowStrict } from "date-fns";
import { Bot, Activity, Pause, AlertCircle, CircleDashed, ChevronRight, Inbox } from "lucide-react";
import { cn } from "@/lib/utils";
import { CostBudgetMeter } from "./cost-budget-meter";

export type AgentStatus =
  | "active"
  | "idle"
  | "running"
  | "error"
  | "paused"
  | "terminated";

export interface AgentCardData {
  id: string;
  name: string;
  description?: string;
  status: AgentStatus;
  adapterType: string;
  lastRunAt?: Date | string | null;
  spentMonthlyCents: number;
  budgetMonthlyCents: number;
  pendingRecommendations: number;
}

const STATUS_META: Record<
  AgentStatus,
  { label: string; tone: string; Icon: React.ComponentType<{ className?: string }> }
> = {
  active: { label: "Active", tone: "text-moss", Icon: Activity },
  idle: { label: "Idle", tone: "text-ink-soft", Icon: CircleDashed },
  running: { label: "Running", tone: "text-amber", Icon: Activity },
  error: { label: "Error", tone: "text-rust", Icon: AlertCircle },
  paused: { label: "Paused", tone: "text-ink-soft", Icon: Pause },
  terminated: { label: "Terminated", tone: "text-ink-soft", Icon: Pause },
};

export interface AgentCardProps extends React.HTMLAttributes<HTMLDivElement> {
  agent: AgentCardData;
  onOpen?: (agentId: string) => void;
}

const AgentCard = React.forwardRef<HTMLDivElement, AgentCardProps>(
  ({ className, agent, onOpen, ...props }, ref) => {
    const status = STATUS_META[agent.status];
    const lastRunRel = agent.lastRunAt
      ? formatDistanceToNowStrict(
          typeof agent.lastRunAt === "string" ? new Date(agent.lastRunAt) : agent.lastRunAt,
          { addSuffix: true }
        )
      : "Never";

    const handleClick = () => onOpen?.(agent.id);
    const handleKey = (e: React.KeyboardEvent) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        onOpen?.(agent.id);
      }
    };

    return (
      <div
        ref={ref}
        role={onOpen ? "button" : undefined}
        tabIndex={onOpen ? 0 : undefined}
        onClick={onOpen ? handleClick : undefined}
        onKeyDown={onOpen ? handleKey : undefined}
        className={cn(
          "group flex flex-col gap-4 p-5 rounded-lg bg-card text-card-foreground",
          "border-[1.5px] border-border-bold",
          "transition-shadow duration-150",
          onOpen && "cursor-pointer hover:shadow-flat-sm focus-visible:shadow-flat-sm",
          className
        )}
        {...props}
      >
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-start gap-3 min-w-0">
            <div className="shrink-0 h-9 w-9 rounded-md bg-copper text-cream-light grid place-items-center">
              <Bot className="h-5 w-5" aria-hidden="true" />
            </div>
            <div className="min-w-0">
              <h4 className="truncate text-xl">{agent.name}</h4>
              {agent.description && (
                <p className="text-sm text-muted-foreground line-clamp-2">
                  {agent.description}
                </p>
              )}
            </div>
          </div>
          {onOpen && (
            <ChevronRight
              className="h-4 w-4 text-ink-soft shrink-0 transition-transform group-hover:translate-x-0.5"
              aria-hidden="true"
            />
          )}
        </div>

        <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 text-sm">
          <span className={cn("inline-flex items-center gap-1.5", status.tone)}>
            <status.Icon className="h-3.5 w-3.5" aria-hidden="true" />
            <span className="font-medium">{status.label}</span>
          </span>
          <span className="text-ink-soft">
            Last run <span className="text-ink">{lastRunRel}</span>
          </span>
          <span className="font-mono text-xs text-ink-soft truncate">
            {agent.adapterType}
          </span>
        </div>

        <CostBudgetMeter
          spentCents={agent.spentMonthlyCents}
          budgetCents={agent.budgetMonthlyCents}
          size="sm"
        />

        {agent.pendingRecommendations > 0 && (
          <div className="flex items-center justify-between pt-2 border-t border-border">
            <span className="inline-flex items-center gap-2 text-sm">
              <Inbox className="h-4 w-4 text-amber" aria-hidden="true" />
              <span className="font-medium">
                {agent.pendingRecommendations} pending
                {agent.pendingRecommendations === 1 ? " recommendation" : " recommendations"}
              </span>
            </span>
            <span className="inline-flex items-center justify-center h-6 min-w-6 px-1.5 rounded-sm bg-amber text-ink text-xs font-semibold border-[1.5px] border-ink">
              {agent.pendingRecommendations}
            </span>
          </div>
        )}
      </div>
    );
  }
);
AgentCard.displayName = "AgentCard";

export { AgentCard };
