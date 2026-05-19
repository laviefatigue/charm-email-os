/**
 * Layout: Workspace detail
 * Renders workspace header (name + slug + attention pill + context freshness)
 * and the 12-item sub-nav left rail. Children render in the main column.
 *
 * Design System: [[design-system/index]]
 * Components: [[design-system/components/workspace-subnav]] · [[design-system/components/context-freshness-pill]]
 */
import * as React from "react";
import Link from "next/link";
import { notFound } from "next/navigation";
import { ChevronLeft, Settings } from "lucide-react";
import {
  ContextFreshnessPill,
  StatusPill,
} from "@/components/charm";
import { getWorkspace } from "@/lib/data/charm";

const ATTENTION_TO_STATUS: Record<string, "live" | "drift" | "burned"> = {
  healthy: "live",
  amber: "drift",
  red: "burned",
};

export default async function WorkspaceLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const workspace = await getWorkspace(id);
  if (!workspace) notFound();

  const attentionKind = ATTENTION_TO_STATUS[workspace.attentionState] ?? "live";

  return (
    <div className="flex flex-col h-full min-h-0">
      {/* Header bar */}
      <div className="px-8 pt-6 pb-4 border-b border-border">
        <Link
          href="/"
          className="inline-flex items-center gap-1 text-xs text-ink-soft hover:text-foreground mb-3 transition-colors"
        >
          <ChevronLeft className="h-3 w-3" aria-hidden="true" />
          All workspaces
        </Link>
        <div className="flex items-end justify-between gap-6">
          <div className="min-w-0">
            <div className="text-xs font-mono uppercase tracking-wider text-ink-soft">
              {workspace.slug ?? workspace.id}
            </div>
            <h1 className="display-village text-5xl truncate mt-1">
              {workspace.name}
            </h1>
            <p className="mt-1.5 text-xs text-ink-soft">
              You&apos;re the CEO of {workspace.name} &mdash; agents propose, you approve.
            </p>
          </div>
          <div className="flex items-center gap-2 shrink-0 pb-2">
            <StatusPill
              kind={attentionKind}
              label={
                workspace.attentionState === "healthy"
                  ? "Healthy"
                  : workspace.attentionState === "amber"
                    ? "Attention"
                    : "Action required"
              }
            />
            <ContextFreshnessPill
              status={workspace.contextSync.status}
              lastSyncedAt={workspace.contextSync.lastSyncedAt}
            />
            <Link
              href={`/workspaces/${id}/settings`}
              aria-label="Workspace settings"
              title="Workspace settings"
              className="inline-flex items-center justify-center h-7 w-7 rounded-md border-[1.5px] border-border text-ink-soft hover:border-border-bold hover:text-foreground transition-colors"
            >
              <Settings className="h-3.5 w-3.5" aria-hidden="true" />
            </Link>
          </div>
        </div>
      </div>

      {/* Content (sub-nav now lives in the global VillageSidebar) */}
      <div className="flex-1 overflow-auto">
        <div className="px-8 py-8 max-w-6xl">{children}</div>
      </div>
    </div>
  );
}
