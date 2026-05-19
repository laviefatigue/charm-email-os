/**
 * VillageSidebar — two-mode workspace-first nav.
 *
 *   HOME MODE (path is /, /agents, /settings, etc.):
 *     Brand → Home link → Workspaces list (active + collapsed inactive) → Admin
 *
 *   WORKSPACE MODE (path matches /workspaces/{id}/*):
 *     Brand → Compact workspace switcher (popover) → Workspace tabs DOMINATE → Admin
 *
 * The mode switch is the load-bearing UX move: when an operator picks a workspace,
 * the cross-workspace switcher collapses and the workspace's own tabs become the
 * dominant left rail. Switching workspaces is still one click via the popover.
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
  ChevronLeft,
  ChevronsUpDown,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { getWorkspaces } from "@/lib/data/charm";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
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

// 7 items. Settings sits as a gear in the workspace header (not in this rail).
const WORKSPACE_NAV_ITEMS: WorkspaceNavItem[] = [
  { segment: "", label: "Overview", icon: LayoutDashboard },
  { segment: "projects", label: "Projects", icon: FolderKanban },
  { segment: "tasks", label: "Tasks", icon: ListTodo },
  { segment: "campaigns", label: "Campaigns", icon: Megaphone },
  { segment: "infrastructure", label: "Infrastructure", icon: Server },
  { segment: "assets", label: "Assets", icon: FileText },
  { segment: "context", label: "Context", icon: GitBranch, comingSoon: true },
];

const WORKSPACE_ROUTE_RE = /^\/workspaces\/([^/]+)/;

export function VillageSidebar() {
  const pathname = usePathname();
  const [workspaces, setWorkspaces] = React.useState<WorkspaceCardData[]>([]);
  const [loaded, setLoaded] = React.useState(false);
  const [inactiveOpen, setInactiveOpen] = React.useState(false);
  const [switcherOpen, setSwitcherOpen] = React.useState(false);

  React.useEffect(() => {
    let cancelled = false;
    getWorkspaces()
      .then((ws) => {
        if (!cancelled) {
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
  const totalPending = workspaces.reduce((sum, w) => sum + w.pendingRecommendations, 0);
  const needsAttention = activeWorkspaces.filter((w) => w.attentionState !== "healthy").length;

  const workspaceMatch = pathname.match(WORKSPACE_ROUTE_RE);
  const activeWorkspaceId = workspaceMatch?.[1];
  const activeWorkspace = activeWorkspaceId
    ? workspaces.find((w) => w.id === activeWorkspaceId)
    : null;
  const inWorkspace = Boolean(activeWorkspaceId);
  const isHome = pathname === "/";

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
        {!inWorkspace && (
          <p className="mt-1 text-xs text-ink-soft">
            {loaded
              ? `${workspaces.length} workspaces${totalPending > 0 ? ` · ${totalPending} pending` : ""}`
              : "Loading…"}
          </p>
        )}
      </div>

      <div className="flex-1 min-h-0 overflow-y-auto custom-scrollbar">
        {inWorkspace ? (
          <WorkspaceModeBody
            pathname={pathname}
            activeWorkspaceId={activeWorkspaceId!}
            activeWorkspace={activeWorkspace ?? null}
            workspaces={workspaces}
            loaded={loaded}
            switcherOpen={switcherOpen}
            setSwitcherOpen={setSwitcherOpen}
          />
        ) : (
          <HomeModeBody
            pathname={pathname}
            workspaces={workspaces}
            activeWorkspaces={activeWorkspaces}
            inactiveWorkspaces={inactiveWorkspaces}
            loaded={loaded}
            isHome={isHome}
            needsAttention={needsAttention}
            inactiveOpen={inactiveOpen}
            setInactiveOpen={setInactiveOpen}
          />
        )}

        {/* Admin — tucked at the bottom in both modes */}
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

// ─── HOME MODE ────────────────────────────────────────────────────────────────

function HomeModeBody({
  pathname,
  workspaces,
  activeWorkspaces,
  inactiveWorkspaces,
  loaded,
  isHome,
  needsAttention,
  inactiveOpen,
  setInactiveOpen,
}: {
  pathname: string;
  workspaces: WorkspaceCardData[];
  activeWorkspaces: WorkspaceCardData[];
  inactiveWorkspaces: WorkspaceCardData[];
  loaded: boolean;
  isHome: boolean;
  needsAttention: number;
  inactiveOpen: boolean;
  setInactiveOpen: (fn: (v: boolean) => boolean) => void;
}) {
  return (
    <>
      {/* Home link */}
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
          <div className="px-3 py-1.5 text-sm text-ink-soft animate-pulse">Fetching…</div>
        )}
        {loaded && workspaces.length === 0 && (
          <div className="px-3 py-1.5 text-sm text-ink-soft">
            No workspaces (API unreachable)
          </div>
        )}

        {activeWorkspaces.length > 0 && (
          <nav className="space-y-0.5" aria-label="Active workspaces">
            {activeWorkspaces.map((ws) => (
              <HomeWorkspaceLink key={ws.id} ws={ws} pathname={pathname} />
            ))}
          </nav>
        )}

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
                className={cn("h-3 w-3 transition-transform", !inactiveOpen && "-rotate-90")}
                aria-hidden="true"
              />
            </button>
            {inactiveOpen && (
              <nav className="mt-1 space-y-0.5" aria-label="Inactive workspaces">
                {inactiveWorkspaces.map((ws) => (
                  <HomeWorkspaceLink key={ws.id} ws={ws} pathname={pathname} dimmed />
                ))}
              </nav>
            )}
          </div>
        )}
      </div>
    </>
  );
}

function HomeWorkspaceLink({
  ws,
  pathname,
  dimmed = false,
}: {
  ws: WorkspaceCardData;
  pathname: string;
  dimmed?: boolean;
}) {
  const wsHref = `/workspaces/${ws.id}`;
  return (
    <Link
      href={wsHref}
      aria-current={pathname === wsHref ? "page" : undefined}
      className={cn(
        "flex items-center justify-between gap-2 px-3 py-1.5 rounded-md text-sm transition-colors border-[1.5px]",
        "border-transparent text-foreground hover:bg-muted",
        dimmed && "text-ink-soft"
      )}
    >
      <span className="inline-flex items-center gap-2 min-w-0">
        <span
          className={cn(
            "h-2 w-2 rounded-full shrink-0",
            ATTENTION_DOT[ws.attentionState],
            dimmed && "opacity-50"
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
}

// ─── WORKSPACE MODE ───────────────────────────────────────────────────────────

function WorkspaceModeBody({
  pathname,
  activeWorkspaceId,
  activeWorkspace,
  workspaces,
  loaded,
  switcherOpen,
  setSwitcherOpen,
}: {
  pathname: string;
  activeWorkspaceId: string;
  activeWorkspace: WorkspaceCardData | null;
  workspaces: WorkspaceCardData[];
  loaded: boolean;
  switcherOpen: boolean;
  setSwitcherOpen: (v: boolean) => void;
}) {
  const wsHref = `/workspaces/${activeWorkspaceId}`;
  const displayName = activeWorkspace?.name ?? (loaded ? "Unknown workspace" : "Loading…");
  const attention = activeWorkspace?.attentionState ?? "healthy";

  return (
    <>
      {/* Back to home + workspace switcher */}
      <div className="px-3 pt-4 space-y-2">
        <Link
          href="/"
          className="inline-flex items-center gap-1 text-xs text-ink-soft hover:text-foreground transition-colors"
        >
          <ChevronLeft className="h-3 w-3" aria-hidden="true" />
          All workspaces
        </Link>

        <Popover open={switcherOpen} onOpenChange={setSwitcherOpen}>
          <PopoverTrigger asChild>
            <button
              type="button"
              className={cn(
                "w-full flex items-center justify-between gap-2 px-3 py-2 rounded-md text-left",
                "bg-card border-[1.5px] border-border-bold shadow-flat-sm",
                "hover:translate-x-px hover:translate-y-px hover:shadow-none transition-all"
              )}
              aria-label="Switch workspace"
            >
              <span className="inline-flex items-center gap-2 min-w-0">
                <span
                  className={cn("h-2 w-2 rounded-full shrink-0", ATTENTION_DOT[attention])}
                  aria-hidden="true"
                />
                <span className="truncate text-sm font-medium">{displayName}</span>
              </span>
              <ChevronsUpDown className="h-3.5 w-3.5 text-ink-soft shrink-0" aria-hidden="true" />
            </button>
          </PopoverTrigger>
          <PopoverContent
            align="start"
            sideOffset={6}
            className="w-60 p-1.5 max-h-[60vh] overflow-y-auto custom-scrollbar"
          >
            <p className="px-2 py-1 text-[10px] font-medium uppercase tracking-wider text-ink-soft">
              Switch workspace
            </p>
            {!loaded && (
              <p className="px-2 py-1 text-sm text-ink-soft">Loading…</p>
            )}
            {loaded &&
              workspaces.map((ws) => {
                const isCurrent = ws.id === activeWorkspaceId;
                return (
                  <Link
                    key={ws.id}
                    href={`/workspaces/${ws.id}`}
                    onClick={() => setSwitcherOpen(false)}
                    className={cn(
                      "flex items-center justify-between gap-2 px-2 py-1.5 rounded-sm text-sm",
                      isCurrent ? "bg-amber/30 text-ink font-medium" : "hover:bg-muted",
                      !ws.isActive && !isCurrent && "text-ink-soft"
                    )}
                  >
                    <span className="inline-flex items-center gap-2 min-w-0">
                      <span
                        className={cn(
                          "h-2 w-2 rounded-full shrink-0",
                          ATTENTION_DOT[ws.attentionState]
                        )}
                        aria-hidden="true"
                      />
                      <span className="truncate">{ws.name}</span>
                      {!ws.isActive && (
                        <span className="ml-1 text-[9px] uppercase tracking-wide text-ink-soft">
                          inactive
                        </span>
                      )}
                    </span>
                    {ws.pendingRecommendations > 0 && (
                      <span className="inline-flex items-center justify-center h-4 min-w-4 px-1 rounded-sm bg-amber text-ink text-[10px] font-semibold border border-ink">
                        {ws.pendingRecommendations}
                      </span>
                    )}
                  </Link>
                );
              })}
          </PopoverContent>
        </Popover>
      </div>

      {/* Workspace tabs DOMINATE — large, full-width, icon + label */}
      <nav className="px-3 pt-4 space-y-1" aria-label={`${displayName} sections`}>
        {WORKSPACE_NAV_ITEMS.map((item) => {
          const subHref = item.segment ? `${wsHref}/${item.segment}` : wsHref;
          const isActive =
            item.segment === ""
              ? pathname === wsHref
              : pathname === subHref || pathname.startsWith(`${subHref}/`);
          const Icon = item.icon;
          return (
            <Link
              key={item.segment || "overview"}
              href={subHref}
              aria-current={isActive ? "page" : undefined}
              className={cn(
                "flex items-center justify-between gap-2 px-3 py-2 rounded-md text-sm transition-colors border-[1.5px]",
                isActive
                  ? "bg-amber text-ink border-ink font-medium shadow-flat-sm"
                  : "border-transparent text-foreground hover:bg-muted",
                item.comingSoon && !isActive && "text-ink-soft"
              )}
            >
              <span className="inline-flex items-center gap-2.5 min-w-0">
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
    </>
  );
}
