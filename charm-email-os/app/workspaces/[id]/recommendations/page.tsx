/**
 * Screen: Workspace Recommendations
 * The mailbox of pending request_confirmation interactions from this workspace's
 * analyst agents. One-click approve/reject inline with cited context.
 *
 * Design System: [[design-system/index]]
 * Components: [[design-system/components/recommendation-card]]
 */
"use client";

import * as React from "react";
import { notFound, useParams } from "next/navigation";
import { Sparkles } from "lucide-react";
import { RecommendationCard, PageHeader } from "@/components/charm";
import { getWorkspace, getRecommendations } from "@/lib/mock/charm";

export default function WorkspaceRecommendationsPage() {
  const { id } = useParams<{ id: string }>();
  const workspace = getWorkspace(id);
  if (!workspace) notFound();

  const recommendations = getRecommendations(id);

  return (
    <div>
      <PageHeader
        kicker="Mailbox"
        title="Recommendations"
        subtitle={
          recommendations.length === 0
            ? "Nothing waiting on your nod. Agents will post here when they have proposals."
            : `${recommendations.length} pending recommendation${
                recommendations.length === 1 ? "" : "s"
              } from this workspace's agents.`
        }
      />

      {recommendations.length === 0 ? (
        <div className="flex flex-col items-center justify-center text-center gap-3 py-16 px-6 rounded-xl border border-dashed border-border bg-muted/30">
          <span className="inline-flex items-center justify-center h-12 w-12 rounded-md bg-moss/15 text-moss border-[1.5px] border-moss">
            <Sparkles className="h-6 w-6" aria-hidden="true" />
          </span>
          <h3 className="text-xl">Mailbox is empty</h3>
          <p className="text-sm text-ink-soft max-w-md">
            All clear. Agents are observing the workspace — anything that needs
            your nod will appear here.
          </p>
        </div>
      ) : (
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
              onViewDetail={(id) => console.warn("view detail", id)}
            />
          ))}
        </div>
      )}
    </div>
  );
}
