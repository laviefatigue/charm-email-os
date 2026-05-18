/**
 * CampaignsTable — Village-styled table of campaigns.
 * Each row: name, status, sends, positive replies, bounce rate, last activity,
 * with a per-row "Audit this campaign" CTA that opens NewTaskModal pre-filled.
 */
"use client";

import * as React from "react";
import { format, formatDistanceToNowStrict } from "date-fns";
import { ArrowRight, Sparkles } from "lucide-react";
import { cn } from "@/lib/utils";
import type { Campaign } from "@/lib/types";

export interface CampaignsTableProps {
  campaigns: Campaign[];
  /** Show workspace column (true for global /campaigns). */
  showWorkspace?: boolean;
  /** Map clientId → workspace name when showWorkspace=true. */
  workspaceNameById?: Map<string, string>;
  onAudit: (campaign: Campaign) => void;
  className?: string;
}

function formatPct(n: number | undefined): string {
  if (n == null || Number.isNaN(n)) return "—";
  return `${(n * 100).toFixed(1)}%`;
}

function formatRate(n: number | undefined): string {
  if (n == null || Number.isNaN(n)) return "—";
  // Bounce rate is stored as percent already in some APIs; we accept either by
  // assuming values > 1 are already percentage points and values <= 1 are ratios.
  if (n > 1) return `${n.toFixed(1)}%`;
  return `${(n * 100).toFixed(1)}%`;
}

const STATUS_TONE: Record<string, string> = {
  active: "border-moss text-moss",
  paused: "border-honey text-honey",
  completed: "border-ink-soft text-ink-soft",
  draft: "border-sky text-sky",
  ready: "border-sky text-sky",
  archived: "border-storm text-ink-soft",
};

export function CampaignsTable({
  campaigns,
  showWorkspace = false,
  workspaceNameById,
  onAudit,
  className,
}: CampaignsTableProps) {
  if (campaigns.length === 0) {
    return (
      <div
        className={cn(
          "flex flex-col items-center justify-center text-center gap-2 py-12 px-6",
          "rounded-xl border border-dashed border-border bg-muted/30",
          className
        )}
      >
        <p className="text-base font-medium">No campaigns yet</p>
        <p className="text-sm text-ink-soft max-w-md">
          Campaigns are populated by the EmailBison sync. Once a campaign sends,
          metrics will appear here.
        </p>
      </div>
    );
  }

  return (
    <div className={cn("rounded-lg border-[1.5px] border-border-bold bg-card overflow-hidden", className)}>
      <div className="overflow-x-auto custom-scrollbar">
        <table className="w-full text-sm">
          <thead className="bg-muted/40 border-b border-border">
            <tr>
              <Th>Campaign</Th>
              {showWorkspace && <Th>Workspace</Th>}
              <Th>Status</Th>
              <Th className="text-right font-mono">Sends</Th>
              <Th className="text-right font-mono">Replies</Th>
              <Th className="text-right font-mono">Bounce</Th>
              <Th>Last activity</Th>
              <Th className="w-px">{""}</Th>
            </tr>
          </thead>
          <tbody>
            {campaigns.map((c) => {
              const statusKey = (c.campaignStatus ?? c.status ?? "draft").toLowerCase();
              const wsLabel = c.clientId
                ? workspaceNameById?.get(c.clientId) ?? c.clientId.slice(0, 8)
                : "—";
              const sends = c.emailsSent ?? c.leadsContacted ?? c.totalLeadsContacted ?? 0;
              const replies = c.uniqueReplies ?? c.repliesCount ?? 0;
              const lastActivity = c.lastSnapshotAt
                ? formatDistanceToNowStrict(new Date(c.lastSnapshotAt), { addSuffix: true })
                : c.updatedAt
                  ? formatDistanceToNowStrict(new Date(c.updatedAt), { addSuffix: true })
                  : "—";
              const lastActivityTitle =
                c.lastSnapshotAt
                  ? format(new Date(c.lastSnapshotAt), "yyyy-MM-dd HH:mm")
                  : c.updatedAt
                    ? format(new Date(c.updatedAt), "yyyy-MM-dd HH:mm")
                    : undefined;
              return (
                <tr
                  key={c.id}
                  className="border-b border-border last:border-b-0 hover:bg-muted/30 transition-colors"
                >
                  <Td>
                    <span className="font-medium truncate block max-w-70" title={c.name ?? c.campaignName}>
                      {c.name ?? c.campaignName}
                    </span>
                    {(c.industry || c.segment) && (
                      <span className="text-xs text-ink-soft truncate block max-w-70">
                        {[c.industry, c.segment].filter(Boolean).join(" · ")}
                      </span>
                    )}
                  </Td>
                  {showWorkspace && (
                    <Td>
                      <span className="text-ink-soft text-xs truncate max-w-35 block" title={wsLabel}>
                        {wsLabel}
                      </span>
                    </Td>
                  )}
                  <Td>
                    <span
                      className={cn(
                        "inline-flex items-center px-2 h-5 rounded-sm border-[1.5px] text-xs font-medium capitalize",
                        STATUS_TONE[statusKey] ?? "border-border text-ink-soft"
                      )}
                    >
                      {statusKey}
                    </span>
                  </Td>
                  <Td className="text-right font-mono text-xs">
                    {sends.toLocaleString()}
                  </Td>
                  <Td className="text-right font-mono text-xs">
                    {replies.toLocaleString()}
                    {sends > 0 && (
                      <span className="text-ink-soft ml-1">
                        ({formatPct(replies / sends)})
                      </span>
                    )}
                  </Td>
                  <Td className="text-right font-mono text-xs">
                    {formatRate(c.bounceRate)}
                  </Td>
                  <Td>
                    <span className="text-xs text-ink-soft" title={lastActivityTitle}>
                      {lastActivity}
                    </span>
                  </Td>
                  <Td className="text-right pr-3">
                    <button
                      type="button"
                      onClick={() => onAudit(c)}
                      className="inline-flex items-center gap-1 h-7 px-2 rounded-sm border-[1.5px] border-border-bold bg-transparent text-xs font-medium hover:bg-amber hover:text-ink transition-colors whitespace-nowrap"
                      title="Send to Data Analyst for audit"
                    >
                      <Sparkles className="h-3 w-3" aria-hidden="true" />
                      Audit
                      <ArrowRight className="h-3 w-3" aria-hidden="true" />
                    </button>
                  </Td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Th({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <th
      className={cn(
        "text-left text-[10px] font-medium uppercase tracking-wider text-ink-soft px-3 py-2",
        className
      )}
    >
      {children}
    </th>
  );
}

function Td({ children, className }: { children: React.ReactNode; className?: string }) {
  return <td className={cn("px-3 py-2 align-top", className)}>{children}</td>;
}
