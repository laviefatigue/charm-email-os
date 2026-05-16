/**
 * Screen: Workspace Pending Gates (STUB)
 * Daemon-related operator actions (kill confirms, firewall overrides, domain adds).
 * Distinct from agent Recommendations.
 *
 * Design System: [[design-system/index]]
 */
import * as React from "react";
import { ComingSoon, PageHeader } from "@/components/charm";

export default function WorkspacePendingGatesPage() {
  return (
    <div>
      <PageHeader
        kicker="Gates"
        title="Pending Gates"
        subtitle="Operator actions required by daemons — kill confirms, cross-workspace firewall overrides, domain add approvals."
      />
      <ComingSoon
        title="Pending Gates coming soon"
        description="Distinct from agent Recommendations: gates are operator confirmations required by state-machine daemons, not LLM-proposed actions."
      />
    </div>
  );
}
