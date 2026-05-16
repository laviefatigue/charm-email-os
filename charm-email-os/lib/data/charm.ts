/**
 * Charm redesign data layer.
 *
 * Live data: workspaces (clients), domain/inbox counts, sync state, last activity
 *   → fetched from the real Charm API at NEXT_PUBLIC_API_URL.
 *
 * Mocked data: analyst agents, recommendations, context-sync, structured events
 *   → backend hasn't shipped yet (see docs/architecture/agent-runtime.md and
 *     docs/architecture/client-context-sync.md). Re-exported from lib/mock/charm.
 *
 * Buttons / approve / reject are intentionally inert in Phase 0 — UX is locked
 * before backend builds against it.
 */

import type {
  WorkspaceCardData,
  IntegrationSummary,
  AttentionState,
} from "@/components/charm";
import {
  getAgents as getMockAgents,
  getRecommendations as getMockRecommendations,
  getEvents as getMockEvents,
  MOCK_WORKSPACES,
} from "@/lib/mock/charm";

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL || "https://api.wizardgrimoire.cloud";

// Re-export mocked data unchanged
export {
  getMockAgents as getAgents,
  getMockRecommendations as getRecommendations,
  getMockEvents as getEvents,
};

// ---------------------------------------------------------------------------
// Real client (workspace) fetch
// ---------------------------------------------------------------------------

interface ApiClient {
  id: string;
  name: string;
  workspace_id?: string | null;
  workspace_name?: string | null;
  domain_pattern?: string | null;
  inbox_count: number;
  connected_inbox_count: number;
  domain_count: number;
  campaign_count: number;
  sync_enabled: boolean;
  package_name?: string | null;
  package_inbox_target?: number | null;
  created_at?: string;
  updated_at?: string;
}

interface ApiClientList {
  items: ApiClient[];
  total: number;
  page: number;
  page_size: number;
}

const FETCH_OPTS: RequestInit = {
  // Tiny revalidation window — Phase 0 UX preview, not production
  next: { revalidate: 30 } as RequestInit["next"],
};

async function fetchClients(): Promise<ApiClient[]> {
  try {
    const res = await fetch(`${API_BASE}/api/clients?page_size=100`, FETCH_OPTS);
    if (!res.ok) {
      console.error(`[charm-data] /api/clients returned ${res.status}`);
      return [];
    }
    const data = (await res.json()) as ApiClientList;
    return data.items ?? [];
  } catch (err) {
    console.error("[charm-data] failed to fetch clients", err);
    return [];
  }
}

/**
 * Derive an attention state from real data signals.
 * Heuristic — will be replaced by an agent-derived health score in Phase 2.
 */
function deriveAttention(c: ApiClient): AttentionState {
  if (c.inbox_count === 0) return "healthy"; // intentional dormant
  const connectedRatio = c.connected_inbox_count / Math.max(1, c.inbox_count);
  if (!c.sync_enabled) return "amber";
  if (connectedRatio < 0.5) return "red";
  if (connectedRatio < 0.85) return "amber";
  return "healthy";
}

function deriveIntegrations(c: ApiClient): IntegrationSummary[] {
  return [
    {
      name: "EmailBison",
      status: c.sync_enabled
        ? c.inbox_count > 0
          ? "connected"
          : "disconnected"
        : "disconnected",
    },
    { name: "day.ai", status: "disconnected" }, // not yet wired
  ];
}

/**
 * Map a real API client into the WorkspaceCardData shape consumed by the UI.
 * Live: name, slug, inbox counts (mapped onto domainsLive/Total with metricLabel="Inboxes"),
 *       integrations (EmailBison), attentionState.
 * Mocked (Phase 2 backend): agentsActive, pendingRecommendations, contextSync,
 *       monthlySpendCents, lastEventAt, eodReapplyEnabled.
 */
function toWorkspaceCardData(c: ApiClient): WorkspaceCardData {
  // Stable mock overlay derived from id so per-workspace mock fields don't shuffle on every refresh
  const overlay = mockOverlayForId(c.id);

  return {
    id: c.id,
    name: c.name,
    slug: c.domain_pattern ?? c.workspace_name ?? c.id.slice(0, 8),
    // domainsLive / domainsTotal are repurposed for inbox connection counts —
    // WorkspaceCard renders this with metricLabel="Inboxes" so the semantics fit.
    domainsLive: c.connected_inbox_count,
    domainsTotal: c.inbox_count,
    lastEventAt: c.updated_at ? new Date(c.updated_at) : null,
    lastEventType: "Last sync",
    eodReapplyEnabled: c.sync_enabled,
    monthlySpendCents: overlay.monthlySpendCents,
    agentsActive: overlay.agentsActive,
    pendingRecommendations: overlay.pendingRecommendations,
    contextSync: overlay.contextSync,
    integrations: deriveIntegrations(c),
    attentionState: deriveAttention(c),
  };
}

/**
 * Stable mock overlay seeded from client UUID. Deterministic per id so values
 * don't shuffle across page renders; entirely replaced by real backend in Phase 2.
 */
function mockOverlayForId(id: string) {
  // Hash the id to a few stable numbers
  let h = 0;
  for (let i = 0; i < id.length; i++) h = (h * 31 + id.charCodeAt(i)) >>> 0;
  const r = (n: number) => (h >> (n * 4)) & 0xff;
  return {
    monthlySpendCents: 0, // hidden when backend agent budgets aren't real
    agentsActive: 0, // no agents shipped yet — surface as "0 agents" honestly
    pendingRecommendations: 0, // no recs yet
    contextSync: {
      status: "never_synced" as const,
      lastSyncedAt: null,
    },
    _seed: r(0), // available for future variation
  };
}

// ---------------------------------------------------------------------------
// Public server-side data getters
// ---------------------------------------------------------------------------

export async function getWorkspaces(): Promise<WorkspaceCardData[]> {
  const clients = await fetchClients();
  if (clients.length === 0) {
    // Fall back to mock if the API is unreachable so the UI still demos
    return MOCK_WORKSPACES;
  }
  return clients.map(toWorkspaceCardData);
}

export async function getWorkspace(
  id: string
): Promise<WorkspaceCardData | undefined> {
  // Cheap path: fetch the list and pick. The API also has /api/clients/{id}
  // but the list endpoint already cached at the edge via revalidate=30.
  const workspaces = await getWorkspaces();
  return workspaces.find((w) => w.id === id);
}

export async function getGlobalSummary(): Promise<{
  workspaceCount: number;
  totalPendingRecommendations: number;
  totalAgentsActive: number;
  totalLiveDomains: number;
  needsAttention: number;
}> {
  const workspaces = await getWorkspaces();
  return {
    workspaceCount: workspaces.length,
    totalPendingRecommendations: workspaces.reduce(
      (sum, w) => sum + w.pendingRecommendations,
      0
    ),
    totalAgentsActive: workspaces.reduce((sum, w) => sum + w.agentsActive, 0),
    totalLiveDomains: workspaces.reduce((sum, w) => sum + w.domainsLive, 0),
    needsAttention: workspaces.filter((w) => w.attentionState !== "healthy")
      .length,
  };
}
