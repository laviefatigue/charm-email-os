/**
 * VillageSidebar — workspace-dominant nav.
 *
 * AE-centric IA (2026-05-16, Option A cut): the work happens INSIDE workspaces.
 * The sidebar reflects that. Cross-workspace roll-ups are dead — there's a
 * single Home as the daily landing, the workspace switcher IS the nav, and
 * Admin (agents + global settings) is tucked at the bottom.
 *
 *   Home
 *   ── Workspaces ──
 *   ● Active workspace (expanded sub-nav inline)
 *   ○ Other workspaces
 *   ── Admin ──
 *   Agents
 *   Settings
 */
"use client";

import * as React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Flame,
  Home,
  Bot,
  Settings,
  LayoutDashboard,
  FolderKanban,
  ListTodo,
  Megaphone,
  GitBranch,
  FileText,
  Server,
  ChevronDown,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { getWorkspaces } from "@/lib/data/charm";
import type { WorkspaceCardData, AttentionState } from "./workspace-card";

const ATTENTION_DOT: Record<AttentionState, string> = {
  healthy: "bg-moss",
  amber: "bg-amber",
  red: "bg-rust",
};

interface WorkspaceNavItem {
  segment: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  comingSoon?: boolean;
}

// 7 items — Settings moves to a gear icon in the workspace header.
// Events is reachable via deep-link / Overview "view all activity" but not in nav.
const WORKSPACE_NAV_ITEMS: WorkspaceNavItem[] = [
  { segment: "", label: "Overview", icon: LayoutDashboard },
  { segment: "projects", label: "Projects", icon: FolderKanban },
  { segment: "tasks", label: "Tasks", icon: ListTodo },
  { segment: "campaigns", label: "Campaigns", icon: Megaphone },
  { segment: "context", label: "Context", icon: GitBranch, comingSoon: true },
  { segment: "assets", label: "Assets", icon: FileText },
  { segment: "infrastructure", label: "Infrastructure", icon: Server, comingSoon: true },
];

const WORKSPACE_ROUTE_RE = /^\/workspaces\/([^/]+)/;

// Renders a single workspace item with its inline sub-nav when active.
function renderWorkspaceItem(
  ws: WorkspaceCardData,
  activeWorkspaceId: string | undefined,
  pathname: string,
  dimmed = false
): React.ReactNode {
  const wsHref = `/workspaces/${ws.id}`;
  const isActive = activeWorkspaceId === ws.id;
  return (
    <div key={ws.id}>
      <Link
        href={wsHref}
        aria-current={pathname === wsHref ? "page" : isActive ? "true" : undefined}
        className={cn(
          "flex items-center justify-between gap-2 px-3 py-1.5 rounded-md text-sm transition-colors border-[1.5px]",
          isActive
            ? "bg-amber text-ink border-ink font-medium"
            : "border-transparent text-foreground hover:bg-muted",
          dimmed && !isActive && "text-ink-soft"
        )}
      >
        <span className="inline-flex items-center gap-2 min-w-0">
          <span
            className={cn(
              "h-2 w-2 rounded-full shrink-0",
              ATTENTION_DOT[ws.attentionState],
              dimmed && !isActive && "opacity-50"
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

      {isActive && (
        <nav
          className="mt-0.5 ml-2 pl-3 border-l border-border space-y-0.5"
          aria-label={`${ws.name} sections`}
        >
          {WORKSPACE_NAV_ITEMS.map((item) => {
            const subHref = item.segment ? `${wsHref}/${item.segment}` : wsHref;
            const subActive =
              item.segment === ""
                ? pathname === wsHref
                : pathname === subHref || pathname.startsWith(`${subHref}/`);
            const Icon = item.icon;
            return (
              <Link
                key={item.segment || "overview"}
                href={subHref}
                aria-current={subActive ? "page" : undefined}
                className={cn(
                  "flex items-center justify-between gap-2 px-2 py-1 rounded-md text-xs transition-colors border-[1.5px]",
                  subActive
                    ? "bg-cream text-ink border-border-bold font-medium"
                    : "border-transparent text-foreground hover:bg-muted",
                  item.comingSoon && !subActive && "text-ink-soft"
                )}
              >
                <span className="inline-flex items-center gap-2 min-w-0">
                  <Icon className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
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
      )}
    </div>
  );
}

export function VillageSidebar() {
  const pathname = usePathname();
  const [workspaces, setWorkspaces] = React.useState<WorkspaceCardData[]>([]);
  const [loaded, setLoaded] = React.useState(false);
  const [inactiveOpen, setInactiveOpen] = React.useState(false);

  React.useEffect(() => {
    let cancelled = false;
    getWorkspaces()
      .then((ws) => {
        if (!cancelled) {
          // Sort: active first (by name), then inactive (by name)
          const sorted = [...ws].sort((a, b) => {
            const aActive = a.isActive ? 1 : 0;
            const bActive = b.isActive ? 1 : 0;
            if (aActive !== bActive) return bActive - aActive;
            return a.name.localeCompare(b.name);
          });
          setWorkspaces(sorted);
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

  const activeWorkspaces = workspaces.filter((w) => w.isActive);
  const inactiveWorkspaces = workspaces.filter((w) => !w.isActive);
  const totalPending = workspaces.reduce(
    (sum, w) => sum + w.pendingRecommendations,
    0
  );
  const needsAttention = activeWorkspaces.filter(
    (w) => w.attentionState !== "healthy"
  ).length;

  const workspaceMatch = pathname.match(WORKSPACE_ROUTE_RE);
  const activeWorkspaceId = workspaceMatch?.[1];
  const isHome = pathname === "/";

  // Auto-expand inactive group if user navigates to an inactive workspace
  React.useEffect(() => {
    if (
      activeWorkspaceId &&
      inactiveWorkspaces.some((w) => w.id === activeWorkspaceId)
    ) {
      setInactiveOpen(true);
    }
  }, [activeWorkspaceId, inactiveWorkspaces]);

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
            ? `${workspaces.length} workspaces${totalPending > 0 ? ` · ${totalPending} pending` : ""}`
            : "Loading…"}
        </p>
      </div>

      {/* Scrollable body */}
      <div className="flex-1 min-h-0 overflow-y-auto custom-scrollbar">
        {/* Home (singular) */}
        <div className="px-3 pt-4">
          <Link
            href="/"
            aria-current={isHome ? "page" : undefined}
            className={cn(
              "flex items-center gap-2 px-3 py-2 rounded-md text-sm transition-colors",
              isHome
                ? "bg-amber text-ink border-[1.5px] border-ink font-medium"
                : "text-foreground hover:bg-muted border-[1.5px] border-transparent"
            )}
          >
            <Home className="h-4 w-4 shrink-0" aria-hidden="true" />
            Home
          </Link>
        </div>

        {/* Workspaces — the dominant nav element */}
        <div className="px-3 pt-5 pb-2">
          <div className="px-2 mb-2 flex items-center justify-between">
            <span className="text-[10px] font-medium uppercase tracking-wider text-ink-soft">
              Workspaces
            </span>
            {needsAttention > 0 && (
              <span className="text-[10px] font-medium text-rust">
                {needsAttention} need attention
              </span>
            )}
          </div>
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

          {/* Active workspaces — always visible */}
          {activeWorkspaces.length > 0 && (
            <nav className="space-y-0.5" aria-label="Active workspaces">
              {activeWorkspaces.map((ws) =>
                renderWorkspaceItem(ws, activeWorkspaceId, pathname)
              )}
            </nav>
          )}

          {/* Inactive workspaces — collapsible */}
          {inactiveWorkspaces.length > 0 && (
            <div className={cn("mt-2", activeWorkspaces.length > 0 && "pt-2 border-t border-border")}>
              <button
                type="button"
                onClick={() => setInactiveOpen((v) => !v)}
                aria-expanded={inactiveOpen}
                className="w-full px-2 py-1 flex items-center justify-between text-[10px] font-medium uppercase tracking-wider text-ink-soft hover:text-foreground transition-colors"
              >
                <span>
                  Inactive
                  <span className="ml-1.5 font-mono">({inactiveWorkspaces.length})</span>
                </span>
                <ChevronDown
                  className={cn(
                    "h-3 w-3 transition-transform",
                    !inactiveOpen && "-rotate-90"
                  )}
                  aria-hidden="true"
                />
              </button>
              {inactiveOpen && (
                <nav className="mt-1 space-y-0.5" aria-label="Inactive workspaces">
                  {inactiveWorkspaces.map((ws) =>
                    renderWorkspaceItem(ws, activeWorkspaceId, pathname, /*dimmed*/ true)
                  )}
                </nav>
              )}
            </div>
          )}
        </div>

        {/* Admin — tucked, rarely touched */}
        <div className="px-3 pt-5 pb-3 border-t border-border mt-3">
          <div className="px-2 mb-2 text-[10px] font-medium uppercase tracking-wider text-ink-soft">
            Admin
          </div>
          <nav className="space-y-0.5" aria-label="Admin">
            {[
              { href: "/agents", label: "Agents", icon: Bot },
              { href: "/settings", label: "Settings", icon: Settings },
            ].map((link) => {
              const active = pathname === link.href || pathname.startsWith(`${link.href}/`);
              return (
                <Link
                  key={link.href}
                  href={link.href}
                  aria-current={active ? "page" : undefined}
                  className={cn(
                    "flex items-center gap-2 px-3 py-1.5 rounded-md text-sm transition-colors border-[1.5px]",
                    active
                      ? "bg-amber text-ink border-ink font-medium"
                      : "border-transparent text-ink-soft hover:bg-muted hover:text-foreground"
                  )}
                >
                  <link.icon className="h-4 w-4 shrink-0" aria-hidden="true" />
                  {link.label}
                </Link>
              );
            })}
          </nav>
        </div>
      </div>
    </aside>
  );
}
