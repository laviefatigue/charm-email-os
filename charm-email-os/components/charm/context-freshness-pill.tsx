/**
 * Context freshness indicator — minutes since last sync from the client's GitHub repo.
 * Reflects workspace_context_repos.sync_status + last_synced_at.
 * Tokens: --moss, --honey, --rust, --amber, --ink-soft
 * See [[design-system/components/context-freshness-pill]] and [[../architecture/client-context-sync]]
 */
"use client";

import * as React from "react";
import { formatDistanceToNowStrict } from "date-fns";
import { cva, type VariantProps } from "class-variance-authority";
import { GitBranch, AlertTriangle, RefreshCcw, ShieldAlert, MinusCircle } from "lucide-react";
import { cn } from "@/lib/utils";

export type SyncStatus =
  | "ok"
  | "never_synced"
  | "syncing"
  | "failed"
  | "auth_failed"
  | "drift_detected";

const pillVariants = cva(
  "inline-flex items-center gap-1.5 rounded-sm h-6 px-2 text-xs font-medium border-[1.5px] whitespace-nowrap transition-colors",
  {
    variants: {
      tone: {
        fresh: "bg-transparent text-moss border-moss",
        stale: "bg-transparent text-ink border-honey",
        drift: "bg-transparent text-rust border-rust",
        "auth-failed": "bg-rust text-cream-light border-rust",
        syncing: "bg-transparent text-ink border-amber animate-pulse",
        never: "bg-transparent text-ink-soft border-ink-soft",
      },
    },
    defaultVariants: { tone: "fresh" },
  }
);

const FRESH_THRESHOLD_MIN = 60;        // ≤ 60 min = fresh (moss)
const STALE_THRESHOLD_MIN = 360;       // 60–360 min = stale (honey)
// > 360 min = drift (rust)

function computeTone(status: SyncStatus, minutesSinceSync: number | null): {
  tone: NonNullable<VariantProps<typeof pillVariants>["tone"]>;
  label: string;
  Icon: React.ComponentType<{ className?: string }>;
} {
  if (status === "auth_failed") {
    return { tone: "auth-failed", label: "Auth failed", Icon: ShieldAlert };
  }
  if (status === "failed") {
    return { tone: "drift", label: "Sync failed", Icon: AlertTriangle };
  }
  if (status === "drift_detected") {
    return { tone: "drift", label: "Drift detected", Icon: AlertTriangle };
  }
  if (status === "syncing") {
    return { tone: "syncing", label: "Syncing…", Icon: RefreshCcw };
  }
  if (status === "never_synced" || minutesSinceSync === null) {
    return { tone: "never", label: "Never synced", Icon: MinusCircle };
  }
  if (minutesSinceSync <= FRESH_THRESHOLD_MIN) {
    return { tone: "fresh", label: `Fresh · ${minutesSinceSync}m`, Icon: GitBranch };
  }
  if (minutesSinceSync <= STALE_THRESHOLD_MIN) {
    return { tone: "stale", label: `Stale · ${formatHoursMin(minutesSinceSync)}`, Icon: GitBranch };
  }
  return { tone: "drift", label: `Stale · ${formatHoursMin(minutesSinceSync)}`, Icon: AlertTriangle };
}

function formatHoursMin(min: number): string {
  const h = Math.floor(min / 60);
  const m = min % 60;
  if (h >= 24) return `${Math.floor(h / 24)}d`;
  if (m === 0) return `${h}h`;
  return `${h}h ${m}m`;
}

export interface ContextFreshnessPillProps
  extends React.HTMLAttributes<HTMLSpanElement> {
  status: SyncStatus;
  lastSyncedAt?: Date | string | null;
  /** Override the computed label (e.g., "47m fresh"). */
  label?: string;
}

const ContextFreshnessPill = React.forwardRef<
  HTMLSpanElement,
  ContextFreshnessPillProps
>(({ className, status, lastSyncedAt, label, ...props }, ref) => {
  const minutesSinceSync = React.useMemo(() => {
    if (!lastSyncedAt) return null;
    const d = typeof lastSyncedAt === "string" ? new Date(lastSyncedAt) : lastSyncedAt;
    return Math.floor((Date.now() - d.getTime()) / 60000);
  }, [lastSyncedAt]);

  const { tone, label: computedLabel, Icon } = computeTone(status, minutesSinceSync);
  const tooltipTime = lastSyncedAt
    ? formatDistanceToNowStrict(
        typeof lastSyncedAt === "string" ? new Date(lastSyncedAt) : lastSyncedAt,
        { addSuffix: true }
      )
    : undefined;

  return (
    <span
      ref={ref}
      className={cn(pillVariants({ tone }), className)}
      title={tooltipTime}
      {...props}
    >
      <Icon className="h-3 w-3 shrink-0" aria-hidden="true" />
      {label ?? computedLabel}
    </span>
  );
});
ContextFreshnessPill.displayName = "ContextFreshnessPill";

export { ContextFreshnessPill };
