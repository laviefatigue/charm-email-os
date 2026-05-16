/**
 * Screen: Home (workspace card grid) — LIVE data + Phase 0 mock overlay
 *
 * Real-time from Charm API: workspaces (clients), inbox connection counts,
 * sync state, last-update timestamp, attention heuristic (connected ratio +
 * sync_enabled).
 *
 * Mocked (backend Phase 2): analyst agents, pending recommendations, context
 * freshness, monthly spend. See docs/architecture/agent-runtime.md.
 *
 * Design System: [[design-system/index]]
 * Components: [[design-system/components/workspace-card]] · [[design-system/components/page-header]]
 */
import * as React from "react";
import Link from "next/link";
import { ChevronRight, Database } from "lucide-react";
import { WorkspaceCard, PageHeader } from "@/components/charm";
import { getWorkspaces, getGlobalSummary } from "@/lib/data/charm";

export const revalidate = 30;

function greetByHour(d: Date): string {
  const h = d.getHours();
  if (h < 5) return "Late night";
  if (h < 12) return "Morning";
  if (h < 17) return "Afternoon";
  if (h < 21) return "Evening";
  return "Evening";
}

export default async function HomePage() {
  const [workspaces, summary] = await Promise.all([
    getWorkspaces(),
    getGlobalSummary(),
  ]);
  const greeting = greetByHour(new Date());

  return (
    <div className="px-8 py-8 max-w-7xl w-full mx-auto">
      <PageHeader
        kicker="Charm operator"
        title={`${greeting}, Elliott.`}
        subtitle={
          summary.totalPendingRecommendations > 0
            ? `${summary.totalPendingRecommendations} pending recommendation${
                summary.totalPendingRecommendations === 1 ? "" : "s"
              } across ${summary.needsAttention} workspace${
                summary.needsAttention === 1 ? "" : "s"
              } need your nod. ${summary.totalAgentsActive} agents on duty.`
            : `${summary.workspaceCount} workspaces · ${summary.totalLiveDomains} connected inboxes · ${summary.needsAttention} need attention.`
        }
        actions={
          summary.totalPendingRecommendations > 0 ? (
            <Link
              href="/recommendations"
              className="inline-flex items-center gap-1.5 h-9 px-4 rounded-md text-sm font-medium bg-amber text-ink border-[1.5px] border-ink hover:shadow-flat-sm focus-visible:shadow-flat-sm transition-shadow"
            >
              Open mailbox
              <ChevronRight className="h-4 w-4" aria-hidden="true" />
            </Link>
          ) : undefined
        }
      />

      <DataProvenanceBanner />

      <section
        aria-label="Workspaces"
        className="mt-6 grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6"
      >
        {workspaces.map((workspace) => (
          <WorkspaceCard
            key={workspace.id}
            workspace={workspace}
            href={`/workspaces/${workspace.id}`}
          />
        ))}
      </section>
    </div>
  );
}

function DataProvenanceBanner() {
  return (
    <div className="mt-2 mb-2 flex items-start gap-3 p-3 rounded-md border border-border bg-muted/40 text-xs">
      <span className="inline-flex items-center justify-center h-6 w-6 rounded-sm bg-sky/15 text-sky border border-sky shrink-0">
        <Database className="h-3.5 w-3.5" aria-hidden="true" />
      </span>
      <div className="space-y-0.5 text-ink-soft">
        <p>
          <strong className="text-foreground">Live data</strong> from the Charm
          API: workspaces, inbox counts, sync state, last activity.
        </p>
        <p>
          <strong className="text-foreground">Mocked (Phase 0):</strong>{" "}
          analyst agents, recommendations, context freshness, monthly spend —
          backend lands in agent-runtime Phase 2. Buttons inert.
        </p>
      </div>
    </div>
  );
}
