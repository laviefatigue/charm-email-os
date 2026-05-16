/**
 * Screen: Cross-workspace Recommendations Mailbox
 * Aggregates pending request_confirmation interactions across ALL workspaces.
 * Top-level nav entry — the operator's morning triage surface.
 *
 * Design System: [[design-system/index]]
 * Components: [[design-system/components/recommendation-card]]
 */
"use client";

import * as React from "react";
import Link from "next/link";
import { ChevronRight, Sparkles } from "lucide-react";
import { RecommendationCard, PageHeader } from "@/components/charm";
import { MOCK_WORKSPACES, getRecommendations } from "@/lib/mock/charm";

export default function GlobalRecommendationsPage() {
  const byWorkspace = MOCK_WORKSPACES.map((ws) => ({
    workspace: ws,
    recommendations: getRecommendations(ws.id),
  })).filter((entry) => entry.recommendations.length > 0);

  const total = byWorkspace.reduce(
    (sum, entry) => sum + entry.recommendations.length,
    0
  );

  return (
    <div className="px-8 py-8 max-w-5xl w-full mx-auto">
      <PageHeader
        kicker="Mailbox"
        title="Recommendations"
        subtitle={
          total === 0
            ? "All clear across all workspaces."
            : `${total} pending recommendation${total === 1 ? "" : "s"} across ${byWorkspace.length} workspace${byWorkspace.length === 1 ? "" : "s"}.`
        }
      />

      {total === 0 ? (
        <div className="flex flex-col items-center justify-center text-center gap-3 py-16 px-6 rounded-xl border border-dashed border-border bg-muted/30">
          <span className="inline-flex items-center justify-center h-12 w-12 rounded-md bg-moss/15 text-moss border-[1.5px] border-moss">
            <Sparkles className="h-6 w-6" aria-hidden="true" />
          </span>
          <h3 className="text-xl">Mailbox is empty</h3>
          <p className="text-sm text-ink-soft max-w-md">
            All five workspaces are clear. Agents are observing — anything that
            needs your nod will appear here.
          </p>
        </div>
      ) : (
        <div className="space-y-10">
          {byWorkspace.map(({ workspace, recommendations }) => (
            <section key={workspace.id} aria-labelledby={`ws-${workspace.id}`}>
              <div className="flex items-center justify-between mb-4">
                <h2
                  id={`ws-${workspace.id}`}
                  className="text-2xl truncate"
                >
                  {workspace.name}
                  <span className="ml-2 text-base font-mono text-ink-soft">
                    · {recommendations.length}
                  </span>
                </h2>
                <Link
                  href={`/workspaces/${workspace.id}`}
                  className="inline-flex items-center gap-1 text-sm text-copper hover:underline focus-visible:underline"
                >
                  Open workspace
                  <ChevronRight className="h-3.5 w-3.5" aria-hidden="true" />
                </Link>
              </div>
              <div className="space-y-5">
                {recommendations.map((rec) => (
                  <RecommendationCard
                    key={rec.id}
                    recommendation={rec}
                    onAccept={async () => {
                      console.warn("approve", rec.id);
                    }}
                    onReject={async () => {
                      console.warn("reject", rec.id);
                    }}
                    onOpenCitation={(path, sha) =>
                      console.warn("open citation", path, sha)
                    }
                  />
                ))}
              </div>
            </section>
          ))}
        </div>
      )}
    </div>
  );
}
