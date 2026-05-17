/**
 * Screen: Agents
 * Admin-editable roster. 4 specialized analyst agents (Data Analyst, Researcher,
 * Day AI Reviewer, GitHub Repo Admin). Status + budget are inline-editable;
 * full prompt/adapter config edits available via the modal.
 */
"use client";

import * as React from "react";
import Link from "next/link";
import { toast } from "sonner";
import {
  Bot,
  Activity,
  Pause,
  AlertCircle,
  CircleDashed,
  ChevronRight,
  Settings,
  Database,
  Search,
  Mic,
  GitBranch,
} from "lucide-react";
import { agentApi } from "@/lib/api";
import { PageHeader, CostBudgetMeter } from "@/components/charm";
import type { Agent, AgentRole, AgentStatus } from "@/lib/types";
import { cn } from "@/lib/utils";

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

const ROLE_ICON: Record<AgentRole, React.ComponentType<{ className?: string }>> = {
  data_analyst: Database,
  researcher: Search,
  day_ai_reviewer: Mic,
  github_admin: GitBranch,
  general: Bot,
};

const STATUS_OPTIONS: AgentStatus[] = ["active", "paused", "idle", "error", "terminated"];

export default function AgentsPage() {
  const [agents, setAgents] = React.useState<Agent[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);
  const [savingId, setSavingId] = React.useState<string | null>(null);

  const refetch = React.useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await agentApi.list({ activeOnly: false });
      setAgents(res.items);
    } catch (err) {
      console.error(err);
      setError("Failed to load agents");
    } finally {
      setLoading(false);
    }
  }, []);

  React.useEffect(() => {
    refetch();
  }, [refetch]);

  const handleStatusChange = async (agentId: string, status: AgentStatus) => {
    setSavingId(agentId);
    try {
      await agentApi.update(agentId, { status });
      toast.success(`Status → ${status}`);
      await refetch();
    } catch {
      toast.error("Failed to update status");
    } finally {
      setSavingId(null);
    }
  };

  const handleBudgetSave = async (agentId: string, dollars: number) => {
    setSavingId(agentId);
    try {
      await agentApi.update(agentId, {
        budgetMonthlyCents: Math.max(0, Math.round(dollars * 100)),
      });
      toast.success("Budget updated");
      await refetch();
    } catch {
      toast.error("Failed to update budget");
    } finally {
      setSavingId(null);
    }
  };

  return (
    <div className="px-8 py-8 max-w-7xl mx-auto">
      <PageHeader
        kicker="Paperclip center"
        title="Agents"
        subtitle={`${agents.length} specialized agent${agents.length === 1 ? "" : "s"} on the bench. Admin owns config; AEs assign tasks. Runtime ships when adapters land.`}
        actions={
          <span className="text-xs text-ink-soft">
            Heartbeat runtime: <span className="text-honey font-medium">not yet wired</span>
          </span>
        }
      />

      {error && (
        <div className="mb-4 p-3 rounded-md border-[1.5px] border-rust bg-rust/10 text-rust text-sm">
          {error}
        </div>
      )}

      {loading && agents.length === 0 ? (
        <div className="text-sm text-ink-soft py-12 text-center">Loading agents…</div>
      ) : agents.length === 0 ? (
        <div className="text-sm text-ink-soft text-center py-16 border border-dashed border-border rounded-md">
          No agents configured. Seed agents land via migration 112 — confirm it applied to production.
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
          {agents.map((agent) => (
            <AgentRosterCard
              key={agent.id}
              agent={agent}
              saving={savingId === agent.id}
              onStatusChange={(s) => handleStatusChange(agent.id, s)}
              onBudgetSave={(d) => handleBudgetSave(agent.id, d)}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function AgentRosterCard({
  agent,
  saving,
  onStatusChange,
  onBudgetSave,
}: {
  agent: Agent;
  saving: boolean;
  onStatusChange: (s: AgentStatus) => void;
  onBudgetSave: (dollars: number) => void;
}) {
  const status = STATUS_META[agent.status];
  const RoleIcon = ROLE_ICON[agent.role];
  const [budgetDraft, setBudgetDraft] = React.useState(
    (agent.budgetMonthlyCents / 100).toFixed(0)
  );
  const [budgetDirty, setBudgetDirty] = React.useState(false);

  React.useEffect(() => {
    setBudgetDraft((agent.budgetMonthlyCents / 100).toFixed(0));
    setBudgetDirty(false);
  }, [agent.budgetMonthlyCents]);

  return (
    <article
      className={cn(
        "flex flex-col gap-4 p-5 rounded-lg bg-card text-card-foreground",
        "border-[1.5px] border-border-bold transition-shadow"
      )}
    >
      <header className="flex items-start gap-3">
        <span className="shrink-0 h-10 w-10 rounded-md bg-copper text-cream-light grid place-items-center border-[1.5px] border-ink">
          <RoleIcon className="h-5 w-5" aria-hidden="true" />
        </span>
        <div className="min-w-0 flex-1">
          <h3 className="text-xl truncate">{agent.title}</h3>
          <p className="font-mono text-xs text-ink-soft">@{agent.name}</p>
        </div>
        <Link
          href={`/tasks?assigneeAgentId=${agent.id}`}
          aria-label="View tasks assigned to this agent"
          className="text-ink-soft hover:text-foreground transition-colors"
        >
          <ChevronRight className="h-4 w-4" aria-hidden="true" />
        </Link>
      </header>

      {agent.description && (
        <p className="text-sm text-foreground/80 leading-relaxed">
          {agent.description}
        </p>
      )}

      <div className="flex items-center gap-3 text-sm">
        <span className={cn("inline-flex items-center gap-1.5", status.tone)}>
          <status.Icon className="h-3.5 w-3.5" aria-hidden="true" />
          <span className="font-medium">{status.label}</span>
        </span>
        <span className="text-ink-soft">
          <span className="text-foreground font-medium">{agent.pendingTaskCount}</span> pending
        </span>
        <span className="font-mono text-xs text-ink-soft">{agent.adapterType}</span>
      </div>

      {/* Skills */}
      {agent.skills.length > 0 && (
        <div>
          <p className="text-xs uppercase tracking-wider text-ink-soft mb-1.5">
            Skills · {agent.skills.length}
          </p>
          <div className="flex flex-wrap gap-1">
            {agent.skills.map((s) => (
              <span
                key={s.slug}
                title={s.description}
                className="inline-flex items-center px-1.5 h-5 rounded-sm border border-border text-xs font-mono text-ink-soft hover:border-border-bold hover:text-foreground transition-colors"
              >
                {s.slug}
              </span>
            ))}
          </div>
        </div>
      )}

      <CostBudgetMeter
        spentCents={agent.spentMonthlyCents}
        budgetCents={agent.budgetMonthlyCents}
        size="sm"
      />

      {/* Inline admin controls */}
      <div className="flex items-end gap-2 pt-3 border-t border-border">
        <div className="flex-1 space-y-1">
          <label className="text-xs uppercase tracking-wider text-ink-soft" htmlFor={`status-${agent.id}`}>
            Status
          </label>
          <select
            id={`status-${agent.id}`}
            value={agent.status}
            onChange={(e) => onStatusChange(e.target.value as AgentStatus)}
            disabled={saving}
            className={cn(
              "w-full h-8 rounded-md border-[1.5px] border-border bg-background px-2 text-xs",
              "focus-visible:border-ring focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/40",
              "disabled:opacity-50"
            )}
          >
            {STATUS_OPTIONS.map((s) => (
              <option key={s} value={s}>
                {STATUS_META[s].label}
              </option>
            ))}
          </select>
        </div>

        <div className="flex-1 space-y-1">
          <label className="text-xs uppercase tracking-wider text-ink-soft" htmlFor={`budget-${agent.id}`}>
            Budget ($/mo)
          </label>
          <input
            id={`budget-${agent.id}`}
            type="number"
            inputMode="numeric"
            min={0}
            value={budgetDraft}
            onChange={(e) => {
              setBudgetDraft(e.target.value);
              setBudgetDirty(true);
            }}
            disabled={saving}
            className={cn(
              "w-full h-8 rounded-md border-[1.5px] border-border bg-background px-2 text-xs font-mono",
              "focus-visible:border-ring focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/40",
              "disabled:opacity-50"
            )}
          />
        </div>

        <button
          type="button"
          disabled={!budgetDirty || saving}
          onClick={() => {
            const n = parseFloat(budgetDraft);
            if (!Number.isFinite(n)) {
              toast.error("Invalid budget");
              return;
            }
            onBudgetSave(n);
          }}
          className={cn(
            "h-8 px-3 rounded-md text-xs font-medium",
            "bg-amber text-ink border-[1.5px] border-border-bold hover:shadow-flat-sm transition-shadow",
            "disabled:opacity-50 disabled:cursor-not-allowed"
          )}
        >
          Save
        </button>
      </div>

      {agent.lastError && (
        <p className="text-xs text-rust">
          <AlertCircle className="inline h-3 w-3 mr-1" aria-hidden="true" />
          {agent.lastError}
        </p>
      )}
    </article>
  );
}
