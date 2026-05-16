/**
 * Mock data for the Charm Village redesign (Phase 0 — UX locked before backend).
 * Realistic shapes that mirror the eventual data model from:
 *   - docs/architecture/agent-runtime.md  (agents, agent_runs, issue_interactions, cost_events)
 *   - docs/architecture/client-context-sync.md  (workspace_context_repos, workspace_context_syncs)
 *
 * Replace each export with a server-side data fetch once the backend lands.
 */

import type {
  WorkspaceCardData,
  AgentCardData,
  RecommendationCardData,
  ActivityEvent,
} from "@/components/charm";

const NOW = new Date();
const minAgo = (n: number) => new Date(NOW.getTime() - n * 60_000);
const hAgo = (n: number) => new Date(NOW.getTime() - n * 3_600_000);
const dAgo = (n: number) => new Date(NOW.getTime() - n * 86_400_000);

// ---------------------------------------------------------------------------
// Workspaces
// ---------------------------------------------------------------------------

export const MOCK_WORKSPACES: WorkspaceCardData[] = [
  {
    id: "ws-hypertide",
    name: "Hypertide",
    slug: "ws-hypertide",
    domainsLive: 87,
    domainsTotal: 142,
    lastEventAt: minAgo(12),
    lastEventType: "warmup_disable fired",
    eodReapplyEnabled: true,
    monthlySpendCents: 12_400,
    agentsActive: 3,
    pendingRecommendations: 2,
    contextSync: { status: "ok", lastSyncedAt: minAgo(47) },
    integrations: [
      { name: "day.ai", status: "connected" },
      { name: "EmailBison", status: "connected" },
      { name: "Hypertide", status: "connected" },
    ],
    attentionState: "amber",
  },
  {
    id: "ws-hubspot-growth-spui",
    name: "Hubspot Growth · SPUI",
    slug: "ws-hubspot-growth-spui",
    domainsLive: 412,
    domainsTotal: 487,
    lastEventAt: minAgo(4),
    lastEventType: "EOD reapply completed",
    eodReapplyEnabled: true,
    monthlySpendCents: 47_200,
    agentsActive: 4,
    pendingRecommendations: 0,
    contextSync: { status: "ok", lastSyncedAt: minAgo(23) },
    integrations: [
      { name: "day.ai", status: "connected" },
      { name: "EmailBison", status: "connected" },
      { name: "HubSpot", status: "connected" },
    ],
    attentionState: "healthy",
  },
  {
    id: "ws-sammy",
    name: "Sammy",
    slug: "ws-sammy",
    domainsLive: 0,
    domainsTotal: 28,
    lastEventAt: dAgo(14),
    lastEventType: "infra_moved_off_eb",
    eodReapplyEnabled: false,
    monthlySpendCents: 0,
    agentsActive: 1,
    pendingRecommendations: 0,
    contextSync: { status: "never_synced", lastSyncedAt: null },
    integrations: [
      { name: "day.ai", status: "disconnected" },
      { name: "EmailBison", status: "disconnected" },
    ],
    attentionState: "healthy",
  },
  {
    id: "ws-acme-ramp",
    name: "Acme · Ramp",
    slug: "ws-acme-ramp",
    domainsLive: 23,
    domainsTotal: 64,
    lastEventAt: hAgo(2),
    lastEventType: "incubation_promoted",
    eodReapplyEnabled: true,
    monthlySpendCents: 6_300,
    agentsActive: 2,
    pendingRecommendations: 1,
    contextSync: { status: "drift_detected", lastSyncedAt: hAgo(8) },
    integrations: [
      { name: "day.ai", status: "drift" },
      { name: "EmailBison", status: "connected" },
    ],
    attentionState: "amber",
  },
  {
    id: "ws-northwind",
    name: "Northwind Logistics",
    slug: "ws-northwind",
    domainsLive: 156,
    domainsTotal: 198,
    lastEventAt: minAgo(38),
    lastEventType: "hypertide_audit_completed",
    eodReapplyEnabled: true,
    monthlySpendCents: 18_900,
    agentsActive: 3,
    pendingRecommendations: 4,
    contextSync: { status: "auth_failed", lastSyncedAt: dAgo(2) },
    integrations: [
      { name: "day.ai", status: "connected" },
      { name: "EmailBison", status: "connected" },
      { name: "Hypertide", status: "connected" },
    ],
    attentionState: "red",
  },
];

export function getWorkspace(id: string): WorkspaceCardData | undefined {
  return MOCK_WORKSPACES.find((w) => w.id === id);
}

// ---------------------------------------------------------------------------
// Agents (per workspace)
// ---------------------------------------------------------------------------

const AGENTS_BY_WORKSPACE: Record<string, AgentCardData[]> = {
  "ws-hypertide": [
    {
      id: "agent-hypertide-perf",
      name: "Performance Analyst",
      description: "Burn velocity, kill-cascade forensics, deliverability trends",
      status: "active",
      adapterType: "claude_local",
      lastRunAt: hAgo(2),
      spentMonthlyCents: 1_240,
      budgetMonthlyCents: 5_000,
      pendingRecommendations: 1,
    },
    {
      id: "agent-hypertide-health",
      name: "Infrastructure Health Monitor",
      description: "Drift detection, warmup audit, hypertide reconcile",
      status: "running",
      adapterType: "claude_local",
      lastRunAt: minAgo(8),
      spentMonthlyCents: 890,
      budgetMonthlyCents: 3_000,
      pendingRecommendations: 1,
    },
    {
      id: "agent-hypertide-insights",
      name: "Domain Insights Advisor",
      description: "Burn forecast, rotation strategy, registrar optimization",
      status: "idle",
      adapterType: "claude_local",
      lastRunAt: dAgo(2),
      spentMonthlyCents: 320,
      budgetMonthlyCents: 2_000,
      pendingRecommendations: 0,
    },
  ],
  "ws-hubspot-growth-spui": [
    {
      id: "agent-spui-perf",
      name: "Performance Analyst",
      description: "Burn velocity, kill-cascade forensics, deliverability trends",
      status: "active",
      adapterType: "claude_local",
      lastRunAt: hAgo(1),
      spentMonthlyCents: 4_200,
      budgetMonthlyCents: 10_000,
      pendingRecommendations: 0,
    },
    {
      id: "agent-spui-health",
      name: "Infrastructure Health Monitor",
      status: "active",
      adapterType: "claude_local",
      lastRunAt: minAgo(15),
      spentMonthlyCents: 3_100,
      budgetMonthlyCents: 8_000,
      pendingRecommendations: 0,
    },
    {
      id: "agent-spui-insights",
      name: "Domain Insights Advisor",
      status: "active",
      adapterType: "claude_local",
      lastRunAt: hAgo(6),
      spentMonthlyCents: 1_800,
      budgetMonthlyCents: 4_000,
      pendingRecommendations: 0,
    },
    {
      id: "agent-spui-manager",
      name: "Account Manager",
      description: "Per-client synthesis, capacity planning, day.ai integration",
      status: "active",
      adapterType: "claude_local",
      lastRunAt: hAgo(4),
      spentMonthlyCents: 980,
      budgetMonthlyCents: 3_000,
      pendingRecommendations: 0,
    },
  ],
  "ws-sammy": [
    {
      id: "agent-sammy-perf",
      name: "Performance Analyst",
      description: "Paused — Sammy off EmailBison, no signal to analyze",
      status: "paused",
      adapterType: "claude_local",
      lastRunAt: dAgo(14),
      spentMonthlyCents: 0,
      budgetMonthlyCents: 1_000,
      pendingRecommendations: 0,
    },
  ],
  "ws-acme-ramp": [
    {
      id: "agent-acme-perf",
      name: "Performance Analyst",
      status: "active",
      adapterType: "claude_local",
      lastRunAt: hAgo(3),
      spentMonthlyCents: 740,
      budgetMonthlyCents: 3_000,
      pendingRecommendations: 0,
    },
    {
      id: "agent-acme-health",
      name: "Infrastructure Health Monitor",
      description: "Detected drift in day.ai integration — pending operator nod",
      status: "active",
      adapterType: "claude_local",
      lastRunAt: minAgo(22),
      spentMonthlyCents: 1_080,
      budgetMonthlyCents: 2_500,
      pendingRecommendations: 1,
    },
  ],
  "ws-northwind": [
    {
      id: "agent-northwind-perf",
      name: "Performance Analyst",
      status: "active",
      adapterType: "claude_local",
      lastRunAt: hAgo(1),
      spentMonthlyCents: 2_800,
      budgetMonthlyCents: 5_000,
      pendingRecommendations: 2,
    },
    {
      id: "agent-northwind-health",
      name: "Infrastructure Health Monitor",
      description: "Context sync auth-failed — operator must rotate GitHub PAT",
      status: "error",
      adapterType: "claude_local",
      lastRunAt: dAgo(2),
      spentMonthlyCents: 410,
      budgetMonthlyCents: 4_000,
      pendingRecommendations: 1,
    },
    {
      id: "agent-northwind-insights",
      name: "Domain Insights Advisor",
      status: "active",
      adapterType: "claude_local",
      lastRunAt: hAgo(12),
      spentMonthlyCents: 1_650,
      budgetMonthlyCents: 3_000,
      pendingRecommendations: 1,
    },
  ],
};

export function getAgents(workspaceId: string): AgentCardData[] {
  return AGENTS_BY_WORKSPACE[workspaceId] ?? [];
}

// ---------------------------------------------------------------------------
// Recommendations (per workspace)
// ---------------------------------------------------------------------------

const RECOMMENDATIONS_BY_WORKSPACE: Record<string, RecommendationCardData[]> = {
  "ws-hypertide": [
    {
      id: "rec-hypertide-rotation",
      agentName: "Performance Analyst",
      prompt: "Rotate these 5 domains before EOD?",
      summary:
        "Burn rate +18% MoM, kill cascade modeled to trigger in 4–6d. Proposed rotation: vapor-pulse.email, echo-pearl.email, drift-anchor.email, mist-flare.email, silver-vine.email. Replacement slate from incubation queue is ready (8 domains scored, 5 above quality threshold).",
      detailLabel: "View proposed rotation slate",
      citedContext: [
        {
          path: "decisions/DECISION_burn-threshold.md",
          commitSha: "a3b7c9d",
          relevance: "policy gate",
        },
        {
          path: "feedback/feedback_aggressive-rotation.md",
          commitSha: "a3b7c9d",
          relevance: "client preference",
        },
        {
          path: "notes/transcripts/2026-05-08-weekly-sync.md",
          commitSha: "a3b7c9d",
          relevance: "burn-rate concern raised",
        },
      ],
      createdAt: minAgo(32),
      rejectRequiresReason: true,
    },
    {
      id: "rec-hypertide-drift",
      agentName: "Infrastructure Health Monitor",
      prompt: "Reconcile 12 inbox warmup drift entries?",
      summary:
        "12 inboxes show divergence between EmailBison warmup status and the CharmDB. Most likely cause: a sync gap during the 2026-05-12 EB outage. Proposed: trigger reconcile via tag op worker. Low risk — read-only divergence, no policy change.",
      citedContext: [
        {
          path: "docs/incidents/2026-05-12-eb-outage.md",
          commitSha: "a3b7c9d",
          relevance: "root cause",
        },
      ],
      createdAt: minAgo(8),
    },
  ],
  "ws-hubspot-growth-spui": [],
  "ws-sammy": [],
  "ws-acme-ramp": [
    {
      id: "rec-acme-day-ai",
      agentName: "Infrastructure Health Monitor",
      prompt: "Re-authenticate day.ai integration?",
      summary:
        "day.ai integration entered drift state 8h ago (token returned 401 on last 3 fetches). Last successful sync was 2026-05-14 22:14. No transcripts pulled in 14h. Proposed: trigger re-auth flow via the integrations page; operator must approve OAuth scope.",
      citedContext: [
        {
          path: "client.md",
          commitSha: "f12e8a4",
          relevance: "day.ai account ID",
        },
      ],
      createdAt: hAgo(6),
      detailLabel: "Open day.ai re-auth flow",
    },
  ],
  "ws-northwind": [
    {
      id: "rec-northwind-pat-rotate",
      agentName: "Infrastructure Health Monitor",
      prompt: "Rotate the GitHub App installation for Northwind?",
      summary:
        "Context-sync auth has failed for 48h — likely the installation was revoked or the App's private key rotated. Operator action required: visit GitHub App settings, regenerate installation token, update the secret. Until rotated, no AE notes or decisions will flow into agent context — recommendations may be stale.",
      citedContext: [
        {
          path: "workspace_context_repos.installation_id",
          commitSha: "(db)",
          relevance: "current installation ID",
        },
      ],
      createdAt: hAgo(24),
      rejectRequiresReason: true,
      detailLabel: "Open GitHub App settings",
    },
    {
      id: "rec-northwind-rotate",
      agentName: "Performance Analyst",
      prompt: "Pre-emptive rotation of 8 domains?",
      summary:
        "Burn rate +27% MoM. Domain Insights Advisor flagged 8 candidates for pre-emptive rotation based on bounce trend slope (>0.4%/day for last 5d). Caveat: context is stale 48h due to auth failure — strongly recommend resolving context-sync first.",
      citedContext: [],
      createdAt: hAgo(2),
      rejectRequiresReason: true,
      detailLabel: "View 8 candidate domains",
    },
    {
      id: "rec-northwind-drift",
      agentName: "Performance Analyst",
      prompt: "Investigate kill cascade on subdomain group ‘nw-q2-eu’?",
      summary:
        "47 inboxes across 8 domains in the nw-q2-eu subgroup killed within 6h on 2026-05-13. Pattern matches prior MSFT throttle event. Proposed: deep-dive analysis with deliverability-trends skill (est. 8K tokens, $0.12).",
      citedContext: [
        {
          path: "decisions/DECISION_msft-deprecation.md",
          commitSha: "(stale)",
          relevance: "MSFT policy",
        },
      ],
      createdAt: hAgo(8),
    },
    {
      id: "rec-northwind-insights",
      agentName: "Domain Insights Advisor",
      prompt: "Switch primary registrar from Dynadot to Namecheap for new buys?",
      summary:
        "Dynadot rate-limit hits on bulk purchase have grown 3× in the last 30d. Northwind's Q3 ramp will need ~120 new domains/week. Namecheap supports higher burst. Tradeoff: $0.50/domain higher cost. Recommended only if Q3 ramp is approved.",
      citedContext: [
        {
          path: "decisions/DECISION_registrar-dynadot-only.md",
          commitSha: "(stale)",
          relevance: "current registrar policy",
        },
      ],
      createdAt: dAgo(1),
      rejectRequiresReason: true,
    },
  ],
};

export function getRecommendations(workspaceId: string): RecommendationCardData[] {
  return RECOMMENDATIONS_BY_WORKSPACE[workspaceId] ?? [];
}

// ---------------------------------------------------------------------------
// Activity events (per workspace, interleaved)
// ---------------------------------------------------------------------------

const EVENTS_BY_WORKSPACE: Record<string, ActivityEvent[]> = {
  "ws-hypertide": [
    {
      id: "e-h-1",
      timestamp: minAgo(8),
      type: "agent-run",
      actor: "Infrastructure Health Monitor",
      action: "completed run",
      detail: "1 recommendation posted · 8.2K tokens · $0.04",
      status: "ok",
    },
    {
      id: "e-h-2",
      timestamp: minAgo(12),
      type: "daemon-event",
      actor: "Plan F",
      action: "warmup_disable fired",
      detail: "47 inboxes affected · domain vapor-pulse.email",
      status: "ok",
    },
    {
      id: "e-h-3",
      timestamp: minAgo(32),
      type: "agent-run",
      actor: "Performance Analyst",
      action: "posted recommendation",
      detail: "Rotate 5 domains before EOD · 14K tokens · $0.07",
      status: "ok",
    },
    {
      id: "e-h-4",
      timestamp: minAgo(47),
      type: "context-sync",
      actor: "context-sync",
      action: "pulled main",
      detail: "+2 docs, +1 deleted, +7 links · commit a3b7c9d ← f12e8a4",
      status: "ok",
    },
    {
      id: "e-h-5",
      timestamp: hAgo(2),
      type: "daemon-event",
      actor: "EOD reapply",
      action: "completed for SPUI · 101",
      detail: "87/87 attached · 0 verification failures",
      status: "ok",
    },
    {
      id: "e-h-6",
      timestamp: hAgo(3),
      type: "daemon-event",
      actor: "Hypertide audit",
      action: "completed",
      detail: "3 ht_cancelled_eb_active, 0 db_only_unlinked",
      status: "ok",
    },
    {
      id: "e-h-7",
      timestamp: hAgo(6),
      type: "context-sync",
      actor: "context-sync",
      action: "pulled main",
      detail: "no changes",
      status: "no_changes",
    },
    {
      id: "e-h-8",
      timestamp: hAgo(8),
      type: "daemon-event",
      actor: "Tag op worker",
      action: "drained queue",
      detail: "238 ops processed in 47s",
      status: "ok",
    },
    {
      id: "e-h-9",
      timestamp: hAgo(12),
      type: "daemon-event",
      actor: "Plan F",
      action: "warmup_disable fired",
      detail: "12 inboxes affected · domain echo-pearl.email",
      status: "ok",
    },
    {
      id: "e-h-10",
      timestamp: dAgo(1),
      type: "agent-run",
      actor: "Domain Insights Advisor",
      action: "weekly forecast",
      detail: "no recommendations · burn trajectory within bounds · 22K tokens · $0.11",
      status: "ok",
    },
  ],
  "ws-hubspot-growth-spui": [
    {
      id: "e-s-1",
      timestamp: minAgo(4),
      type: "daemon-event",
      actor: "EOD reapply",
      action: "completed for 14 campaigns",
      detail: "412/412 attached · 0 failures",
      status: "ok",
    },
    {
      id: "e-s-2",
      timestamp: minAgo(15),
      type: "agent-run",
      actor: "Infrastructure Health Monitor",
      action: "completed run",
      detail: "no drift · 4.1K tokens · $0.02",
      status: "ok",
    },
    {
      id: "e-s-3",
      timestamp: minAgo(23),
      type: "context-sync",
      actor: "context-sync",
      action: "pulled main",
      detail: "+1 doc · commit b9f4ec2 ← b9f4eb1",
      status: "ok",
    },
  ],
  "ws-sammy": [
    {
      id: "e-sa-1",
      timestamp: dAgo(14),
      type: "daemon-event",
      actor: "Plan A firewall",
      action: "infrastructure off-boarded",
      detail: "Sammy moved off EmailBison · intentional",
      status: "ok",
    },
  ],
  "ws-acme-ramp": [
    {
      id: "e-a-1",
      timestamp: minAgo(22),
      type: "agent-run",
      actor: "Infrastructure Health Monitor",
      action: "detected day.ai drift",
      detail: "401 on token refresh · 3 consecutive fetches failed",
      status: "ok",
    },
    {
      id: "e-a-2",
      timestamp: hAgo(2),
      type: "daemon-event",
      actor: "Plan A firewall",
      action: "incubation_promoted",
      detail: "3 domains promoted to reserve",
      status: "ok",
    },
  ],
  "ws-northwind": [
    {
      id: "e-n-1",
      timestamp: minAgo(38),
      type: "daemon-event",
      actor: "Hypertide audit",
      action: "completed",
      detail: "1 ht_cancelled_eb_active, 0 db_only_unlinked",
      status: "ok",
    },
    {
      id: "e-n-2",
      timestamp: hAgo(1),
      type: "agent-run",
      actor: "Performance Analyst",
      action: "completed run",
      detail: "2 recommendations posted · 24K tokens · $0.14",
      status: "ok",
    },
    {
      id: "e-n-3",
      timestamp: hAgo(2),
      type: "agent-run",
      actor: "Performance Analyst",
      action: "kill cascade flagged on nw-q2-eu",
      detail: "47 inboxes in 6h · 8 domains affected",
      status: "ok",
    },
    {
      id: "e-n-4",
      timestamp: hAgo(24),
      type: "agent-run",
      actor: "Infrastructure Health Monitor",
      action: "posted urgent recommendation",
      detail: "context-sync auth failed · operator action required",
      status: "ok",
    },
    {
      id: "e-n-5",
      timestamp: hAgo(48),
      type: "context-sync",
      actor: "context-sync",
      action: "auth failed",
      detail: "GitHub App installation revoked or PAT expired",
      status: "failed",
    },
  ],
};

export function getEvents(workspaceId: string): ActivityEvent[] {
  return EVENTS_BY_WORKSPACE[workspaceId] ?? [];
}

// ---------------------------------------------------------------------------
// Aggregations for the home / global views
// ---------------------------------------------------------------------------

export function getGlobalSummary() {
  return {
    workspaceCount: MOCK_WORKSPACES.length,
    totalPendingRecommendations: MOCK_WORKSPACES.reduce(
      (sum, w) => sum + w.pendingRecommendations,
      0
    ),
    totalAgentsActive: MOCK_WORKSPACES.reduce((sum, w) => sum + w.agentsActive, 0),
    totalLiveDomains: MOCK_WORKSPACES.reduce((sum, w) => sum + w.domainsLive, 0),
    needsAttention: MOCK_WORKSPACES.filter((w) => w.attentionState !== "healthy").length,
  };
}
