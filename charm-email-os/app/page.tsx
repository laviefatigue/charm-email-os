/**
 * Screen: Home
 * AE daily landing. Light variant (Option A, 2026-05-16):
 *   • Workspace cards (the heart — pick where to work today)
 *   • Pending decisions panel — cross-workspace request_confirmation interactions
 *   • Recent activity panel — recently-updated tasks across workspaces
 *
 * Workspace cards are server-rendered (real data, SSR + 30s revalidate).
 * The two panels client-fetch (small, low-priority).
 */
import * as React from "react";
import { WorkspaceCard, PageHeader } from "@/components/charm";
import { getWorkspaces, getGlobalSummary } from "@/lib/data/charm";
import { HomePanels } from "./home-panels";

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
        kicker="Daily landing"
        title={`${greeting}, Elliott.`}
        subtitle={`${summary.workspaceCount} workspaces · ${summary.totalLiveDomains} connected inboxes${
          summary.needsAttention > 0 ? ` · ${summary.needsAttention} need attention` : ""
        }`}
      />

      <section
        aria-label="Workspaces"
        className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6 mb-10"
      >
        {workspaces.map((workspace) => (
          <WorkspaceCard
            key={workspace.id}
            workspace={workspace}
            href={`/workspaces/${workspace.id}`}
          />
        ))}
      </section>

      <HomePanels />
    </div>
  );
}
