/**
 * Screen: Workspace Costs (STUB)
 * Two-tier cost: per-agent LLM spend (Claude tokens) + infrastructure spend
 * (EB seats, HT calls, registrar). With 80%/100% budget enforcement.
 *
 * Design System: [[design-system/index]]
 */
import * as React from "react";
import { ComingSoon, PageHeader } from "@/components/charm";

export default function WorkspaceCostsPage() {
  return (
    <div>
      <PageHeader
        kicker="Spend"
        title="Costs"
        subtitle="Two-tier breakdown: per-agent LLM spend (Claude tokens) + infrastructure spend (EmailBison seats, Hypertide calls, registrar invoices)."
      />
      <ComingSoon
        title="Costs dashboard coming soon"
        description="Will surface monthly spend by agent and by infra category, with 80%/100% budget thresholds and historical trend. CostBudgetMeter component is already built."
      />
    </div>
  );
}
