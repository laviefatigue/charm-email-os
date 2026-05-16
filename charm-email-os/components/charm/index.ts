/**
 * Charm Village composites — workspace-first operator UI primitives.
 * Built on shadcn/ui primitives + Charm tokens (see docs/design-system/tokens/).
 */

export { StatusPill, STATUS_KINDS, type StatusKind, statusPillVariants } from "./status-pill";
export { ContextFreshnessPill, type SyncStatus } from "./context-freshness-pill";
export { CostBudgetMeter } from "./cost-budget-meter";
export {
  AgentCard,
  type AgentCardData,
  type AgentStatus,
} from "./agent-card";
export {
  RecommendationCard,
  type RecommendationCardData,
  type CitedContext,
} from "./recommendation-card";
export {
  WorkspaceCard,
  type WorkspaceCardData,
  type AttentionState,
  type IntegrationStatus,
  type IntegrationSummary,
} from "./workspace-card";
export {
  ActivityLogRow,
  type ActivityEvent,
  type ActivityEventType,
  type ActivityEventStatus,
} from "./activity-log-row";

// Shell + layout primitives for the redesign route group
export { AppShell } from "./app-shell";
export { VillageSidebar } from "./village-sidebar";
export { WorkspaceSubnav, type WorkspaceSubnavProps } from "./workspace-subnav";
export { ComingSoon, type ComingSoonProps } from "./coming-soon";
export { PageHeader, type PageHeaderProps } from "./page-header";
