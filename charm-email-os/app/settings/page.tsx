/**
 * Screen: Global Settings (STUB)
 * Operator-level + system-level configuration — GitHub App installation,
 * global firewall rules, daemon-wide toggles, secret store, ops user list.
 *
 * Design System: [[design-system/index]]
 */
import * as React from "react";
import { ComingSoon, PageHeader } from "@/components/charm";

export default function GlobalSettingsPage() {
  return (
    <div className="px-8 py-8 max-w-5xl w-full mx-auto">
      <PageHeader
        kicker="Global"
        title="Settings"
        subtitle="System-level configuration — GitHub App installation, global firewall rules, daemon-wide toggles, secret store, ops user list."
      />
      <ComingSoon
        title="Global settings coming soon"
        description="Per-workspace settings are at /workspaces/[id]/settings. This view will surface system-wide configuration including the Charm Context Sync GitHub App and Plan A firewall rules."
      />
    </div>
  );
}
