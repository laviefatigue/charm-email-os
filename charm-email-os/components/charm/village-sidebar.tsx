/**
 * VillageSidebar — workspace-first top-level navigation for the Charm redesign.
 * Fixed left rail. Shows global nav + workspace switcher with attention dots.
 * Fetches real workspaces from the Charm API (browser fetch via lib/data/charm).
 *
 * Tokens: --cream, --ink, --amber, --moss, --rust, --border-bold
 * See [[design-system/brand-brief]] §Mental Model — workspace-first
 */
"use client";

import * as React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Flame, Home, ScrollText, Bot, BarChart3, Settings } from "lucide-react";
import { cn } from "@/lib/utils";
import { getWorkspaces } from "@/lib/data/charm";
import type { WorkspaceCardData, AttentionState } from "./workspace-card";

const ATTENTION_DOT: Record<AttentionState, string> = {
  healthy: "bg-moss",
  amber: "bg-amber",
  red: "bg-rust",
};

const GLOBAL_LINKS = [
  { href: "/", label: "Dashboard", icon: BarChart3, match: (p: string) => p === "/" },
  {
    href: "/tasks",
    label: "Tasks",
    icon: ScrollText,
    match: (p: string) => p === "/tasks" || p.startsWith("/tasks/"),
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

export function VillageSidebar() {
  const pathname = usePathname();
  const [workspaces, setWorkspaces] = React.useState<WorkspaceCardData[]>([]);
  const [loaded, setLoaded] = React.useState(false);

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

  return (
    <aside
      className={cn(
        "shrink-0 w-60 h-screen flex flex-col",
        "bg-sidebar text-sidebar-foreground",
        "border-r-[1.5px] border-border-bold"
      )}
    >
      {/* Brand */}
      <div className="px-5 py-5 border-b border-border">
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
          {loaded ? `${workspaces.length} workspaces · ${totalPending} pending` : "Loading…"}
        </p>
      </div>

      {/* Global nav */}
      <nav className="px-3 py-4 space-y-1" aria-label="Global navigation">
        {GLOBAL_LINKS.map((link) => {
          const active = link.match(pathname);
          const showBadge = false; // legacy hook; total-pending badge will return when task counts wire up
          return (
            <Link
              key={link.href}
              href={link.href}
              aria-current={active ? "page" : undefined}
              className={cn(
                "flex items-center justify-between gap-2 px-3 py-2 rounded-md text-sm",
                "transition-colors",
                active
                  ? "bg-amber text-ink border-[1.5px] border-ink font-medium"
                  : "text-foreground hover:bg-muted border-[1.5px] border-transparent"
              )}
            >
              <span className="inline-flex items-center gap-2">
                <link.icon className="h-4 w-4 shrink-0" aria-hidden="true" />
                {link.label}
              </span>
              {showBadge && (
                <span className="inline-flex items-center justify-center h-5 min-w-5 px-1 rounded-sm bg-amber text-ink text-xs font-semibold border-[1.5px] border-ink">
                  {totalPending}
                </span>
              )}
            </Link>
          );
        })}
      </nav>

      {/* Workspace switcher */}
      <div className="px-3 mt-2 mb-2 flex-1 min-h-0 flex flex-col">
        <div className="px-2 mb-2 text-xs font-medium uppercase tracking-wider text-ink-soft">
          Workspaces
        </div>
        <nav
          className="space-y-0.5 overflow-y-auto pr-1 custom-scrollbar"
          aria-label="Workspaces"
        >
          {!loaded && (
            <div className="px-3 py-2 text-sm text-ink-soft animate-pulse">
              Fetching…
            </div>
          )}
          {loaded && workspaces.length === 0 && (
            <div className="px-3 py-2 text-sm text-ink-soft">
              No workspaces (API unreachable)
            </div>
          )}
          {workspaces.map((ws) => {
            const href = `/workspaces/${ws.id}`;
            const active = pathname === href || pathname.startsWith(`${href}/`);
            return (
              <Link
                key={ws.id}
                href={href}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "flex items-center justify-between gap-2 px-3 py-2 rounded-md text-sm",
                  "transition-colors",
                  active
                    ? "bg-amber text-ink border-[1.5px] border-ink font-medium"
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
      </div>

      {/* Footer — quiet stats */}
      <div className="px-5 py-4 border-t border-border text-xs text-ink-soft">
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
