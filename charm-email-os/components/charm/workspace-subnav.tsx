/**
 * WorkspaceSubnav — left rail inside the workspace detail layout.
 * Renders the 12-item sub-nav from [[design-system/references/ref-paperclip]]
 * §Workspace Detail Sub-Nav.
 *
 * Tokens: --ink, --amber, --cream, --ink-soft
 */
"use client";

import * as React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Sparkles,
  LayoutDashboard,
  Inbox,
  Bot,
  Boxes,
  Mail,
  ScrollText,
  ShieldCheck,
  Clock,
  GitBranch,
  Plug,
  DollarSign,
  Settings,
} from "lucide-react";
import { cn } from "@/lib/utils";

interface SubnavItem {
  segment: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  comingSoon?: boolean;
}

const ITEMS: SubnavItem[] = [
  { segment: "", label: "Overview", icon: LayoutDashboard },
  { segment: "recommendations", label: "Recommendations", icon: Sparkles },
  { segment: "agents", label: "Agents", icon: Bot },
  { segment: "domains", label: "Domains", icon: Boxes, comingSoon: true },
  { segment: "inboxes", label: "Inboxes", icon: Mail, comingSoon: true },
  { segment: "events", label: "Events", icon: ScrollText },
  { segment: "pending-gates", label: "Pending Gates", icon: ShieldCheck, comingSoon: true },
  { segment: "routines", label: "Routines", icon: Clock, comingSoon: true },
  { segment: "context", label: "Context", icon: GitBranch, comingSoon: true },
  { segment: "integrations", label: "Integrations", icon: Plug, comingSoon: true },
  { segment: "costs", label: "Costs", icon: DollarSign, comingSoon: true },
  { segment: "settings", label: "Settings", icon: Settings, comingSoon: true },
];

export interface WorkspaceSubnavProps {
  workspaceId: string;
  /** Optional badge counts to render on the right (e.g. { recommendations: 2 }) */
  badges?: Partial<Record<string, number>>;
}

export function WorkspaceSubnav({ workspaceId, badges }: WorkspaceSubnavProps) {
  const pathname = usePathname();
  const base = `/workspaces/${workspaceId}`;

  return (
    <nav className="space-y-0.5" aria-label="Workspace sections">
      {ITEMS.map((item) => {
        const href = item.segment ? `${base}/${item.segment}` : base;
        const active =
          item.segment === ""
            ? pathname === base
            : pathname === href || pathname.startsWith(`${href}/`);
        const Icon = item.icon;
        const badge = badges?.[item.segment === "" ? "overview" : item.segment];

        const content = (
          <>
            <span
              className={cn(
                "inline-flex items-center gap-2 min-w-0",
                item.comingSoon && !active && "text-ink-soft"
              )}
            >
              <Icon className="h-4 w-4 shrink-0" aria-hidden="true" />
              <span className="truncate">{item.label}</span>
            </span>
            <span className="inline-flex items-center gap-2 shrink-0">
              {item.comingSoon && (
                <span className="text-[10px] uppercase tracking-wide text-ink-soft font-medium">
                  soon
                </span>
              )}
              {typeof badge === "number" && badge > 0 && (
                <span className="inline-flex items-center justify-center h-5 min-w-5 px-1 rounded-sm bg-amber text-ink text-xs font-semibold border-[1.5px] border-ink">
                  {badge}
                </span>
              )}
            </span>
          </>
        );

        const linkClass = cn(
          "flex items-center justify-between gap-2 px-3 py-2 rounded-md text-sm",
          "transition-colors border-[1.5px]",
          active
            ? "bg-amber text-ink border-ink font-medium"
            : "border-transparent text-foreground hover:bg-muted"
        );

        return (
          <Link
            key={item.segment || "overview"}
            href={href}
            aria-current={active ? "page" : undefined}
            className={linkClass}
          >
            {content}
          </Link>
        );
      })}
    </nav>
  );
}
