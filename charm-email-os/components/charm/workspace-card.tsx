/**
 * Workspace card — home grid item. The control-plane summary for one client.
 * Surfaces: internal infra metrics, external integrations, analyst agents,
 * pending recommendations, context freshness.
 * `--shadow-flat` reserved for cards with attentionState !== 'healthy' (per
 * [[design-system/tokens/effects]] §Shadows).
 * Tokens: --amber, --moss, --rust, --honey, --ink, --cream-light
 * See [[design-system/components/workspace-card]]
 */
"use client";

import * as React from "react";
import Link from "next/link";
import { formatDistanceToNowStrict } from "date-fns";
import { ChevronRight, Boxes, Calendar, Bot, Inbox, Plug } from "lucide-react";
import { cn } from "@/lib/utils";
import {
  ContextFreshnessPill,
  type SyncStatus,
} from "./context-freshness-pill";

export type AttentionState = "healthy" | "amber" | "red";
export type IntegrationStatus = "connected" | "drift" | "disconnected";

export interface IntegrationSummary {
  name: string;
  status: IntegrationStatus;
}

export interface WorkspaceCardData {
  id: string;
  name: string;
  slug?: string;
  domainsLive: number;
  domainsTotal: number;
  /** Real domain count (separate from inbox-as-domain metric). */
  realDomainCount?: number;
  /** Real campaign count from /api/clients (live). */
  campaignCount?: number;
  /** Package name from subscription, e.g. "Growth". */
  packageName?: string | null;
  /** True when the EmailBison sync daemon is managing this workspace + it has infra. */
  isActive?: boolean;
  lastEventAt?: Date | string | null;
  lastEventType?: string;
  eodReapplyEnabled: boolean;
  monthlySpendCents: number;
  agentsActive: number;
  pendingRecommendations: number;
  contextSync: {
    status: SyncStatus;
    lastSyncedAt?: Date | string | null;
  };
  integrations: IntegrationSummary[];
  attentionState: AttentionState;
}

const ATTENTION_TONE: Record<AttentionState, string> = {
  healthy: "bg-moss",
  amber: "bg-amber",
  red: "bg-rust",
};

const ATTENTION_LABEL: Record<AttentionState, string> = {
  healthy: "Healthy",
  amber: "Attention",
  red: "Action required",
};

const INTEGRATION_TONE: Record<IntegrationStatus, string> = {
  connected: "border-moss text-moss",
  drift: "border-honey text-honey",
  disconnected: "border-storm text-ink-soft",
};

function formatUsd(cents: number): string {
  const dollars = cents / 100;
  if (dollars < 100) return `$${dollars.toFixed(0)}`;
  if (dollars < 1000) return `$${dollars.toFixed(0)}`;
  return `$${(dollars / 1000).toFixed(1)}k`;
}

export interface WorkspaceCardProps {
  workspace: WorkspaceCardData;
  /** Imperative open callback (client components). */
  onOpen?: (workspaceId: string) => void;
  /** Link href (server components). Renders as Next Link wrapper if provided. */
  href?: string;
  /** Override label for the primary count metric (default: "Inboxes"). */
  metricLabel?: string;
  className?: string;
}

const WorkspaceCard = React.forwardRef<HTMLDivElement, WorkspaceCardProps>(
  (
    { className, workspace, onOpen, href, metricLabel = "Inboxes" },
    ref
  ) => {
    const needsAttention = workspace.attentionState !== "healthy";
    const interactive = !!onOpen || !!href;
    const lastEventRel = workspace.lastEventAt
      ? formatDistanceToNowStrict(
          typeof workspace.lastEventAt === "string"
            ? new Date(workspace.lastEventAt)
            : workspace.lastEventAt,
          { addSuffix: true }
        )
      : "No events yet";

    const handleClick = () => onOpen?.(workspace.id);
    const handleKey = (e: React.KeyboardEvent) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        onOpen?.(workspace.id);
      }
    };

    const surfaceClass = cn(
      "group flex flex-col gap-5 p-6 rounded-lg bg-card text-card-foreground",
      "border-[1.5px] border-border-bold",
      needsAttention ? "shadow-flat" : "shadow-none",
      interactive &&
        "cursor-pointer hover:shadow-flat focus-visible:shadow-flat transition-shadow",
      className
    );

    const cardBody = (
      <>
        {/* Header — name + attention indicator */}
        <header className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <h3 className="text-2xl truncate">{workspace.name}</h3>
            {workspace.slug && (
              <p className="font-mono text-xs text-ink-soft truncate">
                {workspace.slug}
              </p>
            )}
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <span className="inline-flex items-center gap-1.5 text-xs font-medium text-ink-soft">
              <span
                className={cn(
                  "h-2 w-2 rounded-full",
                  ATTENTION_TONE[workspace.attentionState]
                )}
                aria-hidden="true"
              />
              {ATTENTION_LABEL[workspace.attentionState]}
            </span>
            {interactive && (
              <ChevronRight
                className="h-4 w-4 text-ink-soft transition-transform group-hover:translate-x-0.5"
                aria-hidden="true"
              />
            )}
          </div>
        </header>

        {/* Metric row */}
        <div className="grid grid-cols-3 gap-4 text-sm">
          <div className="flex flex-col gap-0.5">
            <span className="text-xs text-ink-soft inline-flex items-center gap-1">
              <Boxes className="h-3 w-3" aria-hidden="true" /> {metricLabel}
            </span>
            <span className="text-foreground font-mono">
              {workspace.domainsLive}
              <span className="text-ink-soft"> / {workspace.domainsTotal}</span>
            </span>
          </div>
          <div className="flex flex-col gap-0.5">
            <span className="text-xs text-ink-soft inline-flex items-center gap-1">
              <Calendar className="h-3 w-3" aria-hidden="true" /> EOD
            </span>
            <span className="text-foreground">
              {workspace.eodReapplyEnabled ? "On" : "Off"}
            </span>
          </div>
          <div className="flex flex-col gap-0.5">
            <span className="text-xs text-ink-soft">Spend / mo</span>
            <span className="text-foreground font-mono">
              {formatUsd(workspace.monthlySpendCents)}
            </span>
          </div>
        </div>

        {/* Integrations */}
        {workspace.integrations.length > 0 && (
          <div className="flex flex-wrap items-center gap-1.5">
            <Plug className="h-3.5 w-3.5 text-ink-soft" aria-hidden="true" />
            {workspace.integrations.map((integration) => (
              <span
                key={integration.name}
                className={cn(
                  "inline-flex items-center h-5 px-1.5 rounded-sm border-[1.5px] text-xs font-medium",
                  INTEGRATION_TONE[integration.status]
                )}
                title={`${integration.name}: ${integration.status}`}
              >
                {integration.name}
              </span>
            ))}
          </div>
        )}

        {/* Agents + recommendations row */}
        <div className="flex items-center justify-between gap-3 pt-2 border-t border-border">
          <span className="inline-flex items-center gap-1.5 text-sm text-ink-soft">
            <Bot className="h-3.5 w-3.5" aria-hidden="true" />
            <span className="text-foreground font-medium">{workspace.agentsActive}</span>
            agent{workspace.agentsActive === 1 ? "" : "s"}
          </span>

          {workspace.pendingRecommendations > 0 ? (
            <span className="inline-flex items-center gap-1.5 text-sm">
              <Inbox className="h-3.5 w-3.5 text-amber" aria-hidden="true" />
              <span className="font-medium text-foreground">
                {workspace.pendingRecommendations}
              </span>
              <span className="text-ink-soft">pending</span>
              <span className="inline-flex items-center justify-center h-5 min-w-5 px-1 rounded-sm bg-amber text-ink text-xs font-semibold border-[1.5px] border-ink">
                {workspace.pendingRecommendations}
              </span>
            </span>
          ) : (
            <span className="text-sm text-ink-soft">No pending</span>
          )}
        </div>

        {/* Footer — last event + context freshness */}
        <footer className="flex items-center justify-between gap-3 text-xs text-ink-soft">
          <span className="truncate">
            {workspace.lastEventType ? (
              <>
                <span className="font-medium text-foreground">{workspace.lastEventType}</span>{" "}
                {lastEventRel}
              </>
            ) : (
              lastEventRel
            )}
          </span>
          <ContextFreshnessPill
            status={workspace.contextSync.status}
            lastSyncedAt={workspace.contextSync.lastSyncedAt}
          />
        </footer>
      </>
    );

    // Render as Link (server-component friendly) when href is provided
    if (href && !onOpen) {
      return (
        <Link
          href={href}
          aria-label={`Open workspace ${workspace.name}`}
          className={cn(surfaceClass, "no-underline")}
        >
          {cardBody}
        </Link>
      );
    }

    // Render as button-div (client component with onClick)
    return (
      <div
        ref={ref}
        role={onOpen ? "button" : undefined}
        tabIndex={onOpen ? 0 : undefined}
        onClick={onOpen ? handleClick : undefined}
        onKeyDown={onOpen ? handleKey : undefined}
        aria-label={interactive ? `Open workspace ${workspace.name}` : undefined}
        className={surfaceClass}
      >
        {cardBody}
      </div>
    );
  }
);
WorkspaceCard.displayName = "WorkspaceCard";

export { WorkspaceCard };
