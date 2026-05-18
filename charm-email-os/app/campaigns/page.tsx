/**
 * Screen: Global Campaigns
 * Cross-workspace roll-up of all campaigns. Filterable by workspace + status.
 */
"use client";

import * as React from "react";
import { Megaphone } from "lucide-react";
import { campaignApi, agentApi } from "@/lib/api";
import { getWorkspaces } from "@/lib/data/charm";
import {
  PageHeader,
  CampaignsTable,
  NewTaskModal,
} from "@/components/charm";
import type { Agent, Campaign } from "@/lib/types";
import type { WorkspaceCardData as WCD } from "@/components/charm";
import { cn } from "@/lib/utils";

type StatusFilter = "all" | "active" | "paused" | "completed";

export default function CampaignsPage() {
  const [campaigns, setCampaigns] = React.useState<Campaign[]>([]);
  const [workspaces, setWorkspaces] = React.useState<WCD[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);
  const [statusFilter, setStatusFilter] = React.useState<StatusFilter>("all");
  const [workspaceFilter, setWorkspaceFilter] = React.useState<string>("");

  const [dataAnalyst, setDataAnalyst] = React.useState<Agent | null>(null);
  const [auditCampaign, setAuditCampaign] = React.useState<Campaign | null>(null);

  React.useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      try {
        const wsList = (await getWorkspaces()) as WCD[];
        if (cancelled) return;
        setWorkspaces(wsList);

        // Fetch campaigns per workspace, in parallel (5–20 workspaces; this is fine)
        const perWs = await Promise.all(
          wsList.map((ws) =>
            campaignApi
              .list({ clientId: ws.id, pageSize: 100 })
              .then((r) => r.items)
              .catch((err) => {
                console.warn(`Failed to load campaigns for ${ws.id}`, err);
                return [] as Campaign[];
              })
          )
        );
        const all = perWs.flat();
        if (cancelled) return;
        setCampaigns(all);

        const agents = await agentApi.list({ activeOnly: true }).then((r) => r.items);
        if (cancelled) return;
        setDataAnalyst(agents.find((a) => a.role === "data_analyst") ?? null);
      } catch (err) {
        console.error(err);
        if (!cancelled) setError("Failed to load campaigns");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const workspaceNameById = React.useMemo(
    () => new Map(workspaces.map((w) => [w.id, w.name])),
    [workspaces]
  );

  const filtered = React.useMemo(() => {
    return campaigns.filter((c) => {
      if (statusFilter !== "all") {
        const status = (c.campaignStatus ?? c.status ?? "").toLowerCase();
        if (status !== statusFilter) return false;
      }
      if (workspaceFilter && c.clientId !== workspaceFilter) return false;
      return true;
    });
  }, [campaigns, statusFilter, workspaceFilter]);

  const handleAudit = (c: Campaign) => setAuditCampaign(c);

  return (
    <div className="px-8 py-8 max-w-400 w-full mx-auto">
      <PageHeader
        kicker="Cross-workspace"
        title="Campaigns"
        subtitle={
          loading
            ? "Loading campaigns from all workspaces…"
            : `${campaigns.length} total · ${filtered.length} shown`
        }
      />

      {error && (
        <div className="mb-4 p-3 rounded-md border-[1.5px] border-rust bg-rust/10 text-rust text-sm">
          {error}
        </div>
      )}

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-2 mb-4">
        <span className="text-xs uppercase tracking-wider text-ink-soft mr-2">Status</span>
        {(["all", "active", "paused", "completed"] as StatusFilter[]).map((s) => (
          <button
            key={s}
            type="button"
            onClick={() => setStatusFilter(s)}
            className={cn(
              "inline-flex items-center h-7 px-3 rounded-sm text-xs font-medium border-[1.5px] capitalize transition-colors",
              statusFilter === s
                ? "bg-amber text-ink border-ink"
                : "bg-transparent text-ink-soft border-border hover:border-border-bold hover:text-foreground"
            )}
          >
            {s}
          </button>
        ))}

        <span className="text-xs uppercase tracking-wider text-ink-soft ml-3 mr-1">Workspace</span>
        <select
          value={workspaceFilter}
          onChange={(e) => setWorkspaceFilter(e.target.value)}
          className={cn(
            "h-7 rounded-sm border-[1.5px] border-border bg-background px-2 text-xs",
            "focus-visible:border-ring focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/40"
          )}
        >
          <option value="">All workspaces</option>
          {workspaces.map((w) => (
            <option key={w.id} value={w.id}>{w.name}</option>
          ))}
        </select>
      </div>

      {loading ? (
        <div className="text-sm text-ink-soft py-12 text-center">Loading…</div>
      ) : filtered.length === 0 ? (
        <div className="flex flex-col items-center justify-center text-center gap-3 py-16 px-6 rounded-xl border border-dashed border-border bg-muted/30">
          <span className="inline-flex items-center justify-center h-12 w-12 rounded-md bg-amber/15 text-amber border-[1.5px] border-amber">
            <Megaphone className="h-6 w-6" aria-hidden="true" />
          </span>
          <h3 className="text-xl">No campaigns match these filters</h3>
        </div>
      ) : (
        <CampaignsTable
          campaigns={filtered}
          showWorkspace
          workspaceNameById={workspaceNameById}
          onAudit={handleAudit}
        />
      )}

      <NewTaskModal
        open={!!auditCampaign}
        onOpenChange={(o) => !o && setAuditCampaign(null)}
        defaultWorkspaceId={auditCampaign?.clientId}
        defaultAssigneeAgentId={dataAnalyst?.id}
        defaultTitle={
          auditCampaign ? `Audit campaign: ${auditCampaign.name ?? auditCampaign.campaignName}` : ""
        }
        defaultDescription={auditCampaign ? buildAuditDescription(auditCampaign) : ""}
        onCreated={(taskId) => {
          setAuditCampaign(null);
          window.location.href = `/tasks/${taskId}`;
        }}
      />
    </div>
  );
}

function buildAuditDescription(c: Campaign): string {
  const sends = c.emailsSent ?? c.leadsContacted ?? c.totalLeadsContacted ?? 0;
  const replies = c.uniqueReplies ?? c.repliesCount ?? 0;
  const replyRate = sends > 0 ? ((replies / sends) * 100).toFixed(1) : "—";
  const bounce = c.bounceRate != null ? (c.bounceRate > 1 ? c.bounceRate.toFixed(1) : (c.bounceRate * 100).toFixed(1)) : "—";

  const lines: string[] = [
    "Produce a performance audit for this EmailBison campaign.",
    "",
    "## Campaign snapshot",
    `- **Name:** ${c.name ?? c.campaignName}`,
  ];
  if (c.industry || c.segment || c.angle) {
    lines.push(`- **Targeting:** ${[c.industry, c.segment, c.angle].filter(Boolean).join(" · ")}`);
  }
  lines.push(`- **Status:** ${c.campaignStatus ?? c.status ?? "unknown"}`);
  lines.push(`- **Campaign ID (CharmDB):** \`${c.id}\``);
  if (c.emailbisonCampaignId) lines.push(`- **EmailBison campaign ID:** \`${c.emailbisonCampaignId}\``);
  if (c.workspaceId) lines.push(`- **Workspace ID (OwnRBL):** \`${c.workspaceId}\``);
  lines.push("");
  lines.push(`## Headline metrics`);
  lines.push(`- Sends: **${sends.toLocaleString()}**`);
  lines.push(`- Unique replies: **${replies.toLocaleString()}** (${replyRate}%)`);
  if (c.uniqueOpens != null) lines.push(`- Unique opens: **${c.uniqueOpens.toLocaleString()}**`);
  if (c.bounced != null) lines.push(`- Bounced: **${c.bounced.toLocaleString()}**`);
  lines.push(`- Bounce rate: **${bounce}%**`);
  if (c.unsubscribed != null) lines.push(`- Unsubscribed: **${c.unsubscribed.toLocaleString()}**`);
  if (c.spamComplaints != null) lines.push(`- Spam complaints: **${c.spamComplaints.toLocaleString()}**`);
  lines.push("");
  lines.push(`## What the operator wants`);
  lines.push(`Audit performance vs the workspace's package targets and historical baseline. Flag deliverability concerns. Surface what worked (segments, sender names, angles) and what didn't. End with concrete recommendations the AE can act on this week.`);
  lines.push("");
  lines.push(`## Data to pull`);
  lines.push(`Query OwnRBL for: per-sender-account performance, per-domain bounce concentration (ESP-split), reply timing distribution, kill triggers fired in the window.`);
  return lines.join("\n");
}
