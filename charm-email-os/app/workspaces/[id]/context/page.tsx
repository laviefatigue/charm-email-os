/**
 * Screen: Workspace Context (STUB)
 * Read-only view of the client's GitHub Foam-markdown repo: client.md, notes,
 * feedback, decisions, with backlink graph. Sync status + freshness.
 *
 * Design System: [[design-system/index]]
 */
import * as React from "react";
import { ComingSoon, PageHeader } from "@/components/charm";

export default function WorkspaceContextPage() {
  return (
    <div>
      <PageHeader
        kicker="Source of truth"
        title="Context"
        subtitle="The client's Foam-markdown context repo — notes, feedback, decisions, client card, with backlink graph and sync status."
      />
      <ComingSoon
        title="Context view coming soon"
        description="Will render the client's GitHub-hosted Foam repo read-only with backlink graph, search, and sync history. See docs/architecture/client-context-sync.md."
      />
    </div>
  );
}
