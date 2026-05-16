/**
 * Screen: Workspace Agents
 * The analyst-agent roster for this workspace. Each card shows status, last run,
 * monthly cost utilization, and pending recommendations.
 *
 * Design System: [[design-system/index]]
 * Components: [[design-system/components/agent-card]]
 */
import * as React from "react";
import { notFound } from "next/navigation";
import { Bot, Plus } from "lucide-react";
import { AgentCard, PageHeader } from "@/components/charm";
import { getWorkspace, getAgents } from "@/lib/mock/charm";

export default async function WorkspaceAgentsPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const workspace = getWorkspace(id);
  if (!workspace) notFound();

  const agents = getAgents(id);
  const activeCount = agents.filter((a) => a.status === "active" || a.status === "running").length;
  const totalSpend = agents.reduce((sum, a) => sum + a.spentMonthlyCents, 0);
  const totalBudget = agents.reduce((sum, a) => sum + a.budgetMonthlyCents, 0);

  return (
    <div>
      <PageHeader
        kicker="Roster"
        title="Agents"
        subtitle={
          agents.length === 0
            ? "No agents configured for this workspace yet."
            : `${agents.length} configured · ${activeCount} active · $${(totalSpend / 100).toFixed(2)} / $${(totalBudget / 100).toFixed(0)} this month`
        }
        actions={
          <button
            type="button"
            className="inline-flex items-center gap-1.5 h-9 px-4 rounded-md text-sm font-medium bg-transparent text-ink border-[1.5px] border-border-bold hover:bg-muted transition-colors"
            onClick={() => console.warn("configure new agent — not yet implemented")}
          >
            <Plus className="h-4 w-4" aria-hidden="true" />
            Configure agent
          </button>
        }
      />

      {agents.length === 0 ? (
        <div className="flex flex-col items-center justify-center text-center gap-3 py-16 px-6 rounded-xl border border-dashed border-border bg-muted/30">
          <span className="inline-flex items-center justify-center h-12 w-12 rounded-md bg-copper/15 text-copper border-[1.5px] border-copper">
            <Bot className="h-6 w-6" aria-hidden="true" />
          </span>
          <h3 className="text-xl">No agents configured</h3>
          <p className="text-sm text-ink-soft max-w-md">
            Add analyst agents (Performance, Health, Domain Insights, Account
            Manager) to surface recommendations from this workspace's data.
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
          {agents.map((agent) => (
            <AgentCard
              key={agent.id}
              agent={agent}
              onOpen={(id) => console.warn("open agent detail", id)}
            />
          ))}
        </div>
      )}
    </div>
  );
}
