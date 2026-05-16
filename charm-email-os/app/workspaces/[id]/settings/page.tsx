/**
 * Screen: Workspace Settings (STUB)
 * Per-workspace flags: eod_reapply_enabled, manages_via_hypertide, package_id,
 * agent budgets, daemon toggles, context-repo binding.
 *
 * Design System: [[design-system/index]]
 */
import * as React from "react";
import { ComingSoon, PageHeader } from "@/components/charm";

export default function WorkspaceSettingsPage() {
  return (
    <div>
      <PageHeader
        kicker="Configuration"
        title="Settings"
        subtitle="Per-workspace flags + agent budgets + daemon toggles + context-repo binding."
      />
      <ComingSoon
        title="Workspace settings coming soon"
        description="Will surface eod_reapply_enabled, manages_via_hypertide, package_id, per-agent monthly budgets, daemon enable toggles, and the GitHub context-repo binding (workspace_context_repos row)."
      />
    </div>
  );
}
