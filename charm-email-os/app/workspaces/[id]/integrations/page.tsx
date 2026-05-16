/**
 * Screen: Workspace Integrations (STUB)
 * External connections (day.ai, EmailBison, Hypertide, HubSpot, etc.) with
 * connection state, drift detection, re-auth flow.
 *
 * Design System: [[design-system/index]]
 */
import * as React from "react";
import { ComingSoon, PageHeader } from "@/components/charm";

export default function WorkspaceIntegrationsPage() {
  return (
    <div>
      <PageHeader
        kicker="External"
        title="Integrations"
        subtitle="External tool connections — day.ai, EmailBison, Hypertide, HubSpot. Connection state, drift detection, re-auth."
      />
      <ComingSoon
        title="Integrations manager coming soon"
        description="Will surface each wired integration with health, last-sync, and re-auth controls. day.ai is the first integration; more added per-client."
      />
    </div>
  );
}
