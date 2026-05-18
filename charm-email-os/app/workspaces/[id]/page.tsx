/**
 * Screen: Workspace Overview
 * AE landing for a workspace. Real production data where available:
 *   • Stat strip from /api/health/overview/{client_id} (live)
 *   • Active campaigns from /api/campaigns?client_id={id} (live)
 *   • Active projects + tasks from /api/projects + /api/tasks (live; may be
 *     empty until charm-api ships migrations 112–118)
 */
"use client";

import * as React from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { formatDistanceToNowStrict } from "date-fns";
import {
  ChevronRight,
  FolderKanban,
  ListTodo,
  Megaphone,
  AlertTriangle,
  CheckCircle2,
  Mail,
  Globe,
} from "lucide-react";
import { ProjectCard, TaskCard } from "@/components/charm";
import {
  projectApi,
  taskApi,
  campaignApi,
  healthApi,
} from "@/lib/api";
import type {
  Campaign,
  HealthOverview,
  Project,
  Task,
} from "@/lib/types";
import { cn } from "@/lib/utils";

export default function WorkspaceOverviewPage() {
  const { id } = useParams<{ id: string }>();
  const [health, setHealth] = React.useState<HealthOverview | null>(null);
  const [campaigns, setCampaigns] = React.useState<Campaign[]>([]);
  const [projects, setProjects] = React.useState<Project[]>([]);
  const [tasks, setTasks] = React.useState<Task[]>([]);
  const [loading, setLoading] = React.useState(true);

  React.useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        // Real production data — health + campaigns from existing endpoints.
        // Projects + tasks from new endpoints (empty until backend deploy).
        const [h, c, ps, ts] = await Promise.all([
          healthApi.getOverview(id).catch(() => null),
          campaignApi.list({ clientId: id, pageSize: 50 }).then((r) => r.items).catch(() => []),
          projectApi.list({ workspaceId: id, includeClosed: false }).then((r) => r.items).catch(() => []),
          taskApi.list({ workspaceId: id, includeClosed: false, pageSize: 50 }).then((r) => r.items).catch(() => []),
        ]);
        if (cancelled) return;
        setHealth(h);
        setCampaigns(c);
        setProjects(ps);
        setTasks(ts);
      } catch (err) {
        console.error("Failed to load overview", err);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [id]);

  const activeCampaigns = campaigns.filter(
    (c) => (c.campaignStatus ?? c.status ?? "").toLowerCase() === "active"
  );
  const activeTasks = tasks
    .filter((t) => t.status === "in_progress" || t.status === "in_review")
    .slice(0, 6);
  const needsDecision = tasks.filter((t) => t.interactionPendingCount > 0);

  return (
    <div className="space-y-10">
      {/* Real-data stat strip */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Stat
          label="Connected inboxes"
          Icon={Mail}
          loading={loading}
          value={
            health
              ? `${(health.totalInboxes - health.deadInboxes).toLocaleString()}`
              : "—"
          }
          sub={health ? `of ${health.totalInboxes.toLocaleString()} total` : undefined}
        />
        <Stat
          label="Clean domains"
          Icon={Globe}
          loading={loading}
          value={health ? health.cleanDomains.toLocaleString() : "—"}
          sub={
            health
              ? `${health.flaggedDomains.toLocaleString()} flagged of ${health.totalDomains.toLocaleString()}`
              : undefined
          }
          tone={health && health.flaggedDomains > 0 ? "honey" : "ink"}
        />
        <Stat
          label="Active campaigns"
          Icon={Megaphone}
          loading={loading}
          value={
            health
              ? health.activeCampaigns.toLocaleString()
              : campaigns.length
                ? activeCampaigns.length.toLocaleString()
                : "—"
          }
          href={`/workspaces/${id}/campaigns`}
        />
        <Stat
          label="Critical alerts"
          Icon={AlertTriangle}
          loading={loading}
          value={health ? health.criticalAlerts.toLocaleString() : "—"}
          sub={
            health && health.warningAlerts > 0
              ? `${health.warningAlerts} warning`
              : undefined
          }
          tone={
            health && health.criticalAlerts > 0
              ? "rust"
              : health && health.warningAlerts > 0
                ? "honey"
                : "moss"
          }
        />
      </div>

      {/* Health summary line */}
      {health && (
        <div className="-mt-6 flex flex-wrap items-center gap-x-5 gap-y-1 text-xs text-ink-soft">
          {health.overallReplyRate > 0 && (
            <span>
              Reply rate{" "}
              <span className="font-mono text-foreground">
                {(health.overallReplyRate * 100).toFixed(2)}%
              </span>
            </span>
          )}
          {health.overallBounceRate > 0 && (
            <span>
              Bounce rate{" "}
              <span className="font-mono text-foreground">
                {(health.overallBounceRate * 100).toFixed(2)}%
              </span>
            </span>
          )}
          {health.totalEmailsSent > 0 && (
            <span>
              Total sends{" "}
              <span className="font-mono text-foreground">
                {health.totalEmailsSent.toLocaleString()}
              </span>
            </span>
          )}
          {health.lastUpdated && (
            <span className="ml-auto" title={String(health.lastUpdated)}>
              Health updated{" "}
              {formatDistanceToNowStrict(new Date(health.lastUpdated), {
                addSuffix: true,
              })}
            </span>
          )}
        </div>
      )}

      {/* Active campaigns — real EmailBison data */}
      <section aria-labelledby="overview-campaigns">
        <div className="flex items-center justify-between mb-4">
          <h2
            id="overview-campaigns"
            className="text-2xl inline-flex items-center gap-2"
          >
            <Megaphone className="h-5 w-5 text-honey" aria-hidden="true" />
            Active campaigns
          </h2>
          <Link
            href={`/workspaces/${id}/campaigns`}
            className="inline-flex items-center gap-1 text-sm text-copper hover:underline focus-visible:underline"
          >
            All campaigns
            <ChevronRight className="h-3.5 w-3.5" aria-hidden="true" />
          </Link>
        </div>
        {loading ? (
          <div className="text-sm text-ink-soft">Loading…</div>
        ) : activeCampaigns.length === 0 ? (
          <EmptyState
            title="No active campaigns"
            description="Campaigns appear here once EmailBison sync runs. Audit-this-campaign on the Campaigns page delegates analysis to the Data Analyst."
            cta={{ label: "Open Campaigns", href: `/workspaces/${id}/campaigns` }}
          />
        ) : (
          <ul className="rounded-lg border-[1.5px] border-border-bold bg-card divide-y divide-border">
            {activeCampaigns.slice(0, 5).map((c) => (
              <li key={c.id} className="px-4 py-2.5 flex items-center justify-between gap-3 hover:bg-muted/30 transition-colors">
                <div className="min-w-0">
                  <p className="text-sm font-medium truncate">
                    {c.name ?? c.campaignName}
                  </p>
                  {(c.industry || c.segment) && (
                    <p className="text-xs text-ink-soft truncate">
                      {[c.industry, c.segment].filter(Boolean).join(" · ")}
                    </p>
                  )}
                </div>
                <div className="flex items-center gap-4 shrink-0 text-xs font-mono">
                  <span title="Emails sent">
                    {(c.emailsSent ?? 0).toLocaleString()} sent
                  </span>
                  <span title="Unique replies">
                    {(c.uniqueReplies ?? c.repliesCount ?? 0).toLocaleString()} replies
                  </span>
                  <Link
                    href={`/workspaces/${id}/campaigns`}
                    className="text-copper hover:underline"
                  >
                    Open →
                  </Link>
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>

      {/* Active projects */}
      <section aria-labelledby="overview-projects">
        <div className="flex items-center justify-between mb-4">
          <h2 id="overview-projects" className="text-2xl inline-flex items-center gap-2">
            <FolderKanban className="h-5 w-5 text-copper" aria-hidden="true" />
            Active projects
          </h2>
          <Link
            href={`/workspaces/${id}/projects`}
            className="inline-flex items-center gap-1 text-sm text-copper hover:underline focus-visible:underline"
          >
            All projects
            <ChevronRight className="h-3.5 w-3.5" aria-hidden="true" />
          </Link>
        </div>
        {loading ? (
          <div className="text-sm text-ink-soft">Loading…</div>
        ) : projects.length === 0 ? (
          <EmptyState
            title="No active projects"
            description="Create the first project to plan multi-task work for this client."
            cta={{ label: "Open Projects", href: `/workspaces/${id}/projects` }}
          />
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {projects.slice(0, 4).map((p) => (
              <ProjectCard key={p.id} project={p} href={`/projects/${p.id}`} />
            ))}
          </div>
        )}
      </section>

      {/* Active tasks */}
      <section aria-labelledby="overview-tasks">
        <div className="flex items-center justify-between mb-4">
          <h2 id="overview-tasks" className="text-2xl inline-flex items-center gap-2">
            <ListTodo className="h-5 w-5 text-amber" aria-hidden="true" />
            Active tasks
            {needsDecision.length > 0 && (
              <span className="text-sm font-mono text-amber ml-2">
                · {needsDecision.length} need decision
              </span>
            )}
          </h2>
          <Link
            href={`/workspaces/${id}/tasks`}
            className="inline-flex items-center gap-1 text-sm text-copper hover:underline focus-visible:underline"
          >
            All tasks
            <ChevronRight className="h-3.5 w-3.5" aria-hidden="true" />
          </Link>
        </div>
        {loading ? (
          <div className="text-sm text-ink-soft">Loading…</div>
        ) : activeTasks.length === 0 ? (
          <EmptyState
            title="No active tasks"
            description="Nothing in progress right now. Open the Tasks board to create one."
            cta={{ label: "Open Tasks", href: `/workspaces/${id}/tasks` }}
          />
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
            {activeTasks.map((t) => (
              <TaskCard key={t.id} task={t} href={`/tasks/${t.id}`} />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

function Stat({
  label,
  Icon,
  value,
  sub,
  tone = "ink",
  href,
  loading,
}: {
  label: string;
  Icon?: React.ComponentType<{ className?: string }>;
  value: string;
  sub?: string;
  tone?: "ink" | "moss" | "honey" | "rust";
  href?: string;
  loading?: boolean;
}) {
  const toneClass = {
    ink: "text-foreground",
    moss: "text-moss",
    honey: "text-honey",
    rust: "text-rust",
  }[tone];
  const body = (
    <div className="rounded-lg border-[1.5px] border-border-bold bg-card p-3 transition-shadow hover:shadow-flat-sm h-full">
      <p className="text-xs uppercase tracking-wider text-ink-soft inline-flex items-center gap-1">
        {Icon && <Icon className="h-3 w-3" aria-hidden="true" />}
        {label}
      </p>
      <p className={cn("text-2xl font-mono mt-1", toneClass, loading && "opacity-40")}>
        {value}
      </p>
      {sub && <p className="text-xs text-ink-soft mt-0.5">{sub}</p>}
    </div>
  );
  return href ? (
    <Link href={href} className="no-underline">{body}</Link>
  ) : (
    body
  );
}

function EmptyState({
  title,
  description,
  cta,
}: {
  title: string;
  description: string;
  cta?: { label: string; href: string };
}) {
  return (
    <div className="flex flex-col items-center justify-center text-center gap-2 py-8 px-6 rounded-lg border border-dashed border-border bg-muted/30">
      <p className="text-base font-medium">{title}</p>
      <p className="text-sm text-ink-soft max-w-md">{description}</p>
      {cta && (
        <Link
          href={cta.href}
          className="mt-1 text-sm text-copper hover:underline focus-visible:underline"
        >
          {cta.label} →
        </Link>
      )}
    </div>
  );
}
