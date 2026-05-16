/**
 * Screen: Workspace Domains (STUB)
 * Will list domains in the lifecycle pipeline (incubating → reserve → live → dead/burned)
 * with StatusPill for each. Bulk actions: promote, retire, kill.
 *
 * Design System: [[design-system/index]]
 */
import * as React from "react";
import { ComingSoon, PageHeader } from "@/components/charm";

export default function WorkspaceDomainsPage() {
  return (
    <div>
      <PageHeader
        kicker="Lifecycle"
        title="Domains"
        subtitle="Domain pipeline view — incubating → reserve → live → dead/burned. Bulk operations + StatusPill grid."
      />
      <ComingSoon
        title="Domains pipeline coming soon"
        description="Will show the workspace's domains by lifecycle state, with bulk promote / retire / kill actions and per-domain detail."
      />
    </div>
  );
}
