/**
 * VillageSidebar — consolidated left nav.
 * PRIMARY (top): global views — Dashboard / Projects / Tasks / Timeline / Agents / Settings.
 * WORKSPACE (middle): when inside /workspaces/[id], shows that workspace's sub-pages
 * (Overview / Projects / Tasks / Recommendations / Events / Agents / + stubs).
 * SWITCHER (bottom): workspace list with attention dots.
 *
 * Tokens: --cream, --ink, --amber, --moss, --rust, --border-bold
 * See [[design-system/brand-brief]] §Mental Model — workspace-first
 */
"use client";

import * as React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Flame,
  ScrollText,
  Bot,
  BarChart3,
  Settings,
  FolderKanban,
  CalendarRange,
  LayoutDashboard,
  Server,
  GitBranch,
  ListTodo,
  ChevronDown,
  Megaphone,
  FileText,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { getWorkspaces } from "@/lib/data/charm";
import type { WorkspaceCardData, AttentionState } from "./workspace-card";

const ATTENTION_DOT: Record<AttentionState, string> = {
  healthy: "bg-moss",
  amber: "bg-amber",
  red: "bg-rust",
};

// ─── Global nav ──────────────────────────────────────────────────────────────

const GLOBAL_LINKS = [
  { href: "/", label: "Dashboard", icon: BarChart3, match: (p: string) => p === "/" },
  {
    href: "/projects",
    label: "Projects",
    icon: FolderKanban,
    match: (p: string) =>
      (p === "/projects" || p.startsWith("/projects/")) &&
      !p.startsWith("/workspaces/"),
  },
  {
    href: "/tasks",
    label: "Tasks",
    icon: ScrollText,
    match: (p: string) =>
      (p === "/tasks" || p.startsWith("/tasks/")) && !p.startsWith("/workspaces/"),
  },
  {
    href: "/campaigns",
    label: "Campaigns",
    icon: Megaphone,
    match: (p: string) =>
      (p === "/campaigns" || p.startsWith("/campaigns/")) && !p.startsWith("/workspaces/"),
  },
  {
    href: "/timeline",
    label: "Timeline",
    icon: CalendarRange,
    match: (p: string) => p === "/timeline" || p.startsWith("/timeline/"),
  },
  {
    href: "/agents",
    label: "Agents",
    icon: Bot,
    match: (p: string) => p === "/agents" || p.startsWith("/agents/"),
  },
  {
    href: "/settings",
    label: "Settings",
    icon: Settings,
    match: (p: string) => p === "/settings",
  },
] as const;

// ─── Workspace sub-nav items ─────────────────────────────────────────────────

interface WorkspaceNavItem {
  segment: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  comingSoon?: boolean;
}

// 7 items, ruthlessly pruned (2026-05-16):
//   • Domains + Inboxes → merged into Infrastructure
//   • Pending Gates → subsumed by Projects + Tasks (the new work-decision surfaces)
//   • Recommendations → subsumed by Tasks (interactions render inline on each task;
//     filter by "needs decision" on /tasks if a dedicated mailbox view is needed)
//   • Integrations → controlled internally, not a workspace-level concern
//   • Workspace Agents → redundant with the global /agents page (agents are global)
//   • Routines + Costs → admin config, surface elsewhere when needed
const WORKSPACE_NAV_ITEMS: WorkspaceNavItem[] = [
  { segment: "", label: "Overview", icon: LayoutDashboard },
  { segment: "projects", label: "Projects", icon: FolderKanban },
  { segment: "tasks", label: "Tasks", icon: ListTodo },
  { segment: "campaigns", label: "Campaigns", icon: Megaphone },
  { segment: "events", label: "Events", icon: ScrollText },
  { segment: "assets", label: "Assets", icon: FileText },
  { segment: "infrastructure", label: "Infrastructure", icon: Server, comingSoon: true },
  { segment: "context", label: "Context", icon: GitBranch, comingSoon: true },
  { segment: "settings", label: "Settings", icon: Settings, comingSoon: true },
];

const WORKSPACE_ROUTE_RE = /^\/workspaces\/([^/]+)/;

export function VillageSidebar() {
  const pathname = usePathname();
  const [workspaces, setWorkspaces] = React.useState<WorkspaceCardData[]>([]);
  const [loaded, setLoaded] = React.useState(false);
  const [switcherOpen, setSwitcherOpen] = React.useState(true);

  React.useEffect(() => {
    let cancelled = false;
    getWorkspaces()
      .then((ws) => {
        if (!cancelled) {
          setWorkspaces(ws);
          setLoaded(true);
        }
      })
      .catch(() => {
        if (!cancelled) setLoaded(true);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const totalPending = workspaces.reduce(
    (sum, w) => sum + w.pendingRecommendations,
    0
  );
  const totalAgents = workspaces.reduce((sum, w) => sum + w.agentsActive, 0);
  const totalLive = workspaces.reduce((sum, w) => sum + w.domainsLive, 0);
  const needsAttention = workspaces.filter(
    (w) => w.attentionState !== "healthy"
  ).length;

  // Detect active workspace from URL
  const workspaceMatch = pathname.match(WORKSPACE_ROUTE_RE);
  const activeWorkspaceId = workspaceMatch?.[1];
  const activeWorkspace = activeWorkspaceId
    ? workspaces.find((w) => w.id === activeWorkspaceId)
    : null;

  return (
    <aside
      className={cn(
        "shrink-0 w-64 h-screen flex flex-col",
        "bg-sidebar text-sidebar-foreground",
        "border-r-[1.5px] border-border-bold"
      )}
    >
      {/* Brand */}
      <div className="px-5 py-5 border-b border-border shrink-0">
        <Link
          href="/"
          className="inline-flex items-center gap-2 group focus-visible:outline-none"
        >
          <span className="inline-flex items-center justify-center h-8 w-8 rounded-md bg-amber text-ink border-[1.5px] border-ink shadow-flat-sm transition-shadow group-hover:translate-x-px group-hover:translate-y-px group-hover:shadow-none">
            <Flame className="h-4 w-4" aria-hidden="true" />
          </span>
          <span className="text-2xl">Charm</span>
        </Link>
        <p className="mt-1 text-xs text-ink-soft">
          {loaded
            ? `${workspaces.length} workspaces · ${totalPending} pending`
            : "Loading…"}
        </p>
      </div>

      {/* Scrollable nav body */}
      <div className="flex-1 min-h-0 overflow-y-auto custom-scrollbar">
        {/* PRIMARY (global) */}
        <div className="px-3 pt-4 pb-2">
          <div className="px-2 mb-2 text-[10px] font-medium uppercase tracking-wider text-ink-soft">
            Primary
          </div>
          <nav className="space-y-0.5" aria-label="Global navigation">
            {GLOBAL_LINKS.map((link) => {
              const active = link.match(pathname);
              return (
                <Link
                  key={link.href}
                  href={link.href}
                  aria-current={active ? "page" : undefined}
                  className={cn(
                    "flex items-center gap-2 px-3 py-1.5 rounded-md text-sm transition-colors",
                    active
                      ? "bg-amber text-ink border-[1.5px] border-ink font-medium"
                      : "text-foreground hover:bg-muted border-[1.5px] border-transparent"
                  )}
                >
                  <link.icon className="h-4 w-4 shrink-0" aria-hidden="true" />
                  {link.label}
                </Link>
              );
            })}
          </nav>
        </div>

        {/* WORKSPACE sub-nav (when in a workspace) */}
        {activeWorkspace && (
          <div className="px-3 pt-3 pb-2 border-t border-border">
            <div className="px-2 mb-1 text-[10px] font-medium uppercase tracking-wider text-ink-soft flex items-center gap-2">
              <span
                className={cn(
                  "h-1.5 w-1.5 rounded-full shrink-0",
                  ATTENTION_DOT[activeWorkspace.attentionState]
                )}
                aria-hidden="true"
              />
              Workspace
            </div>
            <div className="px-2 mb-2 text-sm font-medium truncate">
              {activeWorkspace.name}
            </div>
            <nav className="space-y-0.5" aria-label="Workspace pages">
              {WORKSPACE_NAV_ITEMS.map((item) => {
                const base = `/workspaces/${activeWorkspace.id}`;
                const href = item.segment ? `${base}/${item.segment}` : base;
                const active =
                  item.segment === ""
                    ? pathname === base
                    : pathname === href || pathname.startsWith(`${href}/`);
                const Icon = item.icon;
                return (
                  <Link
                    key={item.segment || "overview"}
                    href={href}
                    aria-current={active ? "page" : undefined}
                    className={cn(
                      "flex items-center justify-between gap-2 px-3 py-1.5 rounded-md text-sm transition-colors border-[1.5px]",
                      active
                        ? "bg-amber text-ink border-ink font-medium"
                        : "border-transparent text-foreground hover:bg-muted",
                      item.comingSoon && !active && "text-ink-soft"
                    )}
                  >
                    <span className="inline-flex items-center gap-2 min-w-0">
                      <Icon className="h-4 w-4 shrink-0" aria-hidden="true" />
                      <span className="truncate">{item.label}</span>
                    </span>
                    {item.comingSoon && (
                      <span className="text-[9px] uppercase tracking-wide text-ink-soft font-medium">
                        soon
                      </span>
                    )}
                  </Link>
                );
              })}
            </nav>
          </div>
        )}

        {/* SWITCHER */}
        <div className="px-3 pt-3 pb-3 border-t border-border">
          <button
            type="button"
            onClick={() => setSwitcherOpen((v) => !v)}
            className="w-full px-2 mb-2 text-[10px] font-medium uppercase tracking-wider text-ink-soft flex items-center justify-between hover:text-foreground transition-colors"
          >
            <span>{activeWorkspace ? "Switch workspace" : "Workspaces"}</span>
            <ChevronDown
              className={cn("h-3 w-3 transition-transform", !switcherOpen && "-rotate-90")}
              aria-hidden="true"
            />
          </button>
          {switcherOpen && (
            <nav className="space-y-0.5" aria-label="Workspaces">
              {!loaded && (
                <div className="px-3 py-1.5 text-sm text-ink-soft animate-pulse">
                  Fetching…
                </div>
              )}
              {loaded && workspaces.length === 0 && (
                <div className="px-3 py-1.5 text-sm text-ink-soft">
                  No workspaces (API unreachable)
                </div>
              )}
              {workspaces.map((ws) => {
                const href = `/workspaces/${ws.id}`;
                const active = activeWorkspaceId === ws.id;
                return (
                  <Link
                    key={ws.id}
                    href={href}
                    aria-current={active ? "page" : undefined}
                    className={cn(
                      "flex items-center justify-between gap-2 px-3 py-1.5 rounded-md text-sm transition-colors",
                      active
                        ? "bg-muted text-foreground font-medium border-[1.5px] border-border-bold"
                        : "text-foreground hover:bg-muted border-[1.5px] border-transparent"
                    )}
                  >
                    <span className="inline-flex items-center gap-2 min-w-0">
                      <span
                        className={cn(
                          "h-2 w-2 rounded-full shrink-0",
                          ATTENTION_DOT[ws.attentionState]
                        )}
                        aria-label={ws.attentionState}
                      />
                      <span className="truncate">{ws.name}</span>
                    </span>
                    {ws.pendingRecommendations > 0 && (
                      <span className="inline-flex items-center justify-center h-5 min-w-5 px-1 rounded-sm bg-amber/80 text-ink text-xs font-semibold border border-ink">
                        {ws.pendingRecommendations}
                      </span>
                    )}
                  </Link>
                );
              })}
            </nav>
          )}
        </div>
      </div>

      {/* Footer — quiet stats */}
      <div className="px-5 py-3 border-t border-border text-xs text-ink-soft shrink-0">
        <div className="font-mono">
          {totalAgents} agents · {totalLive} inboxes
        </div>
        {needsAttention > 0 && (
          <div className="mt-1 text-rust">
            {needsAttention} workspace{needsAttention === 1 ? "" : "s"} need attention
          </div>
        )}
      </div>
    </aside>
  );
}
