/**
 * Screen: Global Activity (STUB)
 * Cross-workspace event feed — daemon events + agent runs + context syncs
 * interleaved across all workspaces.
 *
 * Design System: [[design-system/index]]
 */
import * as React from "react";
import { ComingSoon, PageHeader } from "@/components/charm";

export default function GlobalActivityPage() {
  return (
    <div className="px-8 py-8 max-w-5xl w-full mx-auto">
      <PageHeader
        kicker="Chronicle"
        title="Activity"
        subtitle="Cross-workspace event feed — daemons + agent runs + context syncs across all 5 workspaces, chronologically interleaved."
      />
      <ComingSoon
        title="Global activity feed coming soon"
        description="Per-workspace events are at /workspaces/[id]/events. This view will aggregate them with workspace-name annotation and cross-workspace filtering."
      />
    </div>
  );
}
