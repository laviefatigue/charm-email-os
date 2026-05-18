/**
 * Screen: Workspace Campaigns
 * Real EmailBison data per /api/campaigns?client_id=X. Per-row "Audit this"
 * trigger opens NewTaskModal pre-filled with campaign context + Data Analyst
 * assignee — the AE → agent delegation path.
 */
"use client";

import * as React from "react";
import { useParams } from "next/navigation";
import { Megaphone } from "lucide-react";
import { campaignApi, agentApi } from "@/lib/api";
import {
  PageHeader,
  CampaignsTable,
  NewTaskModal,
} from "@/components/charm";
import type { Agent, Campaign } from "@/lib/types";

export default function WorkspaceCampaignsPage() {
  const { id } = useParams<{ id: string }>();
  const [campaigns, setCampaigns] = React.useState<Campaign[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);

  const [dataAnalyst, setDataAnalyst] = React.useState<Agent | null>(null);
  const [auditCampaign, setAuditCampaign] = React.useState<Campaign | null>(null);

  React.useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      try {
        const [c, agents] = await Promise.all([
          campaignApi.list({ clientId: id, pageSize: 200 }),
          agentApi.list({ activeOnly: true }).then((r) => r.items),
        ]);
        if (cancelled) return;
        setCampaigns(c.items);
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
  }, [id]);

  const stats = React.useMemo(() => {
    const active = campaigns.filter((c) => (c.campaignStatus ?? c.status) === "active").length;
    const sends = campaigns.reduce((s, c) => s + (c.emailsSent ?? 0), 0);
    const replies = campaigns.reduce((s, c) => s + (c.uniqueReplies ?? 0), 0);
    return { active, sends, replies };
  }, [campaigns]);

  const handleAudit = (c: Campaign) => setAuditCampaign(c);
  const auditTitle = auditCampaign ? `Audit campaign: ${auditCampaign.name ?? auditCampaign.campaignName}` : "";
  const auditDescription = auditCampaign ? buildAuditDescription(auditCampaign) : "";

  return (
    <div>
      <PageHeader
        kicker="Campaigns"
        title="Historical performance"
        subtitle={
          loading
            ? "Loading…"
            : `${campaigns.length} campaign${campaigns.length === 1 ? "" : "s"} · ${stats.active} active · ${stats.sends.toLocaleString()} sends · ${stats.replies.toLocaleString()} replies`
        }
      />

      {error && (
        <div className="mb-4 p-3 rounded-md border-[1.5px] border-rust bg-rust/10 text-rust text-sm">
          {error}
        </div>
      )}

      {loading && campaigns.length === 0 ? (
        <div className="text-sm text-ink-soft py-12 text-center">Loading campaigns…</div>
      ) : campaigns.length === 0 ? (
        <div className="flex flex-col items-center justify-center text-center gap-3 py-16 px-6 rounded-xl border border-dashed border-border bg-muted/30">
          <span className="inline-flex items-center justify-center h-12 w-12 rounded-md bg-amber/15 text-amber border-[1.5px] border-amber">
            <Megaphone className="h-6 w-6" aria-hidden="true" />
          </span>
          <h3 className="text-xl">No campaigns yet</h3>
          <p className="text-sm text-ink-soft max-w-md">
            Campaigns appear here once EmailBison sync runs and the workspace
            has activity. Audit-this-campaign delegates analysis to the Data Analyst.
          </p>
        </div>
      ) : (
        <CampaignsTable campaigns={campaigns} onAudit={handleAudit} />
      )}

      <NewTaskModal
        open={!!auditCampaign}
        onOpenChange={(o) => !o && setAuditCampaign(null)}
        defaultWorkspaceId={id}
        defaultAssigneeAgentId={dataAnalyst?.id}
        defaultTitle={auditTitle}
        defaultDescription={auditDescription}
        onCreated={(taskId) => {
          setAuditCampaign(null);
          // Navigate to task so AE can immediately click Prepare-agent-run
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

  const lines: string[] = [];
  lines.push(`Produce a performance audit for this EmailBison campaign.`);
  lines.push("");
  lines.push(`## Campaign snapshot`);
  lines.push(`- **Name:** ${c.name ?? c.campaignName}`);
  if (c.industry || c.segment || c.angle) {
    lines.push(`- **Targeting:** ${[c.industry, c.segment, c.angle].filter(Boolean).join(" · ")}`);
  }
  lines.push(`- **Status:** ${c.campaignStatus ?? c.status ?? "unknown"}`);
  lines.push(`- **Campaign ID (CharmDB):** \`${c.id}\``);
  if (c.emailbisonCampaignId) {
    lines.push(`- **EmailBison campaign ID:** \`${c.emailbisonCampaignId}\``);
  }
  if (c.workspaceId) {
    lines.push(`- **Workspace ID (OwnRBL):** \`${c.workspaceId}\``);
  }
  lines.push("");
  lines.push(`## Headline metrics`);
  lines.push(`- Sends: **${sends.toLocaleString()}**`);
  lines.push(`- Unique replies: **${replies.toLocaleString()}** (${replyRate}%)`);
  if (c.uniqueOpens != null) {
    lines.push(`- Unique opens: **${c.uniqueOpens.toLocaleString()}**`);
  }
  if (c.bounced != null) {
    lines.push(`- Bounced: **${c.bounced.toLocaleString()}**`);
  }
  lines.push(`- Bounce rate: **${bounce}%**`);
  if (c.unsubscribed != null) {
    lines.push(`- Unsubscribed: **${c.unsubscribed.toLocaleString()}**`);
  }
  if (c.spamComplaints != null) {
    lines.push(`- Spam complaints: **${c.spamComplaints.toLocaleString()}**`);
  }
  if (c.leadsCapacity) {
    lines.push(`- Leads capacity: **${c.leadsCapacity.toLocaleString()}**`);
  }
  lines.push("");
  lines.push(`## What the operator wants`);
  lines.push(`Audit performance vs the workspace's package targets and historical baseline. Flag deliverability concerns (bounce, spam). Surface what worked (best-performing segments, sender names, angles) and what didn't. End with concrete recommendations the AE can act on this week.`);
  lines.push("");
  lines.push(`## Data to pull`);
  lines.push(`Query the OwnRBL schema for: sender-account performance on this campaign, per-domain bounce concentration (ESP-split), reply timing distribution, and any kill triggers that fired during the campaign window.`);
  return lines.join("\n");
}
