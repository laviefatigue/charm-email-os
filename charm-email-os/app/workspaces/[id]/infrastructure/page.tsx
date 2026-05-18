/**
 * Screen: Workspace Infrastructure (STUB)
 * Merged Domains + Inboxes. Will list per-ESP (Google 3/domain · MSFT 52/domain)
 * with lifecycle status (incubating/reserve/live/dead/burned) and bulk actions
 * (approve, kill, generate). Real data from /api/inboxes + /api/domains scoped
 * to this workspace.
 */
import * as React from "react";
import { ComingSoon, PageHeader } from "@/components/charm";

export default function WorkspaceInfrastructurePage() {
  return (
    <div>
      <PageHeader
        kicker="Workspace infrastructure"
        title="Infrastructure"
        subtitle="Domains + inboxes for this workspace — lifecycle status, ESP-split (Google vs MSFT), bulk actions."
      />
      <ComingSoon
        title="Infrastructure coming soon"
        description="Will surface domains + inboxes side-by-side with status pills (live / incubating / reserve / dead / burned), ESP filter, kill / approve / generate actions per row. Bound to docs/concepts/esp-aware-data-interpretation.md so aggregates don't lie."
      />
    </div>
  );
}
