/**
 * Screen: Workspace Routines (STUB)
 * Scheduled triggers — cron + webhook + on-event. Both for daemons (EOD reapply,
 * hypertide audit) and agents (daily performance review, weekly forecast).
 *
 * Design System: [[design-system/index]]
 */
import * as React from "react";
import { ComingSoon, PageHeader } from "@/components/charm";

export default function WorkspaceRoutinesPage() {
  return (
    <div>
      <PageHeader
        kicker="Schedule"
        title="Routines"
        subtitle="Scheduled triggers — cron, webhook, on-event. Both daemons (EOD reapply, hypertide audit, Plan F) and agents (daily perf review, weekly burn forecast)."
      />
      <ComingSoon
        title="Routines manager coming soon"
        description="Will surface cron expressions, next-run times, concurrency policies (coalesce_if_active), and catch-up policies (skip_missed) per docs/architecture/agent-runtime.md §Routines."
      />
    </div>
  );
}
