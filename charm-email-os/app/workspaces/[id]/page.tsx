/**
 * Screen: Workspace Overview
 * The synthesized landing for a workspace: today's chronicle, top recommendations,
 * agent summary. Lets the operator triage at a glance.
 *
 * Design System: [[design-system/index]]
 * Components: [[design-system/components/recommendation-card]] · [[design-system/components/agent-card]] · [[design-system/components/activity-log-row]]
 */
"use client";

import * as React from "react";
import Link from "next/link";
import { notFound, useParams } from "next/navigation";
import { ChevronRight, Sparkles, Bot, ScrollText } from "lucide-react";
import {
  AgentCard,
  ActivityLogRow,
  RecommendationCard,
} from "@/components/charm";
import {
  getWorkspace,
  getAgents,
  getRecommendations,
  getEvents,
} from "@/lib/mock/charm";

export default function WorkspaceOverviewPage() {
  const { id } = useParams<{ id: string }>();
  const workspace = getWorkspace(id);
  if (!workspace) notFound();

  const recommendations = getRecommendations(id);
  const agents = getAgents(id);
  const events = getEvents(id).slice(0, 8);

  return (
    <div className="space-y-10">
      {/* Top recommendations */}
      <section aria-labelledby="overview-recs">
        <div className="flex items-center justify-between mb-4">
          <h2
            id="overview-recs"
            className="text-2xl inline-flex items-center gap-2"
          >
            <Sparkles className="h-5 w-5 text-amber" aria-hidden="true" />
            Recommendations
          </h2>
          {recommendations.length > 2 && (
            <Link
              href={`/workspaces/${id}/recommendations`}
              className="inline-flex items-center gap-1 text-sm text-copper hover:underline focus-visible:underline"
            >
              View all {recommendations.length}
              <ChevronRight className="h-3.5 w-3.5" aria-hidden="true" />
            </Link>
          )}
        </div>

        {recommendations.length === 0 ? (
          <EmptyState
            title="Mailbox is empty"
            description="No pending recommendations from this workspace's agents. Agents are observing — they'll surface anything worth your nod here."
          />
        ) : (
          <div className="space-y-4">
            {recommendations.slice(0, 2).map((rec) => (
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
        )}
      </section>

      {/* Agent summary */}
      <section aria-labelledby="overview-agents">
        <div className="flex items-center justify-between mb-4">
          <h2
            id="overview-agents"
            className="text-2xl inline-flex items-center gap-2"
          >
            <Bot className="h-5 w-5 text-copper" aria-hidden="true" />
            Agents
          </h2>
          <Link
            href={`/workspaces/${id}/agents`}
            className="inline-flex items-center gap-1 text-sm text-copper hover:underline focus-visible:underline"
          >
            Manage agents
            <ChevronRight className="h-3.5 w-3.5" aria-hidden="true" />
          </Link>
        </div>

        {agents.length === 0 ? (
          <EmptyState
            title="No agents configured"
            description="Configure analyst agents (Performance, Health, Domain Insights) to start surfacing recommendations."
          />
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {agents.map((agent) => (
              <AgentCard key={agent.id} agent={agent} />
            ))}
          </div>
        )}
      </section>

      {/* Today's chronicle */}
      <section aria-labelledby="overview-chronicle">
        <div className="flex items-center justify-between mb-4">
          <h2
            id="overview-chronicle"
            className="text-2xl inline-flex items-center gap-2"
          >
            <ScrollText className="h-5 w-5 text-sky" aria-hidden="true" />
            Today's chronicle
          </h2>
          <Link
            href={`/workspaces/${id}/events`}
            className="inline-flex items-center gap-1 text-sm text-copper hover:underline focus-visible:underline"
          >
            Full activity log
            <ChevronRight className="h-3.5 w-3.5" aria-hidden="true" />
          </Link>
        </div>

        {events.length === 0 ? (
          <EmptyState
            title="No events yet"
            description="Daemon events, agent runs, and context syncs will appear here as the workspace activates."
          />
        ) : (
          <ul className="rounded-lg border-[1.5px] border-border-bold bg-card overflow-hidden">
            {events.map((event) => (
              <ActivityLogRow key={event.id} event={event} />
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

function EmptyState({
  title,
  description,
}: {
  title: string;
  description: string;
}) {
  return (
    <div className="flex flex-col items-center justify-center text-center gap-2 py-10 px-6 rounded-lg border border-dashed border-border bg-muted/30">
      <p className="text-base font-medium">{title}</p>
      <p className="text-sm text-ink-soft max-w-md">{description}</p>
    </div>
  );
}
