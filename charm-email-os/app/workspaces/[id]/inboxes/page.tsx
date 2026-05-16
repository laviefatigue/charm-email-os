/**
 * Screen: Workspace Inboxes (STUB)
 * Per-inbox state, warmup status, kill triggers. ESP-split tables.
 *
 * Design System: [[design-system/index]]
 */
import * as React from "react";
import { ComingSoon, PageHeader } from "@/components/charm";

export default function WorkspaceInboxesPage() {
  return (
    <div>
      <PageHeader
        kicker="Roster"
        title="Inboxes"
        subtitle="Per-inbox state with ESP-split semantics (Google 3/domain vs MSFT 52/domain)."
      />
      <ComingSoon
        title="Inboxes view coming soon"
        description="Will show per-inbox state, warmup status, kill triggers, and ESP-split tables. Encoded against docs/concepts/esp-aware-data-interpretation.md."
      />
    </div>
  );
}
